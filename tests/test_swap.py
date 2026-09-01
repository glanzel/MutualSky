from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.bluesky.swap import ConfirmOutcome, confirm_swap
from app.models import STATUS_COMPLETED, STATUS_EXPIRED, STATUS_PENDING, Offer, utcnow


def _offer(**overrides) -> Offer:
    kwargs = {
        "offerer_did": "did:plc:alice",
        "offerer_handle": "alice.test",
        "target_did": "did:plc:bob",
        "target_handle": "bob.test",
        "status": STATUS_PENDING,
        "expires_at": utcnow() + timedelta(days=14),
    }
    kwargs.update(overrides)
    return Offer(**kwargs)


async def _seed_users(make_user):
    alice = await make_user("did:plc:alice", "alice.test")
    bob = await make_user("did:plc:bob", "bob.test")
    return alice, bob


@pytest.mark.asyncio
async def test_confirm_success(make_user, settings):
    _alice, bob = await _seed_users(make_user)
    offer = _offer()
    await offer.save()

    with patch("app.bluesky.actions.follow_user", new=AsyncMock(return_value=True)) as mock:
        result = await confirm_swap(offer.id, bob.did, settings)

    assert result.outcome == ConfirmOutcome.SUCCESS
    assert mock.await_count == 2

    refreshed = await Offer.objects.get(id=offer.id)
    assert refreshed.status == STATUS_COMPLETED
    assert refreshed.completed_at is not None


@pytest.mark.asyncio
async def test_confirm_not_authorized(make_user, settings):
    _alice, _bob = await _seed_users(make_user)
    offer = _offer()
    await offer.save()
    mallory = await make_user("did:plc:mallory", "mallory.test")

    result = await confirm_swap(offer.id, mallory.did, settings)
    assert result.outcome == ConfirmOutcome.NOT_AUTHORIZED


@pytest.mark.asyncio
async def test_confirm_not_found(settings):
    result = await confirm_swap(999999, "did:plc:bob", settings)
    assert result.outcome == ConfirmOutcome.NOT_FOUND


@pytest.mark.asyncio
async def test_confirm_expired(make_user, settings):
    _alice, bob = await _seed_users(make_user)
    offer = _offer(expires_at=utcnow() - timedelta(seconds=1))
    await offer.save()

    result = await confirm_swap(offer.id, bob.did, settings)
    assert result.outcome == ConfirmOutcome.EXPIRED

    refreshed = await Offer.objects.get(id=offer.id)
    assert refreshed.status == STATUS_EXPIRED


@pytest.mark.asyncio
async def test_confirm_target_follow_failed(make_user, settings):
    _alice, bob = await _seed_users(make_user)
    offer = _offer()
    await offer.save()

    async def fake_follow(user, target_did, settings, persist_cb=None):
        if user["did"] == bob.did:
            raise RuntimeError("PDS 500")

    with patch("app.bluesky.actions.follow_user", new=fake_follow):
        result = await confirm_swap(offer.id, bob.did, settings)

    assert result.outcome == ConfirmOutcome.TARGET_FOLLOW_FAILED

    refreshed = await Offer.objects.get(id=offer.id)
    assert refreshed.status == STATUS_PENDING
    assert "Dein Follow" in (refreshed.follow_error or "")


@pytest.mark.asyncio
async def test_confirm_offerer_follow_failed(make_user, settings):
    alice, bob = await _seed_users(make_user)
    offer = _offer()
    await offer.save()

    async def fake_follow(user, target_did, settings, persist_cb=None):
        if user["did"] == alice.did:
            raise RuntimeError("PDS 500")

    with patch("app.bluesky.actions.follow_user", new=fake_follow):
        result = await confirm_swap(offer.id, bob.did, settings)

    assert result.outcome == ConfirmOutcome.OFFERER_FOLLOW_FAILED

    refreshed = await Offer.objects.get(id=offer.id)
    assert refreshed.status == STATUS_PENDING


@pytest.mark.asyncio
async def test_confirm_double_confirm_guard(make_user, settings):
    _alice, bob = await _seed_users(make_user)
    offer = _offer()
    await offer.save()

    async def fake_follow(user, target_did, settings, persist_cb=None):
        return True

    with patch("app.bluesky.actions.follow_user", new=fake_follow):
        first = await confirm_swap(offer.id, bob.did, settings)
        second = await confirm_swap(offer.id, bob.did, settings)

    assert first.outcome == ConfirmOutcome.SUCCESS
    assert second.outcome == ConfirmOutcome.ALREADY_FINISHED


@pytest.mark.asyncio
async def test_confirm_offerer_unavailable(make_user, settings):
    bob = await make_user("did:plc:bob", "bob.test")
    offer = _offer(offerer_did="did:plc:ghost", offerer_handle="ghost.test")  # no User row
    await offer.save()

    result = await confirm_swap(offer.id, bob.did, settings)
    assert result.outcome == ConfirmOutcome.OFFERER_UNAVAILABLE


@pytest.mark.asyncio
async def test_create_offer_duplicate_pending(make_user, settings):
    alice, _bob = await _seed_users(make_user)
    settings.offer_cooldown_seconds = 0
    await Offer.objects.filter(offerer_did=alice.did).delete()
    from app.offers import OfferError, create_offer

    first = await create_offer(alice, "did:plc:bob", "bob.test", settings)
    assert first is not None
    with pytest.raises(OfferError):
        await create_offer(alice, "did:plc:bob", "bob.test", settings)


@pytest.mark.asyncio
async def test_create_offer_self_denied(make_user, settings):
    alice, _bob = await _seed_users(make_user)
    settings.offer_cooldown_seconds = 0
    from app.offers import OfferError, create_offer

    with pytest.raises(OfferError):
        await create_offer(alice, alice.did, alice.handle, settings)