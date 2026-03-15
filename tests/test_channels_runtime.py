"""Tests for channel registry and runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.channels.registry import ChannelRegistry
from mini_agent.channels.runtime import ChannelRuntime
from mini_agent.channels.types import ChannelContext
from mini_agent.config import Config


class _DummyPlugin:
    id = "feishu"

    def __init__(self):
        self.started = False
        self.stopped = False
        self.sent = []

    async def start(self, _ctx):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def send(self, target, content, **kwargs):
        self.sent.append((target, content, kwargs))
        return {"ok": True}

    def snapshot(self):
        return {"enabled": True, "running": self.started and not self.stopped, "plugin": self.id}


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _build_config(tmp_path: Path, feishu_enabled: bool) -> Config:
    accounts_block = ""
    if feishu_enabled:
        accounts_block = """
    default_account: "main"
    accounts:
      main:
        app_id: "cli_main"
        app_secret: "secret-main"
"""
    config_path = _write_config(
        tmp_path / "config.yaml",
        f"""
api_key: "test-key"
channels:
  feishu:
    enabled: {"true" if feishu_enabled else "false"}
{accounts_block}
""",
    )
    return Config.from_yaml(config_path)


def test_registry_prevents_duplicate_channel():
    registry = ChannelRegistry()
    registry.register("feishu", _DummyPlugin)
    with pytest.raises(ValueError, match="channel already registered"):
        registry.register("feishu", _DummyPlugin)


@pytest.mark.asyncio
async def test_runtime_start_send_stop(tmp_path):
    cfg = _build_config(tmp_path, feishu_enabled=True)
    registry = ChannelRegistry()
    holder: dict[str, _DummyPlugin] = {}

    def _factory():
        plugin = _DummyPlugin()
        holder["plugin"] = plugin
        return plugin

    registry.register("feishu", _factory)
    runtime = ChannelRuntime(registry=registry, context=ChannelContext(config=cfg, config_path=tmp_path / "config.yaml"))

    await runtime.start()
    assert "plugin" in holder
    assert holder["plugin"].started is True

    send_resp = await runtime.send("feishu", target="chat-1", content="hello")
    assert send_resp["ok"] is True
    assert holder["plugin"].sent[0][0] == "chat-1"

    snapshot = runtime.snapshot()
    assert snapshot["started"] is True
    assert snapshot["channels"]["feishu"]["running"] is True

    await runtime.stop()
    assert holder["plugin"].stopped is True


@pytest.mark.asyncio
async def test_runtime_skips_disabled_channel(tmp_path):
    cfg = _build_config(tmp_path, feishu_enabled=False)
    registry = ChannelRegistry()
    created = {"count": 0}

    def _factory():
        created["count"] += 1
        return _DummyPlugin()

    registry.register("feishu", _factory)
    runtime = ChannelRuntime(registry=registry, context=ChannelContext(config=cfg, config_path=tmp_path / "config.yaml"))

    await runtime.start()
    assert created["count"] == 0
    snapshot = runtime.snapshot()
    assert snapshot["channels"]["feishu"]["enabled"] is False
    assert snapshot["channels"]["feishu"]["running"] is False
