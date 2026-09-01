from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..config import get_settings
from ..deps import current_user
from ..models import (
    STATUS_COMPLETED,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    Offer,
    User,
)
from ..offers import lazy_expire, link_for
from ..ui import home as home_ui

router = APIRouter()


def _user_view(user: User) -> dict:
    return {
        "handle": user.handle,
        "display_name": user.display_name or user.handle,
        "avatar": user.avatar_url,
    }


def _offer_view(offer: Offer, settings) -> dict:
    return {
        "id": offer.id,
        "offer_url": link_for(offer, settings),
        "offerer_did": offer.offerer_did,
        "offerer_handle": offer.offerer_handle,
        "target_did": offer.target_did,
        "target_handle": offer.target_handle,
        "status": offer.status,
        "dm_status": offer.dm_status,
        "expires_at": offer.expires_at,
    }


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User | None = Depends(current_user)):
    if user is None:
        return str(home_ui.LandingPage())

    settings = get_settings()
    outgoing = await Offer.objects.filter(offerer_did=user.did).all()
    incoming = await Offer.objects.filter(target_did=user.did).all()
    for offer in list(outgoing) + list(incoming):
        await lazy_expire(offer)

    open_statuses = (STATUS_PENDING, STATUS_PROCESSING)
    outgoing = [o for o in outgoing if o.status in open_statuses]
    incoming = [o for o in incoming if o.status in open_statuses]

    page = home_ui.Dashboard(
        user=_user_view(user),
        outgoing=[_offer_view(o, settings) for o in outgoing],
        incoming=[_offer_view(o, settings) for o in incoming],
    )
    return str(page)


@router.get("/archiv", response_class=HTMLResponse)
async def archive(request: Request, user: User | None = Depends(current_user)):
    if user is None:
        return str(home_ui.LandingPage())

    settings = get_settings()
    outgoing = await Offer.objects.filter(offerer_did=user.did).all()
    incoming = await Offer.objects.filter(target_did=user.did).all()
    for offer in list(outgoing) + list(incoming):
        await lazy_expire(offer)

    archived_statuses = (STATUS_COMPLETED, STATUS_EXPIRED)
    outgoing = [o for o in outgoing if o.status in archived_statuses]
    incoming = [o for o in incoming if o.status in archived_statuses]

    page = home_ui.ArchivePage(
        user=_user_view(user),
        outgoing=[_offer_view(o, settings) for o in outgoing],
        incoming=[_offer_view(o, settings) for o in incoming],
    )
    return str(page)