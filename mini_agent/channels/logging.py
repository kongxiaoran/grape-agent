"""Standardized channel event logging."""

from __future__ import annotations

from typing import Any

_channel_log_quiet = False


def set_channel_log_quiet(quiet: bool) -> None:
    """Enable or disable channel event printing globally."""
    global _channel_log_quiet
    _channel_log_quiet = quiet


def log_channel_event(channel: str, event: str, **fields: Any) -> None:
    """Print normalized channel event logs.

    Format:
        [ChannelEvent] channel=<id> event=<name> key=value ...
    """
    parts = [f"[ChannelEvent] channel={channel}", f"event={event}"]
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value).replace("\n", "\\n")
        if len(text) > 300:
            text = text[:297] + "..."
        parts.append(f"{key}={text}")
    if not _channel_log_quiet:
        print(" ".join(parts))
