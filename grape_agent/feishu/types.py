"""Type definitions for Feishu long-connection integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FeishuChatType(str, Enum):
    """Feishu chat types."""

    P2P = "p2p"
    GROUP = "group"
    PRIVATE = "private"


class FeishuMessageType(str, Enum):
    """Feishu message content types."""

    TEXT = "text"
    POST = "post"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"
    STICKER = "sticker"
    INTERACTIVE = "interactive"


@dataclass
class FeishuMention:
    """Feishu @ mention metadata."""

    key: str
    name: str
    open_id: str | None = None
    user_id: str | None = None
    union_id: str | None = None


@dataclass
class FeishuIncomingMessage:
    """Normalized inbound Feishu message payload."""

    message_id: str
    chat_id: str
    chat_type: FeishuChatType
    message_type: FeishuMessageType
    content: str
    raw_content: str
    sender_open_id: str
    sender_user_id: str
    sender_name: str | None = None
    create_time_ms: int | None = None
    root_id: str | None = None
    parent_id: str | None = None
    thread_id: str | None = None
    mentions: list[FeishuMention] = field(default_factory=list)
    mentioned_bot: bool = False


@dataclass
class FeishuSendResult:
    """Send/reply API result wrapper."""

    success: bool
    message_id: str | None = None
    error: str | None = None
    raw: dict[str, Any] | None = None
