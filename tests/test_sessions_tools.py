"""Tests for sessions_* tool wrappers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from grape_agent.agents.orchestrator import SessionOrchestrator
from grape_agent.session_store import AgentSessionStore
from grape_agent.tools.sessions_history_tool import SessionsHistoryTool
from grape_agent.tools.sessions_list_tool import SessionsListTool
from grape_agent.tools.sessions_send_tool import SessionsSendTool
from grape_agent.tools.sessions_spawn_tool import SessionsSpawnTool


class _DummyAgent:
    def __init__(self, label: str):
        self.label = label
        self.messages = [SimpleNamespace(role="system", content="sys", tool_calls=[])]

    def add_user_message(self, message: str) -> None:
        self.messages.append(SimpleNamespace(role="user", content=message, tool_calls=[]))

    async def run(self) -> str:
        self.messages.append(SimpleNamespace(role="assistant", content=f"{self.label}:ok", tool_calls=[]))
        return f"{self.label}:ok"


async def _create_session(store: AgentSessionStore, agent_id: str, channel: str, session_id: str, parent_key=None, depth=0):
    return await store.get_or_create(
        channel=channel,
        session_id=session_id,
        agent_id=agent_id,
        parent_key=parent_key,
        depth=depth,
        factory=lambda: _DummyAgent(agent_id),
    )


@pytest.mark.asyncio
async def test_sessions_tools_respect_access_scope():
    store = AgentSessionStore()
    root = await _create_session(store, "main", "terminal", "root")
    foreign = await _create_session(store, "main", "terminal", "foreign")
    orchestrator = SessionOrchestrator(
        session_store=store,
        create_session=lambda **kwargs: _create_session(store, **kwargs),
    )

    spawn_tool = SessionsSpawnTool(orchestrator, root.key)
    spawn_result = await spawn_tool.execute(task="do it", mode="create")
    assert spawn_result.success is True

    child_key = orchestrator.list_accessible_sessions(owner_session_key=root.key, limit=10)[1]["key"]
    list_tool = SessionsListTool(orchestrator, root.key)
    list_result = await list_tool.execute(limit=10)
    assert list_result.success is True
    assert child_key in list_result.content

    send_tool = SessionsSendTool(orchestrator, root.key)
    denied_send = await send_tool.execute(session_key=foreign.key, message="nope")
    assert denied_send.success is False
    assert "access denied" in (denied_send.error or "")

    history_tool = SessionsHistoryTool(orchestrator, root.key)
    allowed_history = await history_tool.execute(session_key=child_key)
    assert allowed_history.success is True
