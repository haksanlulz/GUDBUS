from __future__ import annotations

from time import monotonic
from typing import Any


class TTLCache:
    def __init__(self, ttl: float = 10.0, max_size: int = 1000) -> None:
        self._store: dict[tuple, tuple[float, Any]] = {}
        self._ttl = ttl
        self._max_size = max_size

    def _prune(self) -> None:
        now = monotonic()
        self._store = {
            k: v for k, v in self._store.items()
            if now - v[0] <= self._ttl
        }

    def get(self, key: tuple) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: tuple, value: Any) -> None:
        if len(self._store) >= self._max_size:
            self._prune()
        self._store[key] = (monotonic(), value)

    def invalidate(self, key: tuple) -> None:
        self._store.pop(key, None)

    def invalidate_user(self, user_id: int) -> None:
        to_remove = [k for k in self._store if k[0] == user_id]
        for k in to_remove:
            del self._store[k]

    def clear(self) -> None:
        self._store.clear()
