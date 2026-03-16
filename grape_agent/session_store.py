"""Channel-aware Agent session store."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from grape_agent.agent import Agent
from grape_agent.routing.session_key import build_session_key


@dataclass
class AgentSession:
    """Container for one logical session with serialized execution."""

    key: str
    agent_id: str
    channel: str
    session_id: str
    parent_key: str | None
    depth: int
    created_at: str
    agent: Agent
    lock: asyncio.Lock


class AgentSessionStore:
    """Unified `agent:{agent_id}:{channel}:{session_id}` session management."""

    def __init__(self):
        self._sessions: dict[str, AgentSession] = {}
        self._guard = asyncio.Lock()

    @staticmethod
    def make_key(channel: str, session_id: str, agent_id: str = "main") -> str:
        return build_session_key(agent_id=agent_id, channel=channel, chat_id=session_id)

    async def get_or_create(
        self,
        channel: str,
        session_id: str,
        factory: Callable[[], Agent],
        agent_id: str = "main",
        parent_key: str | None = None,
        depth: int = 0,
    ) -> AgentSession:
        key = self.make_key(channel, session_id, agent_id=agent_id)
        async with self._guard:
            existing = self._sessions.get(key)
            if existing is not None:
                return existing

            created = AgentSession(
                key=key,
                agent_id=agent_id,
                channel=channel,
                session_id=session_id,
                parent_key=parent_key,
                depth=max(0, int(depth)),
                created_at=datetime.now(timezone.utc).isoformat(),
                agent=factory(),
                lock=asyncio.Lock(),
            )
            self._sessions[key] = created
            return created

    def get(self, channel: str, session_id: str, agent_id: str = "main") -> AgentSession | None:
        return self._sessions.get(self.make_key(channel, session_id, agent_id=agent_id))

    def pop(self, channel: str, session_id: str, agent_id: str = "main") -> AgentSession | None:
        return self._sessions.pop(self.make_key(channel, session_id, agent_id=agent_id), None)

    def get_by_key(self, session_key: str) -> AgentSession | None:
        return self._sessions.get(session_key)

    def pop_by_key(self, session_key: str) -> AgentSession | None:
        return self._sessions.pop(session_key, None)

    def pop_channel_sessions(self, channel: str, session_id: str) -> list[AgentSession]:
        removed: list[AgentSession] = []
        for key, value in list(self._sessions.items()):
            if value.channel == channel and value.session_id == session_id:
                removed_session = self._sessions.pop(key, None)
                if removed_session is not None:
                    removed.append(removed_session)
        return removed

    def all_keys(self) -> list[str]:
        return list(self._sessions.keys())

    def all_sessions(self) -> list[AgentSession]:
        return list(self._sessions.values())
