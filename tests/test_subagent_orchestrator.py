"""Tests for subagent orchestrator core behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from grape_agent.agents.orchestrator import SessionOrchestrator
from grape_agent.session_store import AgentSessionStore


class _DummyAgent:
    def __init__(self, label: str):
        self.label = label
        self.messages = [SimpleNamespace(role="system", content="system", tool_calls=[])]

    def add_user_message(self, message: str) -> None:
        self.messages.append(SimpleNamespace(role="user", content=message, tool_calls=[]))

    async def run(self) -> str:
        self.messages.append(SimpleNamespace(role="assistant", content=f"{self.label}: done", tool_calls=[]))
        return f"{self.label}: done"


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
async def test_orchestrator_spawn_and_depth_limit():
    store = AgentSessionStore()
    parent = await _create_session(store, "main", "terminal", "main", depth=0)
    orchestrator = SessionOrchestrator(
        session_store=store,
        create_session=lambda **kwargs: _create_session(store, **kwargs),
        enabled=True,
        max_depth=1,
    )

    created = await orchestrator.spawn(
        parent_session_key=parent.key,
        task="analyze this",
        mode="create",
    )
    assert created["ok"] is True
    assert created["depth"] == 1

    blocked = await orchestrator.spawn(
        parent_session_key=created["child_session_key"],
        task="nested",
        mode="create",
    )
    assert blocked["ok"] is False
    assert "max subagent depth reached" in blocked["error"]


@pytest.mark.asyncio
async def test_orchestrator_send_wait_and_history_redact():
    store = AgentSessionStore()
    session = await _create_session(store, "main", "terminal", "main")
    session.agent.messages.append(SimpleNamespace(role="user", content="api_key=sk-12345", tool_calls=[]))

    orchestrator = SessionOrchestrator(
        session_store=store,
        create_session=lambda **kwargs: _create_session(store, **kwargs),
    )

    send_res = await orchestrator.send(session_key=session.key, message="hello", wait=True)
    assert send_res["ok"] is True
    assert send_res["status"] == "completed"
    assert "done" in send_res["result"]

    history = orchestrator.history(session_key=session.key, limit=10)
    assert history["ok"] is True
    previews = [item["content_preview"] for item in history["items"]]
    assert any("[REDACTED]" in preview for preview in previews)
