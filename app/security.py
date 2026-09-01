"""Rate limiting and request helpers."""

import time

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        hits = [t for t in self._hits.get(key, []) if now - t < window_seconds]
        if len(hits) >= limit:
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


_limiter = RateLimiter()


def rate_limit(limit: int, window_seconds: float = 60.0):
    async def dependency(request: Request) -> None:
        key = f"{request.client.host if request.client else 'unknown'}:{request.url.path}"
        if not _limiter.check(key, limit, window_seconds):
            raise HTTPException(status_code=429, detail="Zu viele Anfragen, bitte kurz warten.")

    return dependency


def is_safe_local_path(path: str) -> bool:
    return path.startswith("/") and not path.startswith("//") and "\\" not in path