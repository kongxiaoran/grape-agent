"""Gateway health handler."""

from __future__ import annotations

from .utils import uptime_seconds


def handle_health(_params: dict, ctx, _conn) -> dict:
    return {
        "service": ctx.app_name,
        "status": "ok",
        "uptime_sec": uptime_seconds(ctx.started_at),
    }

