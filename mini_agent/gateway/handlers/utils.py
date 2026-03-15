"""Shared handler helpers."""

from __future__ import annotations

from datetime import datetime


def uptime_seconds(started_at: datetime) -> int:
    return max(0, int((datetime.now() - started_at).total_seconds()))

