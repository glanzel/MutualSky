"""Authenticated PDS actions executed on behalf of a user (OAuth grant)."""

import time
from datetime import UTC, datetime

import jwt as pyjwt

from ..atproto_service import get_client_key
from ..oauth import atproto_oauth as oauth
from . import client as public_client

CHAT_PROXY = "did:web:api.bsky.chat#bsky_chat"
APPVIEW_PROXY = "did:web:api.bsky.app#bsky_appview"


class BlueskyActionError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ChatUnavailableError(BlueskyActionError):
    pass


class AuthSessionError(BlueskyActionError):
    """The stored OAuth session is no longer valid (token refresh failed)."""


def _friendly_chat_error(exc: BlueskyActionError) -> str:
    import json as _json

    try:
        err = _json.loads(exc.body or "")
        code = err.get("error", "")
    except Exception:
        code = ""
    return {
        "MessagesDisabled": "Der Empfänger hat eingehende Nachrichten deaktiviert.",
        "BlockedActor": "Dieser Account hat dich blockiert.",
        "BlockedSubject": "Du hast diesen Account blockiert.",
        "RecipientNotFound": "Empfänger nicht gefunden.",
        "NotFollowedBySender": "Du folgst dem Empfänger nicht.",
    }.get(code, str(exc))


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
    try:
        tokens, nonce = await oauth.refresh_token_request(
            user, client_id, client_secret_jwk
        )
    except Exception as exc:
        raise AuthSessionError(
            "Deine Anmeldung ist abgelaufen – bitte melde dich erneut an."
        ) from exc
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
    if await _already_follows(user, target_did):
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
    try:
        await authed_post(
            user, "com.atproto.repo.createRecord", body, settings=settings, persist_cb=persist_cb
        )
    except BlueskyActionError as exc:
        # 409 Conflict / 400 Duplicate means they already follow – fine.
        if exc.status_code in (400, 409) and "Duplicate" in (exc.body or ""):
            return True
        raise
    return True


async def _already_follows(user: dict, target_did: str) -> bool:
    try:
        return await public_client.does_follow(user["did"], target_did)
    except public_client.PublicBskyError:
        # Follow status unknown (public AppView down/timed out): assume not yet
        # following so the follow record is attempted anyway.
        return False


async def authed_get(
    user: dict,
    path: str,
    params: dict | None = None,
    headers: dict | None = None,
    settings=None,
    persist_cb=None,
    pds_url: str | None = None,
):
    """GET an XRPC method from the user's PDS with DPoP-bound auth (auto-refresh)."""
    await ensure_access_token(user, settings, persist_cb)
    base = pds_url or user["pds_url"]
    url = f"{base}/xrpc/{path}"
    resp = await oauth.pds_authed_req(
        url, user, method="GET", params=params, headers=headers, persist_cb=persist_cb
    )
    if resp.status_code != 200:
        raise BlueskyActionError(
            f"{path} HTTP {resp.status_code}: {resp.text}", resp.status_code, resp.text
        )
    return resp.json()


async def search_posts(
    user: dict,
    q: str,
    settings,
    persist_cb=None,
    limit: int = 25,
    cursor: str | None = None,
) -> tuple[list[dict], str | None]:
    """Search posts via the AppView (newest first), on behalf of the signed-in user.

    Uses the account's PDS with the AppView service proxy; returns post objects
    with author info plus the next-page cursor.
    """
    params: dict = {"q": q, "sort": "latest", "limit": limit}
    if cursor:
        params["cursor"] = cursor
    data = await authed_get(
        user,
        "app.bsky.feed.searchPosts",
        params=params,
        headers={"atproto-proxy": APPVIEW_PROXY},
        settings=settings,
        persist_cb=persist_cb,
    )
    return data.get("posts", []), data.get("cursor")


async def reply_to_offer_post(
    user: dict,
    target_did: str,
    text: str,
    facets: list[dict] | None,
    settings,
    persist_cb=None,
    rkey: str | None = None,
) -> None:
    """Publicly reply to the target's latest post with the offer notice.

    Pass a deterministic ``rkey`` so the reply can be deleted later (e.g. when
    the offer is withdrawn).
    """
    feed = await public_client.get_author_feed(target_did, limit=10)
    top_level = next(
        (
            it
            for it in feed
            if it["post"]["record"].get("$type") == "app.bsky.feed.post"
            and "reply" not in it["post"]["record"]
        ),
        None,
    )
    selected = top_level or next(
        (it for it in feed if it["post"]["record"].get("$type") == "app.bsky.feed.post"), None
    )
    if selected is None:
        raise BlueskyActionError("Kein Post gefunden, auf den öffentlich geantwortet werden kann.")
    post = selected["post"]
    record = post["record"]
    if "reply" in record:
        root = {"uri": record["reply"]["root"]["uri"], "cid": record["reply"]["root"]["cid"]}
    else:
        root = {"uri": post["uri"], "cid": post["cid"]}
    parent = {"uri": post["uri"], "cid": post["cid"]}

    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    body = {
        "repo": user["did"],
        "collection": "app.bsky.feed.post",
        "record": {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": now,
            "reply": {"root": root, "parent": parent},
            "langs": ["de"],
        },
    }
    if facets:
        body["record"]["facets"] = facets
    if rkey:
        body["rkey"] = rkey
    await authed_post(user, "com.atproto.repo.createRecord", body, settings=settings, persist_cb=persist_cb)


async def delete_record(
    user: dict, collection: str, rkey: str, settings, persist_cb=None
) -> None:
    """Delete a repo record of the user (e.g. a public reply post)."""
    body = {"repo": user["did"], "collection": collection, "rkey": rkey}
    await authed_post(
        user, "com.atproto.repo.deleteRecord", body, settings=settings, persist_cb=persist_cb
    )


async def send_dm(
    user: dict,
    target_did: str,
    text: str,
    settings,
    persist_cb=None,
    facets: list[dict] | None = None,
) -> None:
    """Send a direct message to ``target_did`` via the central chat service.

    Chat calls go through the user's own PDS, which forwards to the central
    chat service via the ``atproto-proxy`` header. ``getConvoForMembers`` is a
    GET query (members as params), ``sendMessage`` a POST procedure.
    """
    if "chat.bsky" not in (user.get("scope") or ""):
        raise ChatUnavailableError(
            "OAuth-Grant hat keinen DM-Zugriff (transition:chat.bsky fehlt)"
        )
    proxy_headers = {"atproto-proxy": CHAT_PROXY}
    try:
        convo = await authed_get(
            user,
            "chat.bsky.convo.getConvoForMembers",
            params={"members": [target_did]},
            headers=proxy_headers,
            settings=settings,
            persist_cb=persist_cb,
        )
    except BlueskyActionError as exc:
        raise ChatUnavailableError(
            f"Convo konnte nicht erstellt werden: {_friendly_chat_error(exc)}"
        ) from exc
    convo_id = convo["convo"]["id"]
    message: dict = {"text": text}
    if facets:
        message["facets"] = facets
    await authed_post(
        user,
        "chat.bsky.convo.sendMessage",
        {"convoId": convo_id, "message": message},
        headers=proxy_headers,
        settings=settings,
        persist_cb=persist_cb,
    )