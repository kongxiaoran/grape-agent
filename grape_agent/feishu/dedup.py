"""Persistent dedup cache for inbound Feishu message IDs."""

from __future__ import annotations

import json
import time
from pathlib import Path


class FeishuMessageDedup:
    """Simple persistent deduplication with TTL pruning."""

    def __init__(
        self,
        state_file: str | Path,
        ttl_seconds: int = 24 * 60 * 60,
        max_entries: int = 10_000,
    ):
        self.state_file = Path(state_file)
        self.ttl_seconds = max(60, ttl_seconds)
        self.max_entries = max(1000, max_entries)
        self._cache: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(key, str) and isinstance(value, (int, float)):
                        self._cache[key] = float(value)
        except Exception:
            self._cache = {}

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")
        except Exception:
            # Dedup persistence is best-effort only.
            pass

    def _prune(self, now: float) -> None:
        deadline = now - self.ttl_seconds
        expired = [key for key, ts in self._cache.items() if ts < deadline]
        for key in expired:
            self._cache.pop(key, None)

        if len(self._cache) > self.max_entries:
            # Keep most recent entries only.
            for key, _ in sorted(self._cache.items(), key=lambda item: item[1])[: len(self._cache) - self.max_entries]:
                self._cache.pop(key, None)

    def seen_or_record(self, dedup_key: str) -> bool:
        """Return True if message is already seen; otherwise record and return False."""
        key = dedup_key.strip()
        if not key:
            return False

        now = time.time()
        self._prune(now)

        if key in self._cache:
            return True

        self._cache[key] = now
        self._save()
        return False
