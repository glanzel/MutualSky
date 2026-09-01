from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from .. import i18n
from ..atproto_service import make_persist_cb, session_to_dict
from ..bluesky import actions as bsky_actions
from ..bluesky import client as public_client
from ..config import get_settings
from ..deps import current_user
from ..models import User
from ..offers import pending_offer_between
from ..security import rate_limit
from ..ui import components as ui_components
from ..ui import partials as ui_partials
from ..ui import profile as profile_ui

router = APIRouter()


@router.post("/profiles/search", dependencies=[Depends(rate_limit(20, 60))])
async def search_profiles(request: Request):
    form = await request.form()
    query = str(form.get("q", "")).strip()
    raw_max = str(form.get("max_followers", "")).strip()
    max_followers = int(raw_max) if raw_max.isdigit() and int(raw_max) > 0 else None
    if not query:
        return HTMLResponse(str(ui_components.SearchResults(actors=[], max_followers=max_followers)))
    try:
        actors, cursor = await public_client.search_profiles(query, max_followers=max_followers)
    except public_client.PublicBskyError as exc:
        return HTMLResponse(str(ui_components.Notice(kind="error", children=[i18n.t("Suche fehlgeschlagen: {fehler}", fehler=exc)])))
    return HTMLResponse(
        str(ui_components.SearchResults(actors=actors, max_followers=max_followers, query=query, cursor=cursor))
    )


@router.post("/profiles/search/more", dependencies=[Depends(rate_limit(60, 60))])
async def search_profiles_more(request: Request):
    form = await request.form()
    query = str(form.get("q", "")).strip()
    raw_max = str(form.get("max_followers", "")).strip()
    max_followers = int(raw_max) if raw_max.isdigit() and int(raw_max) > 0 else None
    cursor = str(form.get("cursor", "")).strip()
    if not query or not cursor:
        return HTMLResponse(str(ui_components.Notice(kind="error", children=[i18n.t("Such-Sitzung abgelaufen.")])))
    actors, next_cursor = await public_client.search_profiles(query, max_followers=max_followers, cursor=cursor)
    return HTMLResponse(
        str(ui_components.MoreResults(actors=actors, max_followers=max_followers, query=query, cursor=next_cursor))
    )


@router.get("/profile/{handle}", response_class=HTMLResponse)
async def profile_page(request: Request, handle: str, user: User | None = Depends(current_user)):
    try:
        profile = await public_client.get_profile(handle)
    except public_client.PublicBskyError:
        viewer_view = None
        if user:
            viewer_view = {"handle": user.handle, "display_name": user.display_name or user.handle, "avatar": user.avatar_url}
        return HTMLResponse(str(profile_ui.Profile404(handle=handle, user=viewer_view)), status_code=404)

    viewer_did = user.did if user else None
    profile_did = profile.get("did", "")

    if viewer_did is None:
        action = ui_partials.LoginCta(next_url="/profile/" + handle)
        notice = None
    elif viewer_did == profile_did:
        action = ui_partials.InfoPanel(text=i18n.t("Das ist dein eigenes Profil."))
        notice = None
    else:
        offer_me_to_them = await pending_offer_between(user.did, profile_did)
        offer_them_to_me = await pending_offer_between(profile_did, user.did)
        action = None
        notice = None
        if offer_me_to_them is not None:
            action = ui_partials.InfoPanel(text=i18n.t("Dein Angebot ist ausstehend – du folgst erst nach der Bestätigung."))
            notice = None
        elif offer_them_to_me is not None:
            action = ui_partials.InfoPanel(text=i18n.t("Diese Person hat dir einen Follow-Swap angeboten."))
        else:
            try:
                already = await public_client.does_follow(user.did, profile_did)
            except public_client.PublicBskyError:
                already = False
            if already:
                action = ui_partials.InfoPanel(text=i18n.t("Du folgst diesem Account bereits."))
            else:
                action = ui_partials.OfferStartButton(target_handle=profile.get("handle", ""))

    viewer_view = None
    if user:
        viewer_view = {"handle": user.handle, "display_name": user.display_name or user.handle, "avatar": user.avatar_url}

    page = profile_ui.ProfilePage(
        profile=profile,
        viewer=viewer_view,
        action=action,
        notice=notice,
    )
    return str(page)


@router.post("/posts/search", dependencies=[Depends(rate_limit(20, 60))])
async def search_posts_route(request: Request, user: User | None = Depends(current_user)):
    if user is None:
        return HTMLResponse(str(ui_partials.LoginCta(next_url="/")))
    settings = get_settings()
    session = session_to_dict(user, settings)
    form = await request.form()
    query = str(form.get("q", "")).strip()
    raw_max = str(form.get("max_followers", "")).strip()
    max_followers = int(raw_max) if raw_max.isdigit() and int(raw_max) > 0 else None
    if not query:
        return HTMLResponse(str(ui_components.PostResults(posts=[], max_followers=max_followers)))
    try:
        posts, cursor = await bsky_actions.search_posts(
            session, query, settings, persist_cb=make_persist_cb(user, settings)
        )
    except bsky_actions.AuthSessionError as exc:
        return HTMLResponse(
            str(ui_components.Notice(kind="error", children=[str(exc), ' '])) + '<a class="btn btn-primary" href="/auth/login">i18n.t("Erneut anmelden")</a>'
        )
    except bsky_actions.BlueskyActionError as exc:
        return HTMLResponse(str(ui_components.Notice(kind="error", children=[i18n.t("Post-Suche fehlgeschlagen: {fehler}", fehler=exc)])))
    posts = await public_client.enrich_posts_authors(posts, max_followers=max_followers)
    return HTMLResponse(
        str(ui_components.PostResults(posts=posts, max_followers=max_followers, query=query, cursor=cursor))
    )


@router.post("/posts/search/more", dependencies=[Depends(rate_limit(60, 60))])
async def search_posts_more(request: Request, user: User | None = Depends(current_user)):
    if user is None:
        return HTMLResponse(str(ui_partials.LoginCta(next_url="/")))
    settings = get_settings()
    session = session_to_dict(user, settings)
    form = await request.form()
    query = str(form.get("q", "")).strip()
    raw_max = str(form.get("max_followers", "")).strip()
    max_followers = int(raw_max) if raw_max.isdigit() and int(raw_max) > 0 else None
    cursor = str(form.get("cursor", "")).strip()
    if not query or not cursor:
        return HTMLResponse(str(ui_components.Notice(kind="error", children=[i18n.t("Such-Sitzung abgelaufen.")])))
    try:
        posts, next_cursor = await bsky_actions.search_posts(
            session, query, settings, persist_cb=make_persist_cb(user, settings), cursor=cursor
        )
    except bsky_actions.AuthSessionError as exc:
        return HTMLResponse(
            str(ui_components.Notice(kind="error", children=[str(exc), ' '])) + '<a class="btn btn-primary" href="/auth/login">i18n.t("Erneut anmelden")</a>'
        )
    except bsky_actions.BlueskyActionError as exc:
        return HTMLResponse(str(ui_components.Notice(kind="error", children=[i18n.t("Post-Suche fehlgeschlagen: {fehler}", fehler=exc)])))
    posts = await public_client.enrich_posts_authors(posts, max_followers=max_followers)
    return HTMLResponse(
        str(ui_components.MorePostResults(posts=posts, max_followers=max_followers, query=query, cursor=next_cursor))
    )