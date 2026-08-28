"""Authenticated PDS actions executed on behalf of a user (OAuth grant)."""

import time
from datetime import UTC, datetime

import jwt as pyjwt

from ..atproto_service import get_client_key
from ..oauth import atproto_oauth as oauth
from . import client as public_client

CHAT_PROXY = "did:web:api.bsky.chat#bsky_chat"


class BlueskyActionError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ChatUnavailableError(BlueskyActionError):
    pass


def _access_token_is_fresh(access_token: str) -> bool:
    if not access_token:
        return False
    try:
        payload = pyjwt.decode(access_token, options={"verify_signature": False})
    except Exception:
        return False
    exp = payload.get("exp")
    if not exp:
        return False
    return (exp - time.time()) > 60


async def ensure_access_token(user: dict, settings, persist_cb=None) -> None:
    """Refresh the access token when missing or about to expire.

    Mutates ``user`` in place and invokes ``persist_cb`` when the refresh
    token (and DPoP auth-server nonce) were rotated.
    """
    if _access_token_is_fresh(user.get("access_token", "")):
        return
    client_secret_jwk = get_client_key(settings)
    client_id = user.get("client_id") or settings.client_id_url
    tokens, nonce = await oauth.refresh_token_request(
        user, client_id, client_secret_jwk
    )
    updates = {
        "access_token": tokens.get("access_token", ""),
        "refresh_token": tokens.get("refresh_token", user.get("refresh_token", "")),
        "scope": tokens.get("scope", user.get("scope", "")),
        "dpop_authserver_nonce": nonce,
    }
    user.update(updates)
    if persist_cb:
        persist_cb(updates)


async def authed_post(
    user: dict,
    path: str,
    body: dict | None = None,
    headers: dict | None = None,
    settings=None,
    persist_cb=None,
    pds_url: str | None = None,
):
    """POST an XRPC method to the user's PDS with DPoP-bound auth (auto-refresh)."""
    await ensure_access_token(user, settings, persist_cb)
    base = pds_url or user["pds_url"]
    url = f"{base}/xrpc/{path}"
    resp = await oauth.pds_authed_req(
        url, user, body=body, headers=headers, persist_cb=persist_cb
    )
    if resp.status_code not in (200, 201):
        raise BlueskyActionError(
            f"{path} HTTP {resp.status_code}: {resp.text}", resp.status_code, resp.text
        )
    return resp.json()


async def follow_user(user: dict, target_did: str, settings, persist_cb=None) -> bool:
    """Create a follow record (idempotent) on behalf of ``user``."""
    if await public_client.does_follow(user["did"], target_did):
        return True
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    body = {
        "repo": user["did"],
        "collection": "app.bsky.graph.follow",
        "record": {
            "$type": "app.bsky.graph.follow",
            "subject": target_did,
            "createdAt": now,
        },
    }
    await authed_post(
        user, "com.atproto.repo.createRecord", body, settings=settings, persist_cb=persist_cb
    )
    return True


async def send_dm(user: dict, target_did: str, text: str, settings, persist_cb=None) -> None:
    """Send a direct message to ``target_did`` via the central chat service."""
    if "chat.bsky" not in (user.get("scope") or ""):
        raise ChatUnavailableError(
            "OAuth-Grant hat keinen DM-Zugriff (transition:chat.bsky fehlt)"
        )
    proxy_headers = {"atproto-proxy": CHAT_PROXY}
    try:
        convo = await authed_post(
            user,
            "chat.bsky.convo.getConvoForMembers",
            {"members": [target_did]},
            headers=proxy_headers,
            settings=settings,
            persist_cb=persist_cb,
        )
    except BlueskyActionError as exc:
        raise ChatUnavailableError("Convo konnte nicht erstellt werden") from exc
    convo_id = convo["convo"]["id"]
    await authed_post(
        user,
        "chat.bsky.convo.sendMessage",
        {"convoId": convo_id, "message": {"text": text}},
        headers=proxy_headers,
        settings=settings,
        persist_cb=persist_cb,
    )