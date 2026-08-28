"""Offer lifecycle helpers (creation, expiry) independent of HTTP routing."""

from datetime import timedelta

from .models import (
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    Offer,
    User,
    utcnow,
)


class OfferError(Exception):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def link_for(offer: Offer, settings) -> str:
    return f"{settings.public_base_url}/o/{offer.id}"


async def active_offer_count(user: User) -> int:
    return await Offer.objects.filter(
        offerer_did=user.did, status__in=[STATUS_PENDING, STATUS_PROCESSING]
    ).count()


async def latest_offer_by(user: User) -> Offer | None:
    return await Offer.objects.filter(offerer_did=user.did).order_by("-created_at").first()


async def pending_offer_between(offerer_did: str, target_did: str) -> Offer | None:
    return await Offer.objects.filter(
        offerer_did=offerer_did,
        target_did=target_did,
        status__in=[STATUS_PENDING, STATUS_PROCESSING],
    ).first()


async def create_offer(offerer: User, target_did: str, target_handle: str, settings) -> Offer:
    if offerer.did == target_did:
        raise OfferError("Du kannst dir selbst keinen Follow-Swap anbieten.")
    if await active_offer_count(offerer) >= settings.max_active_offers:
        raise OfferError(
            f"Maximal {settings.max_active_offers} aktive Angebote pro Account erlaubt."
        )
    latest = await latest_offer_by(offerer)
    if latest and latest.created_at:
        elapsed = (utcnow() - latest.created_at).total_seconds()
        if elapsed < settings.offer_cooldown_seconds:
            wait = int(settings.offer_cooldown_seconds - elapsed)
            raise OfferError(f"Bitte warte {wait}s, bevor du das nächste Angebot erstellst.")
    if await pending_offer_between(offerer.did, target_did):
        raise OfferError("Ein offenes Angebot für diesen Account existiert bereits.")

    offer = Offer(
        offerer_did=offerer.did,
        offerer_handle=offerer.handle,
        target_did=target_did,
        target_handle=target_handle,
        status=STATUS_PENDING,
        expires_at=utcnow() + timedelta(days=settings.offer_ttl_days),
    )
    await offer.save()
    return offer


async def lazy_expire(offer: Offer) -> bool:
    """Expire an offer lazily when its deadline passed. Returns True if expired."""
    if (
        offer.status == STATUS_PENDING
        and offer.expires_at is not None
        and utcnow() > offer.expires_at
    ):
        offer.status = STATUS_EXPIRED
        await offer.save()
        return True
    return False