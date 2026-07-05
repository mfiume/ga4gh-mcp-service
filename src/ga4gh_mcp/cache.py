"""A tiny async-safe TTL cache used for registry responses."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


class TTLCache:
    """In-memory TTL cache with single-flight coalescing per key."""

    def __init__(self, ttl: float = 300.0) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    def _fresh(self, key: str) -> bool:
        entry = self._store.get(key)
        return entry is not None and (time.monotonic() - entry[0]) < self._ttl

    def peek(self, key: str) -> Any | None:
        entry = self._store.get(key)
        return entry[1] if entry else None

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: str | None = None) -> None:
        if key is None:
            self._store.clear()
        else:
            self._store.pop(key, None)

    async def get_or_set(self, key: str, factory: Callable[[], Awaitable[Any]]) -> Any:
        """Return a cached value or compute it via ``factory`` (coalesced per key)."""
        if self._fresh(key):
            return self._store[key][1]
        async with self._guard:
            lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Re-check after acquiring the per-key lock.
            if self._fresh(key):
                return self._store[key][1]
            value = await factory()
            self.set(key, value)
            return value
