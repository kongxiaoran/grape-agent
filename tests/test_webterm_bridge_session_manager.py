"""Tests for webterm bridge session manager."""

from grape_agent.config import WebtermBridgeConfig
from grape_agent.webterm_bridge.session_manager import WebtermSessionManager


class _DummyGateway:
    async def call(self, method, params=None, timeout_sec=15.0):  # noqa: ARG002
        if method == "sessions.spawn":
            return {"ok": True, "child_session_key": "agent:main:webterm:session_1"}
        if method == "sessions.send":
            return {
                "ok": True,
                "result": '{"summary":"ok","command":"grep -n error app.log","risk":"low","reason":"快速定位报错"}',
            }
        raise ValueError(f"unexpected method: {method}")


async def test_open_ingest_suggest_prepare_execute():
    cfg = WebtermBridgeConfig(
        enabled=True,
        token="tok",
        parent_session_key="agent:main:terminal:main",
        command_allowlist=["grep", "tail"],
        command_denylist=["rm"],
    )
    manager = WebtermSessionManager(config=cfg, gateway=_DummyGateway())

    session, created = await manager.open_session(host="bastion", scope="prod", user="ops")
    assert created is True
    assert session.session_key == "agent:main:webterm:session_1"

    manager.ingest(session.bridge_session_id, "line-1", stream="stdout")
    manager.ingest(session.bridge_session_id, "line-2", stream="stderr")
    suggestion = await manager.suggest(session.bridge_session_id)
    assert suggestion["command"].startswith("grep -n")
    assert suggestion["risk"] == "low"

    prepared = manager.prepare_execute(
        bridge_session_id=session.bridge_session_id,
        command=suggestion["command"],
        wrap_markers=True,
        trace_id="tr_1",
    )
    assert prepared["risk"] == "low"
    assert "__MA_BEGIN_tr_1__" in prepared["wrapped_command"]
