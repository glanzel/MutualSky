"""In-memory OAuth authorization-request state store (single worker)."""

import time
from threading import Lock

_MAX_AGE = 60 * 15


class OAuthStateStore:
    def __init__(self):
        self._data: dict[str, dict] = {}
        self._lock = Lock()

    def put(self, state: str, payload: dict) -> None:
        with self._lock:
            self._purge_locked()
            self._data[state] = {"payload": payload, "created": time.monotonic()}

    def pop(self, state: str) -> dict | None:
        with self._lock:
            entry = self._data.pop(state, None)
        if entry is None:
            return None
        if time.monotonic() - entry["created"] > _MAX_AGE:
            return None
        return entry["payload"]

    def _purge_locked(self) -> None:
        cutoff = time.monotonic() - _MAX_AGE
        for state, entry in list(self._data.items()):
            if entry["created"] < cutoff:
                del self._data[state]


oauth_state_store = OAuthStateStore()