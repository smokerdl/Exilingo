from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Optional


@dataclass(slots=True)
class CacheEntry:
    translated_text: str
    created_at: float
    last_used_at: float


class TranslationCache:
    """In-memory TTL/LRU cache for successful provider translations."""

    DEFAULT_MAX_ENTRIES = 1000
    DEFAULT_TTL_SECONDS = 300.0

    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ):
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._entries: OrderedDict[tuple[str, str, str, str], CacheEntry] = OrderedDict()
        self._lock = RLock()

    def _expire(self, now: float) -> None:
        if not self._entries or self.ttl_seconds <= 0:
            return

        expired = [
            key
            for key, entry in self._entries.items()
            if now - entry.created_at >= self.ttl_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)

    def get(
        self,
        provider_id: str,
        source_language: str,
        target_language: str,
        text: str,
    ) -> Optional[str]:
        now = time.monotonic()
        key = (provider_id, source_language, target_language, text)

        with self._lock:
            self._expire(now)
            entry = self._entries.get(key)
            if entry is None:
                return None

            entry.last_used_at = now
            self._entries.move_to_end(key)
            return entry.translated_text

    def put(
        self,
        provider_id: str,
        source_language: str,
        target_language: str,
        text: str,
        translated_text: str,
    ) -> None:
        now = time.monotonic()
        key = (provider_id, source_language, target_language, text)

        with self._lock:
            self._expire(now)
            self._entries[key] = CacheEntry(
                translated_text=translated_text,
                created_at=now,
                last_used_at=now,
            )
            self._entries.move_to_end(key)

            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def size(self) -> int:
        now = time.monotonic()
        with self._lock:
            self._expire(now)
            return len(self._entries)
