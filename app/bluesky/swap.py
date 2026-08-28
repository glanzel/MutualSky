"""Confirm orchestration: execute BOTH follows in one step when the target
confirms the friendship in the app. Deliberately decoupled from HTTP so the
logic is unit-testable.
"""

from enum import Enum

from ..atproto_service import make_persist_cb, session_to_dict
from ..models import (
    STATUS_COMPLETED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    Offer,
    User,
    utcnow,
)
from ..offers import lazy_expire
from . import actions


class ConfirmOutcome(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    NOT_AUTHORIZED = "not_authorized"
    ALREADY_FINISHED = "already_finished"
    EXPIRED = "expired"
    OFFERER_UNAVAILABLE = "offerer_unavailable"
    TARGET_UNAVAILABLE = "target_unavailable"
    TARGET_FOLLOW_FAILED = "target_follow_failed"
    OFFERER_FOLLOW_FAILED = "offerer_follow_failed"


class ConfirmResult:
    def __init__(self, outcome: ConfirmOutcome, offer: Offer | None, error: str = ""):
        self.outcome = outcome
        self.offer = offer
        self.error = error


async def confirm_swap(offer_id: int, actor_did: str, settings) -> ConfirmResult:
    offer = await Offer.objects.get_or_none(id=offer_id)
    if offer is None:
        return ConfirmResult(ConfirmOutcome.NOT_FOUND, None, "Angebot nicht gefunden.")
    if offer.target_did != actor_did:
        return ConfirmResult(
            ConfirmOutcome.NOT_AUTHORIZED, offer, "Nur die angefragte Person kann bestätigen."
        )
    if await lazy_expire(offer):
        return ConfirmResult(ConfirmOutcome.EXPIRED, offer, "Das Angebot ist abgelaufen.")
    if offer.status == STATUS_COMPLETED:
        return ConfirmResult(ConfirmOutcome.ALREADY_FINISHED, offer, "Angebot bereits erfüllt.")

    # Atomic claim: only one confirm may process a pending offer.
    claimed = await Offer.objects.filter(id=offer_id, status=STATUS_PENDING).update(
        status=STATUS_PROCESSING
    )
    if not claimed:
        offer.status = STATUS_PROCESSING
        return ConfirmResult(ConfirmOutcome.ALREADY_FINISHED, offer, "Wird schon verarbeitet.")
    offer.status = STATUS_PROCESSING

    target_user = await User.objects.get_or_none(did=offer.target_did)
    offerer_user = await User.objects.get_or_none(did=offer.offerer_did)

    if target_user is None:
        offer.status = STATUS_PENDING
        await offer.save()
        return ConfirmResult(ConfirmOutcome.TARGET_UNAVAILABLE, offer, "")
    if offerer_user is None:
        offer.status = STATUS_PENDING
        await offer.save()
        return ConfirmResult(ConfirmOutcome.OFFERER_UNAVAILABLE, offer, "")

    target_session = session_to_dict(target_user, settings)
    offerer_session = session_to_dict(offerer_user, settings)
    persist_target = make_persist_cb(target_user, settings)
    persist_offerer = make_persist_cb(offerer_user, settings)

    # Step 1: target follows the offerer (using the target's own grant).
    try:
        await actions.follow_user(
            target_session,
            offerer_user.did,
            settings,
            persist_cb=persist_target,
        )
    except Exception as exc:  # noqa: BLE001 - surface any provider error
        offer.status = STATUS_PENDING
        offer.follow_error = f"Dein Follow konnte nicht gesetzt werden: {exc}"
        await offer.save()
        await target_user.save()
        await offerer_user.save()
        return ConfirmResult(ConfirmOutcome.TARGET_FOLLOW_FAILED, offer, str(exc))

    # Step 2: offerer follows back (using the offerer's stored grant).
    try:
        await actions.follow_user(
            offerer_session,
            target_user.did,
            settings,
            persist_cb=persist_offerer,
        )
    except Exception as exc:  # noqa: BLE001
        offer.status = STATUS_PENDING
        offer.follow_error = (
            f"@{(offerer_user.handle or offerer_user.did)}'s Follow konnte nicht "
            f"gesetzt werden: {exc}"
        )
        await offer.save()
        await offerer_user.save()
        await target_user.save()
        return ConfirmResult(ConfirmOutcome.OFFERER_FOLLOW_FAILED, offer, str(exc))

    offer.status = STATUS_COMPLETED
    offer.completed_at = utcnow()
    offer.follow_error = None
    await offer.save()
    await target_user.save()
    await offerer_user.save()
    return ConfirmResult(ConfirmOutcome.SUCCESS, offer, "")