"""Tests for gateway cron handlers."""

from __future__ import annotations

from datetime import datetime

import pytest

from grape_agent.config import Config
from grape_agent.cron.models import CronRun, utc_now_iso
from grape_agent.cron.store import CronStore
from grape_agent.gateway.handlers import register_builtin_handlers
from grape_agent.gateway.protocol import GatewayContext
from grape_agent.gateway.router import GatewayRouter
from grape_agent.gateway.server import GatewayServer
from grape_agent.session_store import AgentSessionStore


class _DummyScheduler:
    def snapshot(self):
        return {"running": True, "active_jobs": 0}

    async def trigger_job(self, job_id: str):
        if job_id != "job_1":
            return None
        return CronRun(
            run_id="cronrun_1",
            job_id=job_id,
            status="completed",
            scheduled_at=utc_now_iso(),
            started_at=utc_now_iso(),
            finished_at=utc_now_iso(),
            result_preview="ok",
        )


def _build_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
api_key: "test-key"
gateway:
  enabled: true
  host: "127.0.0.1"
  port: 8765
  auth:
    enabled: true
    token: "secret-token"
cron:
  enabled: true
""",
        encoding="utf-8",
    )
    return Config.from_yaml(config_path)


@pytest.mark.asyncio
async def test_gateway_cron_methods(tmp_path):
    cfg = _build_config(tmp_path)
    store = CronStore(str(tmp_path / "cron-jobs.json"))
    await store.upsert_job(
        {
            "id": "job_1",
            "schedule": "@every 1m",
            "task": "hello",
            "agent_id": "main",
            "session_target": "sticky",
        }
    )

    ctx = GatewayContext(
        app_name="grape-agent",
        started_at=datetime.now(),
        config=cfg,
        gateway_config=cfg.gateway,
        session_store=AgentSessionStore(),
        cron_store=store,
        cron_scheduler=_DummyScheduler(),
    )
    router = GatewayRouter(ctx)
    register_builtin_handlers(router)
    server = GatewayServer(config=cfg.gateway, router=router)

    list_resp = await server._dispatch_payload(  # pylint: disable=protected-access
        '{"id":"req-1","method":"cron.jobs.list","params":{},"auth":{"token":"secret-token","client_id":"x","role":"operator"}}',
        "127.0.0.1:1",
    )
    assert list_resp.ok is True
    assert list_resp.result is not None
    assert list_resp.result["ok"] is True
    assert list_resp.result["total"] == 1

    trigger_resp = await server._dispatch_payload(  # pylint: disable=protected-access
        '{"id":"req-2","method":"cron.trigger","params":{"job_id":"job_1"},"auth":{"token":"secret-token","client_id":"x","role":"operator"}}',
        "127.0.0.1:1",
    )
    assert trigger_resp.ok is True
    assert trigger_resp.result is not None
    assert trigger_resp.result["ok"] is True
    assert trigger_resp.result["run"]["job_id"] == "job_1"
