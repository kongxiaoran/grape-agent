"""Feishu policy helpers."""

from __future__ import annotations

from mini_agent.config import FeishuPolicyConfig
from mini_agent.feishu.types import FeishuChatType, FeishuIncomingMessage


def resolve_session_scope_id(inbound: FeishuIncomingMessage, policy: FeishuPolicyConfig) -> str:
    """Resolve session scope key for incoming message."""
    if inbound.chat_type != FeishuChatType.GROUP:
        return inbound.chat_id

    scope = policy.group_session_scope
    if scope == "group_sender":
        sender = inbound.sender_open_id or inbound.sender_user_id or "unknown"
        return f"{inbound.chat_id}:{sender}"
    if scope == "topic":
        topic = inbound.thread_id or inbound.root_id
        if topic:
            return f"{inbound.chat_id}:topic:{topic}"
    return inbound.chat_id
