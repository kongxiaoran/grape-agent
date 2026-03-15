"""Session key helpers for multi-agent routing."""

from __future__ import annotations


def build_session_key(agent_id: str, channel: str, chat_id: str) -> str:
    """Build canonical session key.

    Format: agent:{agent_id}:{channel}:{chat_id}
    """
    a = str(agent_id).strip() or "main"
    c = str(channel).strip() or "unknown"
    s = str(chat_id).strip() or "default"
    return f"agent:{a}:{c}:{s}"


def parse_session_key(key: str) -> tuple[str, str, str]:
    """Parse canonical session key and return (agent_id, channel, chat_id)."""
    parts = str(key).split(":", 3)
    if len(parts) != 4 or parts[0] != "agent":
        raise ValueError(f"invalid session key format: {key!r}")
    return parts[1], parts[2], parts[3]
