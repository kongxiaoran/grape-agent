"""Tests for routed session store key model."""

from __future__ import annotations

import pytest

from grape_agent.session_store import AgentSessionStore


class _DummyAgent:
    pass


def _new_agent():
    return _DummyAgent()


@pytest.mark.asyncio
async def test_session_store_uses_agent_prefixed_key():
    store = AgentSessionStore()
    session = await store.get_or_create(
        channel="feishu",
        session_id="oc_1",
        agent_id="ops",
        factory=_new_agent,
    )
    assert session.key == "agent:ops:feishu:oc_1"
    assert session.agent_id == "ops"
    assert store.get("feishu", "oc_1", agent_id="ops") is session


@pytest.mark.asyncio
async def test_session_store_pop_channel_sessions_removes_all_agents():
    store = AgentSessionStore()
    await store.get_or_create(channel="feishu", session_id="oc_1", agent_id="main", factory=_new_agent)
    await store.get_or_create(channel="feishu", session_id="oc_1", agent_id="ops", factory=_new_agent)
    await store.get_or_create(channel="feishu", session_id="oc_2", agent_id="main", factory=_new_agent)

    removed = store.pop_channel_sessions("feishu", "oc_1")
    assert len(removed) == 2
    assert store.get("feishu", "oc_1", agent_id="main") is None
    assert store.get("feishu", "oc_1", agent_id="ops") is None
    assert store.get("feishu", "oc_2", agent_id="main") is not None
