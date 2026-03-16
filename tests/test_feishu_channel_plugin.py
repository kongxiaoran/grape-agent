"""Tests for Feishu channel plugin send path (M6 multi-account)."""

from __future__ import annotations

from pathlib import Path

import pytest

from grape_agent.channels.plugins.feishu.plugin import FeishuChannelPlugin
from grape_agent.channels.types import ChannelContext
from grape_agent.config import Config


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _build_config(tmp_path: Path, enabled: bool = True) -> Config:
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
api_key: "test-key"
channels:
  feishu:
    enabled: {"true" if enabled else "false"}
    default_account: "main"
    accounts:
      main:
        app_id: "cli_main"
        app_secret: "secret-main"
      ops:
        app_id: "cli_ops"
        app_secret: "secret-ops"
        domain: "lark"
""",
    )
    return Config.from_yaml(config_path)


@pytest.mark.asyncio
async def test_plugin_send_returns_error_when_not_started(tmp_path):
    cfg = _build_config(tmp_path, enabled=True)
    plugin = FeishuChannelPlugin()
    result = await plugin.send(target="chat_1", content="hello")
    assert result["ok"] is False
    assert "not enabled/running" in result["error"]
    assert cfg.channels.feishu.enabled is True


@pytest.mark.asyncio
async def test_plugin_start_multi_account_and_send(monkeypatch, tmp_path):
    cfg = _build_config(tmp_path, enabled=True)
    runners: dict[str, object] = {}

    class _DummyRunner:
        def __init__(self, config, config_path, account_id, session_store=None, subagent_orchestrator=None):  # noqa: ARG002
            self.account_id = account_id
            self.started = False
            self.stopped = False
            self.sent = []
            runners[account_id] = self

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

        async def send_payload(self, target, msg_type, content, receive_id_type="chat_id"):
            self.sent.append(("send_payload", target, msg_type, content, receive_id_type))
            return {"ok": True, "message_id": f"{self.account_id}_send"}

        async def reply_payload(self, message_id, msg_type, content, reply_in_thread=False):
            self.sent.append(("reply_payload", message_id, msg_type, content, reply_in_thread))
            return {"ok": True, "message_id": f"{self.account_id}_reply"}

        def snapshot(self):
            return {"enabled": True, "running": self.started and not self.stopped, "account_id": self.account_id}

    import grape_agent.channels.plugins.feishu.plugin as feishu_plugin_mod

    monkeypatch.setattr(feishu_plugin_mod, "EmbeddedFeishuRunner", _DummyRunner)
    plugin = FeishuChannelPlugin()
    await plugin.start(ChannelContext(config=cfg, config_path=tmp_path / "config.yaml"))

    send_main = await plugin.send(target="chat_1", content="hello-main")
    send_ops = await plugin.send(target="chat_2", content="hello-ops", account_id="ops")
    reply_ops = await plugin.send(
        target="om_fallback",
        mode="reply",
        message_id="om_123",
        content="reply-text",
        account_id="ops",
        reply_in_thread=True,
    )

    assert send_main["ok"] is True
    assert send_ops["ok"] is True
    assert reply_ops["ok"] is True
    assert runners["main"].sent[0][0] == "send_payload"
    assert runners["ops"].sent[0][0] == "send_payload"
    assert runners["ops"].sent[1][0] == "reply_payload"

    snapshot = plugin.snapshot()
    assert snapshot["running"] is True
    assert snapshot["running_count"] == 2
    assert sorted(snapshot["accounts"].keys()) == ["main", "ops"]

    await plugin.stop()
    assert runners["main"].stopped is True
    assert runners["ops"].stopped is True


@pytest.mark.asyncio
async def test_plugin_send_unknown_account(monkeypatch, tmp_path):
    cfg = _build_config(tmp_path, enabled=True)

    class _DummyRunner:
        def __init__(self, config, config_path, account_id, session_store=None, subagent_orchestrator=None):  # noqa: ARG002
            self.account_id = account_id

        def start(self):
            return None

        def stop(self):
            return None

        async def send_payload(self, target, msg_type, content, receive_id_type="chat_id"):  # pragma: no cover
            return {"ok": True}

        async def reply_payload(self, message_id, msg_type, content, reply_in_thread=False):  # pragma: no cover
            return {"ok": True}

        def snapshot(self):
            return {"enabled": True, "running": True}

    import grape_agent.channels.plugins.feishu.plugin as feishu_plugin_mod

    monkeypatch.setattr(feishu_plugin_mod, "EmbeddedFeishuRunner", _DummyRunner)
    plugin = FeishuChannelPlugin()
    await plugin.start(ChannelContext(config=cfg, config_path=tmp_path / "config.yaml"))
    res = await plugin.send(target="chat_1", content="hello", account_id="missing")
    assert res["ok"] is False
    assert "unknown feishu account" in res["error"]
