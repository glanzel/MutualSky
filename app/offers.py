"""Offer lifecycle helpers (creation, expiry) independent of HTTP routing."""

import hashlib
import hmac
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


def _offer_sig(offer_id: int, settings) -> str:
    return hmac.new(
        settings.encryption_secret.encode(),
        f"mutualsky:offer:{offer_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:16]


def offer_ref(offer, settings) -> str:
    """Capability reference ``<id>-<sig>``; URLs are not enumerable without it."""
    return f"{offer.id}-{_offer_sig(offer.id, settings)}"


def verify_offer_ref(ref: str, settings) -> int | None:
    """Return the offer id for a signed ref, or None when the signature is invalid."""
    id_part, sep, sig_part = ref.partition("-")
    if not sep or not id_part.isdigit() or not sig_part:
        return None
    expected = _offer_sig(int(id_part), settings)
    if not hmac.compare_digest(sig_part, expected):
        return None
    return int(id_part)


def link_for(offer: Offer, settings) -> str:
    return f"{settings.public_base_url}/o/{offer_ref(offer, settings)}"


def offer_dm_payload(offer: Offer, settings) -> tuple[str, list[dict]]:
    """Build the DM text (with a clickable link facet) notifying the target."""
    url = link_for(offer, settings)
    text = (
        f"MutualSky · Follow-Swap\n"
        f"\n"
        f"@{offer.offerer_handle} hat dir einen Follow-Swap angeboten:\n"
        f"Du folgst @{offer.offerer_handle}, und er/sie folgt dir im Gegenzug zurück.\n"
        f"\n"
        f"Zum Angebot:\n{url}"
    )
    encoded = text.encode("utf-8")
    byte_start = len(encoded) - len(url.encode("utf-8"))
    byte_end = len(encoded)
    facets = [
        {
            "index": {"byteStart": byte_start, "byteEnd": byte_end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
        }
    ]
    return text, facets


def offer_reply_payload(offer: Offer, settings) -> tuple[str, list[dict]]:
    """Build a public reply to the target's post (mention + clickable link)."""
    url = link_for(offer, settings)
    mention = f"@{offer.target_handle}"
    text = (
        f"{mention} – ich habe dir über MutualSky einen Follow-Swap vorgeschlagen:\n"
        f"Wir folgen uns gegenseitig und sind danach wechselseitig verbunden.\n"
        f"\n"
        f"Angebot ansehen: {url}"
    )
    encoded = text.encode("utf-8")
    mention = f"@{offer.target_handle}" if offer.target_handle else ""
    mention_bytes = len(mention.encode("utf-8"))
    url_start = len(encoded) - len(url.encode("utf-8"))
    url_end = len(encoded)
    facets = []
    if mention:
        facets.append(
            {
                "index": {"byteStart": 0, "byteEnd": mention_bytes},
                "features": [{"$type": "app.bsky.richtext.facet#mention", "did": offer.target_did}],
            }
        )
    facets.append(
        {
            "index": {"byteStart": url_start, "byteEnd": url_end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
        }
    )
    return text, facets


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