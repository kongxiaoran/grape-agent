"""Routing rule models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ChatType = Literal["direct", "group"]


@dataclass(slots=True, frozen=True)
class RoutingInput:
    """Runtime input used for route selection."""

    channel: str
    chat_id: str
    chat_type: ChatType
    account_id: str | None = None


@dataclass(slots=True, frozen=True)
class RoutingRule:
    """One route match rule."""

    agent_id: str
    channel: str | None = None
    account_id: str | None = None
    chat_type: ChatType | None = None
    chat_id: str | None = None

    def matches(self, item: RoutingInput) -> bool:
        if self.channel and self.channel != item.channel:
            return False
        if self.account_id and self.account_id != item.account_id:
            return False
        if self.chat_type and self.chat_type != item.chat_type:
            return False
        if self.chat_id and self.chat_id != item.chat_id:
            return False
        return True


@dataclass(slots=True, frozen=True)
class RoutingResult:
    """Resolved route result."""

    agent_id: str
    channel: str
    chat_id: str
    session_key: str
    matched_by: str
