from unittest.mock import AsyncMock, patch

import pytest

from app.bluesky.swap import ConfirmOutcome, ConfirmResult
from app.deps import current_user
from app.main import app


# --------------------------------------------------------------------------- #
# Public pages
# --------------------------------------------------------------------------- #
def test_landing_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Tausche Follows mit Bluesky" in resp.text


def test_login_page(client):
    resp = client.get("/auth/login")
    assert resp.status_code == 200
    assert "Mit Bluesky anmelden" in resp.text


def test_client_metadata(client):
    resp = client.get("/bsky-oauth-client.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "/bsky-oauth-client.json" in data["client_id"]
    assert "auth/callback" in data["redirect_uris"][0]
    assert data["token_endpoint_auth_method"] == "private_key_jwt"
    assert "keys" in data["jwks"]


def test_auth_start_invalid_handle_redirects(client):
    resp = client.post("/auth/start", data={"handle": "invalid-handle"}, follow_redirects=False)
    assert resp.status_code == 303
    assert "/auth/login" in resp.headers["location"]


def test_profile_404(client):
    from app.bluesky import client as public_client

    with patch(
        "app.routes.profiles.public_client.get_profile",
        new=AsyncMock(side_effect=public_client.PublicBskyError("nf", 404, "")),
    ):
        resp = client.get("/profile/does-not-exist.bsky")
        assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Authenticated flows
# --------------------------------------------------------------------------- #
@pytest.fixture()
def alice(make_user, client):
    async def _create():
        return await make_user("did:plc:route-alice", "route-alice.test", display_name="Route Alice")



def _override_user(app_obj, user):
    app_obj.dependency_overrides[current_user] = lambda: user
    return app_obj


def _clear_overrides(app_obj):
    app_obj.dependency_overrides.pop(current_user, None)


def test_dashboard_authenticated(client, make_user, settings):
    user = None

    async def _seed():
        return await make_user("did:plc:route-alice", "route-alice.test", display_name="Route Alice")

    import asyncio

    user = asyncio.run(_seed())
    _override_user(app, user)
    try:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Route Alice" in resp.text or "route-alice.test" in resp.text
        assert "Hallo" in resp.text
    finally:
        _clear_overrides(app)


def test_create_offer_htmx(client, make_user, settings):
    import asyncio

    user = asyncio.run(make_user("did:plc:route-alice", "route-alice.test", display_name="Route Alice"))
    _override_user(app, user)
    try:
        with (
            patch(
                "app.routes.offers.resolve_identity",
                new=AsyncMock(return_value=("did:plc:bob-real", "bob.test", {})),
            ),
            patch("app.bluesky.client.get_chat_allow_incoming", new=AsyncMock(return_value="all")),
            patch("app.bluesky.client.does_follow", new=AsyncMock(return_value=False)),
            patch("app.bluesky.actions.send_dm", new=AsyncMock()) as send_dm,
        ):
            resp = client.post("/offers", data={"target": "bob.test"}, headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "Angebot erstellt" in resp.text
        send_dm.assert_awaited_once()
    finally:
        _clear_overrides(app)


    offers = await_offers(user.did)
    assert len(offers) == 1
    assert offers[0].target_handle == "bob.test"


def test_offer_public_page(client, make_user):
    import asyncio
    from datetime import timedelta

    from app.models import Offer, utcnow

    user = asyncio.run(make_user("did:plc:pub-alice", "pub-alice.test"))
    user_bob = asyncio.run(make_user("did:plc:pub-bob", "pub-bob.test"))
    asyncio.run(
        Offer.objects.create(
            offerer_did=user.did,
            offerer_handle=user.handle,
            target_did=user_bob.did,
            target_handle=user_bob.handle,
            status="pending",
            expires_at=utcnow() + timedelta(days=14),
        )
    )
    offer_id = asyncio.run(Offer.objects.filter(offerer_did=user.did).first()).id

    from app.config import get_settings
    from app.offers import offer_ref

    offer = asyncio.run(Offer.objects.get(id=offer_id))
    ref = offer_ref(offer, get_settings())

    with patch("app.routes.offers._safe_profile", new=AsyncMock(side_effect=lambda h: {"handle": h, "avatar": None})):
        resp = client.get(f"/o/{ref}")
    assert resp.status_code == 200
    assert "pub-alice" in resp.text
    assert "bestätigen" in resp.text.lower()


def test_confirm_route_success(client, make_user):
    import asyncio
    from datetime import timedelta

    from app.models import Offer, utcnow

    alice = asyncio.run(make_user("did:plc:ca-alice", "ca-alice.test"))
    bob = asyncio.run(make_user("did:plc:ca-bob", "ca-bob.test"))
    offer = asyncio.run(
        Offer.objects.create(
            offerer_did=alice.did,
            offerer_handle=alice.handle,
            target_did=bob.did,
            target_handle=bob.handle,
            status="pending",
            expires_at=utcnow() + timedelta(days=14),
        )
    )
    _override_user(app, bob)
    try:
        with patch("app.routes.offers.confirm_swap", new=AsyncMock(return_value=ConfirmResult(ConfirmOutcome.SUCCESS, offer, ""))):
            resp = client.post(f"/offers/{offer.id}/confirm", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "folgt euch jetzt" in resp.text
    finally:
        _clear_overrides(app)


def test_cancel_route(client, make_user):
    import asyncio
    from datetime import timedelta

    from app.models import Offer, utcnow

    alice = asyncio.run(make_user("did:plc:c-alice", "c-alice.test"))
    bob = asyncio.run(make_user("did:plc:c-bob", "c-bob.test"))
    offer = asyncio.run(
        Offer.objects.create(
            offerer_did=alice.did,
            offerer_handle=alice.handle,
            target_did=bob.did,
            target_handle=bob.handle,
            status="pending",
            expires_at=utcnow() + timedelta(days=14),
        )
    )
    _override_user(app, alice)
    try:
        resp = client.post(f"/offers/{offer.id}/cancel", headers={"HX-Request": "true"})
        assert resp.status_code == 200
    finally:
        _clear_overrides(app)

    from app.models import Offer as O

    refreshed = asyncio.run(O.objects.get(id=offer.id))
    assert refreshed.status == "cancelled"


def await_offers(offerer_did: str):
    import asyncio

    from app.models import Offer

    return_asyncio = asyncio.run(Offer.objects.filter(offerer_did=offerer_did).all())
    return return_asyncio