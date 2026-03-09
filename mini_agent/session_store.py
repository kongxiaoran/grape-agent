"""Channel-aware Agent session store."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from mini_agent.agent import Agent


@dataclass
class AgentSession:
    """Container for one logical session with serialized execution."""

    key: str
    channel: str
    session_id: str
    agent: Agent
    lock: asyncio.Lock


class AgentSessionStore:
    """Unified `channel:session_id` session management."""

    def __init__(self):
        self._sessions: dict[str, AgentSession] = {}
        self._guard = asyncio.Lock()

    @staticmethod
    def make_key(channel: str, session_id: str) -> str:
        return f"{channel}:{session_id}"

    async def get_or_create(self, channel: str, session_id: str, factory: Callable[[], Agent]) -> AgentSession:
        key = self.make_key(channel, session_id)
        async with self._guard:
            existing = self._sessions.get(key)
            if existing is not None:
                return existing

            created = AgentSession(
                key=key,
                channel=channel,
                session_id=session_id,
                agent=factory(),
                lock=asyncio.Lock(),
            )
            self._sessions[key] = created
            return created

    def get(self, channel: str, session_id: str) -> AgentSession | None:
        return self._sessions.get(self.make_key(channel, session_id))

    def pop(self, channel: str, session_id: str) -> AgentSession | None:
        return self._sessions.pop(self.make_key(channel, session_id), None)

    def all_keys(self) -> list[str]:
        return list(self._sessions.keys())
