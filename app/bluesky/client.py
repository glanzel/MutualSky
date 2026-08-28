"""Public (unauthenticated) AppView calls via public.api.bsky.app."""

from ..oauth.atproto_security import safe_get

APPVIEW_BASE = "https://public.api.bsky.app"


class PublicBskyError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


async def _get(path: str, params: dict | None = None) -> dict:
    resp = await safe_get(f"{APPVIEW_BASE}/xrpc/{path}", params=params)
    if resp.status_code != 200:
        raise PublicBskyError(f"{path} HTTP {resp.status_code}", resp.status_code, resp.text)
    return resp.json()


async def resolve_handle(handle: str) -> str:
    data = await _get("com.atproto.identity.resolveHandle", {"handle": handle})
    return data["did"]


async def search_actors(q: str, limit: int = 10) -> list[dict]:
    data = await _get("app.bsky.actor.searchActors", {"q": q, "limit": limit})
    return data.get("actors", [])


async def get_profile(actor: str) -> dict:
    return await _get("app.bsky.actor.getProfile", {"actor": actor})


async def does_follow(actor: str, subject: str) -> bool:
    """Returns True if ``actor`` (DID) follows ``subject`` (DID).

    Uses the public AppView relationship data; no authentication needed.
    """
    resp = await safe_get(
        f"{APPVIEW_BASE}/xrpc/app.bsky.graph.getRelationships",
        params={"actor": actor, "subject": subject},
    )
    if resp.status_code != 200:
        raise PublicBskyError(
            "getRelationships HTTP " + str(resp.status_code), resp.status_code, resp.text
        )
    relationships = resp.json().get("relationships", [])
    for rel in relationships:
        if rel.get("did") == subject:
            return bool(rel.get("following"))
    return False