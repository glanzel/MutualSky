from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..deps import current_user
from ..models import Offer, User
from ..offers import lazy_expire
from ..ui import home as home_ui

router = APIRouter()


def _user_view(user: User) -> dict:
    return {
        "handle": user.handle,
        "display_name": user.display_name or user.handle,
        "avatar": user.avatar_url,
    }


def _offer_view(offer: Offer) -> dict:
    return {
        "id": offer.id,
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

    outgoing = await Offer.objects.filter(offerer_did=user.did).all()
    incoming = await Offer.objects.filter(target_did=user.did).all()
    all_offers = list(outgoing) + list(incoming)
    for offer in all_offers:
        await lazy_expire(offer)

    page = home_ui.Dashboard(
        user=_user_view(user),
        outgoing=[_offer_view(o) for o in outgoing],
        incoming=[_offer_view(o) for o in incoming],
    )
    return str(page)