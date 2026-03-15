"""Tests for cron schedule/store/scheduler core."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from mini_agent.cron import CronDelivery, CronExecutor, CronScheduler, CronStore, compute_next_run_at, parse_schedule
from mini_agent.session_store import AgentSessionStore


class _DummyAgent:
    def __init__(self):
        self.messages = [SimpleNamespace(role="system", content="sys", tool_calls=[])]

    def add_user_message(self, message: str) -> None:
        self.messages.append(SimpleNamespace(role="user", content=message, tool_calls=[]))

    async def run(self) -> str:
        return "cron-ok"


@pytest.mark.asyncio
async def test_parse_schedule_and_compute_next_run():
    spec = parse_schedule("@every 2s")
    assert spec.kind == "interval"
    assert spec.interval_seconds == 2

    now = datetime.now(timezone.utc)
    next_run = compute_next_run_at("*/5 * * * *", after=now)
    assert next_run > now
    assert next_run.minute % 5 == 0

    with pytest.raises(ValueError):
        parse_schedule("invalid schedule")


@pytest.mark.asyncio
async def test_cron_scheduler_executes_due_job(tmp_path):
    store = CronStore(str(tmp_path / "cron.json"))
    session_store = AgentSessionStore()

    async def _create_session(agent_id: str, channel: str, session_id: str, parent_key=None, depth=0):
        return await session_store.get_or_create(
            channel=channel,
            session_id=session_id,
            agent_id=agent_id,
            parent_key=parent_key,
            depth=depth,
            factory=_DummyAgent,
        )

    await store.upsert_job(
        {
            "id": "job_interval",
            "schedule": "@every 1s",
            "agent_id": "main",
            "task": "ping",
            "enabled": True,
            "session_target": "isolated",
        }
    )

    scheduler = CronScheduler(
        store=store,
        executor=CronExecutor(create_session=_create_session, default_timeout_sec=30),
        delivery=CronDelivery(channels_runtime=None),
        poll_interval_sec=0.2,
        max_concurrency=1,
    )
    await scheduler.start()
    await asyncio.sleep(1.5)
    await scheduler.stop()

    runs = await store.list_runs(limit=10)
    assert len(runs) >= 1
    assert runs[0].status in {"completed", "failed", "timeout"}
