"""Public (unauthenticated) AppView calls via public.api.bsky.app."""

import asyncio

from ..oauth.atproto_security import safe_get

APPVIEW_BASE = "https://public.api.bsky.app"


class PublicBskyError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


async def _get(path: str, params: dict | None = None) -> dict:
    try:
        resp = await safe_get(f"{APPVIEW_BASE}/xrpc/{path}", params=params)
    except Exception as exc:
        raise PublicBskyError(f"{path} Fehler: {exc}") from exc
    if resp.status_code != 200:
        raise PublicBskyError(f"{path} HTTP {resp.status_code}", resp.status_code, resp.text)
    return resp.json()


async def resolve_handle(handle: str) -> str:
    data = await _get("com.atproto.identity.resolveHandle", {"handle": handle})
    return data["did"]


async def search_actors(q: str, limit: int = 25, cursor: str | None = None) -> tuple[list[dict], str | None]:
    params: dict = {"q": q, "limit": limit}
    if cursor:
        params["cursor"] = cursor
    data = await _get("app.bsky.actor.searchActors", params)
    return data.get("actors", []), data.get("cursor")


async def get_profile(actor: str) -> dict:
    return await _get("app.bsky.actor.getProfile", {"actor": actor})


async def get_author_feed(actor: str, limit: int = 10) -> list[dict]:
    data = await _get("app.bsky.feed.getAuthorFeed", {"actor": actor, "limit": limit})
    return data.get("feed", [])


async def get_chat_allow_incoming(actor_did: str) -> str | None:
    """Return the account's DM policy: ``all``, ``following``, ``none`` or None.

    Read from the public profile's ``associated.chat`` field. Accounts without a
    chat declaration effectively behave like ``following`` in the official app.
    """
    profile = await get_profile(actor_did)
    return profile.get("associated", {}).get("chat", {}).get("allowIncoming")


async def get_profiles(actors: list[dict]) -> list[dict]:
    """Enrich actor cards with follower/follows/posts counts and last activity.

    ``searchActors`` returns profiles without counts, so each result is
    enriched via its detailed profile (fetched concurrently). Falls back to the
    search result if a profile fetch fails or times out.
    """
    sem = asyncio.Semaphore(6)

    async def enrich(actor: dict) -> dict:
        async with sem:
            try:
                profile = await get_profile(actor.get("did") or actor.get("handle"))
                return {**actor, **profile}
            except PublicBskyError:
                return actor

    return await asyncio.gather(*(enrich(a) for a in actors))


async def enrich_posts_authors(posts: list[dict], max_followers: int | None = None) -> list[dict]:
    """Merge follower/follows/posts counts and last activity into each post's author.

    Post search results only carry did + handle for authors, so unique authors
    are enriched via ``getProfile`` (fetched concurrently). Posts whose author
    exceeds ``max_followers`` (when given) are dropped.
    """
    if not posts:
        return posts
    dids = sorted({p["author"]["did"] for p in posts if "author" in p and p["author"].get("did")})
    profiles = await get_profiles([{"did": d} for d in dids])
    by_did = {p.get("did"): p for p in profiles}
    for post in posts:
        author = post.get("author") or {}
        profile = by_did.get(author.get("did"))
        if profile:
            author = {**author, **profile}
            post["author"] = author
    if max_followers:
        posts = [p for p in posts if ((p.get("author") or {}).get("followersCount") or 0) <= max_followers]
    return posts


async def search_profiles(
    q: str,
    limit: int = 25,
    max_followers: int | None = None,
    cursor: str | None = None,
    max_pages: int = 5,
) -> tuple[list[dict], str | None]:
    """Search profiles, optionally keeping only those with ``max_followers`` or fewer.

    Bluesky's ``searchActors`` has no follower filter, and follower counts only
    exist in the detailed profile. So when a filter is set we fetch pages, enrich
    them and accumulate matches until ``limit`` matches are found (or the pages /
    cursor run out). The returned cursor points at the last consumed page so the
    "load more" flow can continue seamlessly.
    """
    collected: list[dict] = []
    cursor_out = cursor
    for _ in range(max_pages):
        batch, cursor_out = await search_actors(q, limit=limit, cursor=cursor_out)
        if not batch:
            break
        enriched = await get_profiles(batch)
        if max_followers:
            enriched = [a for a in enriched if (a.get("followersCount") or 0) <= max_followers]
        collected.extend(enriched)
        if len(collected) >= limit or not cursor_out:
            break
    return collected[:limit], cursor_out


async def does_follow(actor: str, subject: str) -> bool:
    """Returns True if ``actor`` (DID) follows ``subject`` (DID).

    Uses the public AppView relationship data; no authentication needed.
    """
    try:
        resp = await safe_get(
            f"{APPVIEW_BASE}/xrpc/app.bsky.graph.getRelationships",
            params={"actor": actor, "subject": subject},
        )
    except Exception as exc:
        raise PublicBskyError(f"getRelationships Fehler: {exc}") from exc
    if resp.status_code != 200:
        raise PublicBskyError(
            "getRelationships HTTP " + str(resp.status_code), resp.status_code, resp.text
        )
    relationships = resp.json().get("relationships", [])
    for rel in relationships:
        if rel.get("did") == subject:
            return bool(rel.get("following"))
    return False