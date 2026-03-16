"""Tests for gateway router and auth flow."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from grape_agent.agents.orchestrator import SessionOrchestrator
from grape_agent.config import Config
from grape_agent.gateway.handlers import register_builtin_handlers
from grape_agent.gateway.protocol import (
    ERR_INTERNAL,
    ERR_METHOD_NOT_FOUND,
    ConnectionContext,
    GatewayContext,
    GatewayRequest,
)
from grape_agent.gateway.router import GatewayRouter
from grape_agent.gateway.server import GatewayServer
from grape_agent.session_store import AgentSessionStore


class _DummyRuntime:
    def __init__(self):
        self.calls = []

    async def send(self, channel_id: str, target: str, content: str, **kwargs):
        self.calls.append((channel_id, target, content, kwargs))
        return {"ok": True, "message_id": "msg_001"}

    def snapshot(self):
        return {
            "started": True,
            "running_count": 1,
            "channels": {"feishu": {"enabled": True, "running": True}},
        }


class _DummyAgent:
    def __init__(self, label: str):
        self.label = label
        self.messages = [SimpleNamespace(role="system", content="sys", tool_calls=[])]

    def add_user_message(self, message: str):
        self.messages.append(SimpleNamespace(role="user", content=message, tool_calls=[]))

    async def run(self) -> str:
        self.messages.append(SimpleNamespace(role="assistant", content=f"{self.label}:ok", tool_calls=[]))
        return f"{self.label}:ok"


def _build_config(tmp_path, extra: str = "") -> Config:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
api_key: "test-key"
gateway:
  enabled: true
  host: "127.0.0.1"
  port: 8765
  auth:
    enabled: true
    token: "secret-token"
{extra}
""",
        encoding="utf-8",
    )
    return Config.from_yaml(config_path)


def _build_router(cfg: Config, runtime=None, orchestrator=None) -> GatewayRouter:
    ctx = GatewayContext(
        app_name="grape-agent",
        started_at=datetime.now(),
        config=cfg,
        gateway_config=cfg.gateway,
        session_store=AgentSessionStore(),
        channels_runtime=runtime,
        subagent_orchestrator=orchestrator,
    )
    router = GatewayRouter(ctx)
    return router


@pytest.mark.asyncio
async def test_router_dispatch_method_not_found(tmp_path):
    cfg = _build_config(tmp_path)
    router = _build_router(cfg)
    req = GatewayRequest(id="1", method="missing.method", params={})
    conn = ConnectionContext(client_id="t", role="operator", remote="127.0.0.1:1")

    resp = await router.dispatch(req, conn)
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.code == ERR_METHOD_NOT_FOUND


@pytest.mark.asyncio
async def test_router_dispatch_handler_exception(tmp_path):
    cfg = _build_config(tmp_path)
    router = _build_router(cfg)

    async def _boom(_params, _ctx, _conn):
        raise RuntimeError("boom")

    router.register("boom", _boom)
    req = GatewayRequest(id="1", method="boom", params={})
    conn = ConnectionContext(client_id="t", role="operator", remote="127.0.0.1:1")

    resp = await router.dispatch(req, conn)
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.code == ERR_INTERNAL
    assert "boom" in resp.error.message


@pytest.mark.asyncio
async def test_server_dispatch_rejects_missing_token(tmp_path):
    cfg = _build_config(tmp_path)
    router = _build_router(cfg)
    register_builtin_handlers(router)
    server = GatewayServer(config=cfg.gateway, router=router)

    resp = await server._dispatch_payload(  # pylint: disable=protected-access
        '{"id":"req-1","method":"health","params":{},"auth":{"client_id":"x","role":"channel"}}',
        "127.0.0.1:12345",
    )
    assert resp.ok is False
    assert resp.error is not None
    assert resp.error.code == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_server_dispatch_health_success(tmp_path):
    cfg = _build_config(tmp_path)
    router = _build_router(cfg)
    register_builtin_handlers(router)
    server = GatewayServer(config=cfg.gateway, router=router)

    resp = await server._dispatch_payload(  # pylint: disable=protected-access
        '{"id":"req-2","method":"health","params":{},"auth":{"token":"secret-token","client_id":"x","role":"operator"}}',
        "127.0.0.1:12345",
    )
    assert resp.ok is True
    assert resp.result is not None
    assert resp.result["status"] == "ok"


@pytest.mark.asyncio
async def test_server_dispatch_channels_status_success(tmp_path):
    cfg = _build_config(tmp_path)
    router = _build_router(cfg, runtime=_DummyRuntime())
    register_builtin_handlers(router)
    server = GatewayServer(config=cfg.gateway, router=router)

    resp = await server._dispatch_payload(  # pylint: disable=protected-access
        '{"id":"req-3","method":"channels.status","params":{},"auth":{"token":"secret-token","client_id":"x","role":"operator"}}',
        "127.0.0.1:12345",
    )
    assert resp.ok is True
    assert resp.result is not None
    assert "channels" in resp.result


@pytest.mark.asyncio
async def test_server_dispatch_channels_send_success(tmp_path):
    cfg = _build_config(tmp_path)
    runtime = _DummyRuntime()
    router = _build_router(cfg, runtime=runtime)
    register_builtin_handlers(router)
    server = GatewayServer(config=cfg.gateway, router=router)

    resp = await server._dispatch_payload(  # pylint: disable=protected-access
        (
            '{"id":"req-4","method":"channels.send","params":{"channel":"feishu","target":"chat_1","content":"hello",'
            '"options":{"receive_id_type":"chat_id"}},"auth":{"token":"secret-token","client_id":"x","role":"operator"}}'
        ),
        "127.0.0.1:12345",
    )
    assert resp.ok is True
    assert resp.result is not None
    assert resp.result["ok"] is True
    assert runtime.calls[0][0] == "feishu"
    assert runtime.calls[0][1] == "chat_1"


@pytest.mark.asyncio
async def test_server_dispatch_channels_send_missing_params(tmp_path):
    cfg = _build_config(tmp_path)
    router = _build_router(cfg, runtime=_DummyRuntime())
    register_builtin_handlers(router)
    server = GatewayServer(config=cfg.gateway, router=router)

    resp = await server._dispatch_payload(  # pylint: disable=protected-access
        '{"id":"req-5","method":"channels.send","params":{"channel":"feishu","content":"hello"},"auth":{"token":"secret-token","client_id":"x","role":"operator"}}',
        "127.0.0.1:12345",
    )
    assert resp.ok is True
    assert resp.result is not None
    assert resp.result["ok"] is False
    assert "missing required param: target" in resp.result["error"]


@pytest.mark.asyncio
async def test_server_dispatch_sessions_list_includes_agent_id(tmp_path):
    cfg = _build_config(tmp_path)
    ctx = GatewayContext(
        app_name="grape-agent",
        started_at=datetime.now(),
        config=cfg,
        gateway_config=cfg.gateway,
        session_store=AgentSessionStore(),
        channels_runtime=_DummyRuntime(),
    )
    router = GatewayRouter(ctx)
    register_builtin_handlers(router)
    server = GatewayServer(config=cfg.gateway, router=router)

    class _DummyAgent:
        pass

    await ctx.session_store.get_or_create(
        channel="feishu",
        session_id="oc_1",
        agent_id="reviewer",
        factory=lambda: _DummyAgent(),
    )

    resp = await server._dispatch_payload(  # pylint: disable=protected-access
        '{"id":"req-6","method":"sessions.list","params":{},"auth":{"token":"secret-token","client_id":"x","role":"operator"}}',
        "127.0.0.1:12345",
    )
    assert resp.ok is True
    assert resp.result is not None
    assert resp.result["total"] == 1
    assert resp.result["items"][0]["agent_id"] == "reviewer"
    assert resp.result["items"][0]["key"] == "agent:reviewer:feishu:oc_1"


@pytest.mark.asyncio
async def test_server_dispatch_sessions_spawn_and_run_get(tmp_path):
    cfg = _build_config(tmp_path)
    store = AgentSessionStore()

    async def _create_session(agent_id: str, channel: str, session_id: str, parent_key=None, depth=0):
        return await store.get_or_create(
            channel=channel,
            session_id=session_id,
            agent_id=agent_id,
            parent_key=parent_key,
            depth=depth,
            factory=lambda: _DummyAgent(agent_id),
        )

    parent = await _create_session("main", "terminal", "main")
    orchestrator = SessionOrchestrator(
        session_store=store,
        create_session=_create_session,
    )
    ctx = GatewayContext(
        app_name="grape-agent",
        started_at=datetime.now(),
        config=cfg,
        gateway_config=cfg.gateway,
        session_store=store,
        channels_runtime=_DummyRuntime(),
        subagent_orchestrator=orchestrator,
    )
    router = GatewayRouter(ctx)
    register_builtin_handlers(router)
    server = GatewayServer(config=cfg.gateway, router=router)

    spawn_resp = await server._dispatch_payload(  # pylint: disable=protected-access
        (
            '{"id":"req-7","method":"sessions.spawn","params":{"parent_session_key":"'
            + parent.key
            + '","task":"hello","mode":"run","wait":false},"auth":{"token":"secret-token","client_id":"x","role":"operator"}}'
        ),
        "127.0.0.1:12345",
    )
    assert spawn_resp.ok is True
    assert spawn_resp.result is not None
    assert spawn_resp.result["ok"] is True
    run_id = spawn_resp.result["dispatch"]["run_id"]

    # wait for background run to finish
    for _ in range(20):
        run = orchestrator.get_run(run_id)
        if run and run["status"] in {"completed", "failed"}:
            break
        await asyncio.sleep(0.01)

    run_get_resp = await server._dispatch_payload(  # pylint: disable=protected-access
        (
            '{"id":"req-8","method":"sessions.run.get","params":{"run_id":"'
            + run_id
            + '"},"auth":{"token":"secret-token","client_id":"x","role":"operator"}}'
        ),
        "127.0.0.1:12345",
    )
    assert run_get_resp.ok is True
    assert run_get_resp.result is not None
    assert run_get_resp.result["ok"] is True
    assert run_get_resp.result["run"]["run_id"] == run_id
