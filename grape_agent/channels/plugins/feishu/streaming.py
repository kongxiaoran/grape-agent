"""Feishu progressive chunk streaming helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


class FeishuChunkStreamer:
    """Emit text chunks progressively with optional interval."""

    def __init__(self, interval_ms: int = 0):
        self._interval_sec = max(0.0, float(interval_ms) / 1000.0)

    async def emit(self, chunks: list[str], callback: Callable[[int, int, str], Awaitable[None]]) -> None:
        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            await callback(index, total, chunk)
            if self._interval_sec > 0 and index < total:
                await asyncio.sleep(self._interval_sec)
