from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from ..atproto_service import make_persist_cb, session_to_dict
from ..bluesky import actions as bsky_actions
from ..bluesky import client as public_client
from ..bluesky.swap import ConfirmOutcome, confirm_swap
from ..config import get_settings
from ..deps import current_user
from ..models import (
    DM_FAILED,
    DM_SENT,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_PENDING,
    Offer,
    User,
    utcnow,
)
from ..oauth.atproto_identity import is_valid_did, is_valid_handle, resolve_identity
from ..offers import OfferError, create_offer, lazy_expire, link_for
from ..security import rate_limit
from ..ui import components as ui_components
from ..ui import offer as offer_ui
from ..ui import partials as ui_partials

router = APIRouter()


def _offer_view(offer: Offer, action, notice="") -> dict:
    return {
        "id": offer.id,
        "offerer_did": offer.offerer_did,
        "offerer_handle": offer.offerer_handle,
        "target_did": offer.target_did,
        "target_handle": offer.target_handle,
        "status": offer.status,
        "dm_status": offer.dm_status,
        "action_panel": action,
        "notice": notice,
        "expires_at": offer.expires_at,
    }


def _viewer_view(user: User) -> dict:
    return {
        "handle": user.handle,
        "display_name": user.display_name or user.handle,
        "avatar": user.avatar_url,
    }


@router.post("/offers", dependencies=[Depends(rate_limit(10, 60))])
async def create_offer_route(request: Request, user: User | None = Depends(current_user)):
    if user is None:
        raise HTTPException(status_code=401, detail="Anmeldung erforderlich.")
    settings = get_settings()
    form = await request.form()
    target_raw = str(form.get("target", "")).strip()
    target_raw = target_raw.removeprefix("@")

    if not (is_valid_handle(target_raw) or is_valid_did(target_raw)):
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text="Ungültiger Handle oder DID.")))

    try:
        target_did, target_handle, _ = await resolve_identity(target_raw)
    except Exception as exc:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text=f"Account konnte nicht aufgelöst werden: {exc}")))

    try:
        offer = await create_offer(user, target_did, target_handle, settings)
    except OfferError as exc:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text=str(exc))))

    # Notify the target per DM (best effort).
    if settings.dm_enabled and "chat.bsky" in (user.scope or ""):
        session = session_to_dict(user, settings)
        message = (
            f"MutualSky: @{user.handle} bietet dir einen Follow-Swap an – "
            f"du bekommst einen Follow von @{user.handle}, wenn du zurückfolgst. "
            f"Bestätigen: {link_for(offer, settings)}"
        )
        try:
            await bsky_actions.send_dm(session, target_did, message, settings, persist_cb=make_persist_cb(user, settings))
            offer.dm_status = DM_SENT
            offer.dm_error = None
        except Exception as exc:
            offer.dm_status = DM_FAILED
            offer.dm_error = str(exc)
    else:
        offer.dm_status = DM_FAILED
        offer.dm_error = "DM nicht möglich (kein chat.bsky-Scope)."
    await offer.save()

    return HTMLResponse(str(ui_partials.OfferCreatedPanel(offer_url=link_for(offer, settings))))


@router.get("/o/{offer_id}", response_class=HTMLResponse)
async def offer_page(request: Request, offer_id: int, user: User | None = Depends(current_user)):
    offer = await Offer.objects.get_or_none(id=offer_id)
    if offer is None:
        return HTMLResponse(str(offer_ui.Offer404()), status_code=404)
    await lazy_expire(offer)
    if offer.status == STATUS_PENDING:
        await offer.refresh()

    offerer_profile = await _safe_profile(offer.offerer_handle)
    target_profile = await _safe_profile(offer.target_handle)

    viewer = _viewer_view(user) if user else None
    is_target = bool(user and user.did == offer.target_did)
    is_offerer = bool(user and user.did == offer.offerer_did)

    action = None
    notice = None
    if offer.follow_error and (is_target or is_offerer):
        notice = ui_components.Notice(children=[offer.follow_error], kind="error")

    if offer.status == STATUS_PENDING:
        if is_target:
            action = ui_partials.ConfirmPanel(confirm_url=f"/offers/{offer.id}/confirm", offerer=offer.offerer_handle)
        elif is_offerer:
            action = ui_partials.CancelPanel(
                cancel_url=f"/offers/{offer.id}/cancel",
                resend_url=f"/offers/{offer.id}/resend-dm",
                dm_failed=(offer.dm_status == DM_FAILED),
            )
        elif user is None:
            action = ui_partials.LoginCta(next_url=f"/o/{offer.id}")
        else:
            action = ui_partials.InfoPanel(text="Nur die angefragte Person kann diesen Tausch bestätigen.")
    elif offer.status == STATUS_COMPLETED:
        action = ui_partials.ResultPanel(ok=True, text="Erfüllt – ihr folgt euch jetzt gegenseitig.")
    elif offer.status == STATUS_CANCELLED:
        action = ui_partials.ResultPanel(ok=False, text="Dieses Angebot wurde zurückgezogen.")
    else:
        action = ui_partials.ResultPanel(ok=False, text="Dieses Angebot ist abgelaufen.")

    page = offer_ui.OfferPage(
        offer=_offer_view(offer, action, notice),
        viewer=viewer,
        offerer_profile=offerer_profile,
        target_profile=target_profile,
    )
    return str(page)


@router.post("/offers/{offer_id}/confirm", dependencies=[Depends(rate_limit(10, 60))])
async def confirm_offer_route(request: Request, offer_id: int, user: User | None = Depends(current_user)):
    if user is None:
        raise HTTPException(status_code=401, detail="Anmeldung erforderlich.")
    settings = get_settings()
    result = await confirm_swap(offer_id, user.did, settings)
    if result.outcome == ConfirmOutcome.SUCCESS:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=True, text="Tausch erfüllt – ihr folgt euch jetzt gegenseitig.")))
    if result.outcome == ConfirmOutcome.EXPIRED:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text="Dieses Angebot ist abgelaufen.")))
    if result.outcome == ConfirmOutcome.ALREADY_FINISHED:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text="Dieses Angebot ist bereits abgeschlossen.")))
    if result.outcome == ConfirmOutcome.NOT_AUTHORIZED:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text="Du bist nicht die angefragte Person.")))
    if result.outcome == ConfirmOutcome.TARGET_UNAVAILABLE:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text="Dein Account ist bei uns nicht (mehr) angemeldet.")))
    if result.outcome == ConfirmOutcome.OFFERER_UNAVAILABLE:
        return HTMLResponse(
            str(ui_partials.ResultPanel(ok=False, text="Der Anbieter hat seine Anmeldung entfernt – der Tausch kann nicht abgeschlossen werden."))
        )
    return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text=result.error or "Tausch fehlgeschlagen – bitte erneut versuchen.")))


@router.post("/offers/{offer_id}/cancel", dependencies=[Depends(rate_limit(10, 60))])
async def cancel_offer_route(request: Request, offer_id: int, user: User | None = Depends(current_user)):
    if user is None:
        raise HTTPException(status_code=401, detail="Anmeldung erforderlich.")
    offer = await Offer.objects.get_or_none(id=offer_id)
    if offer is None:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text="Angebot nicht gefunden.")))
    if offer.offerer_did != user.did:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text="Nur der Anbieter kann zurückziehen.")))
    if offer.status == STATUS_PENDING:
        offer.status = STATUS_CANCELLED
        offer.cancelled_at = utcnow()
        await offer.save()
    return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text="Angebot zurückgezogen.")))


@router.post("/offers/{offer_id}/resend-dm", dependencies=[Depends(rate_limit(5, 60))])
async def resend_dm_route(request: Request, offer_id: int, user: User | None = Depends(current_user)):
    if user is None:
        raise HTTPException(status_code=401, detail="Anmeldung erforderlich.")
    settings = get_settings()
    offer = await Offer.objects.get_or_none(id=offer_id)
    if offer is None:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text="Angebot nicht gefunden.")))
    if offer.offerer_did != user.did:
        return HTMLResponse(str(ui_partials.ResultPanel(ok=False, text="Nur der Anbieter kann eine Nachricht senden.")))
    offer.dm_status = DM_FAILED
    offer.dm_error = None
    await offer.save()
    if settings.dm_enabled and "chat.bsky" in (user.scope or ""):
        session = session_to_dict(user, settings)
        message = (
            f"MutualSky: @{user.handle} bietet dir einen Follow-Swap an – "
            f"du bekommst einen Follow von @{user.handle}, wenn du zurückfolgst. "
            f"Bestätigen: {link_for(offer, settings)}"
        )
        try:
            await bsky_actions.send_dm(session, offer.target_did, message, settings, persist_cb=make_persist_cb(user, settings))
            offer.dm_status = DM_SENT
        except Exception as exc:
            offer.dm_status = DM_FAILED
            offer.dm_error = str(exc)
    await offer.save()
    dm_failed = offer.dm_status == DM_FAILED
    return HTMLResponse(
        str(ui_partials.CancelPanel(cancel_url=f"/offers/{offer.id}/cancel", resend_url=f"/offers/{offer.id}/resend-dm", dm_failed=dm_failed))
    )


async def _safe_profile(handle: str) -> dict:
    if not handle:
        return {}
    try:
        return await public_client.get_profile(handle)
    except public_client.PublicBskyError:
        return {"handle": handle, "displayName": handle, "avatar": None}