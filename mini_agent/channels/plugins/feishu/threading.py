"""Feishu reply threading helpers."""

from __future__ import annotations

from mini_agent.feishu.types import FeishuIncomingMessage


def resolve_reply_in_thread(inbound: FeishuIncomingMessage, enabled: bool) -> bool:
    """Resolve whether outbound reply should stay in thread/topic."""
    if not enabled:
        return False
    return bool(inbound.thread_id or inbound.root_id)
