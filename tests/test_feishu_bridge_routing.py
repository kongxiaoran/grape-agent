"""Tests for Feishu bridge M3 routing integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from grape_agent.config import Config
from grape_agent.feishu.bridge import FeishuAgentBridge
from grape_agent.feishu.types import FeishuChatType, FeishuIncomingMessage, FeishuMessageType


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _build_config(tmp_path: Path) -> Config:
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
agents:
  default_agent_id: "main"
  profiles:
    reviewer:
      workspace: "./workspace-reviewer"
      model: "GLM-5-reviewer"
routing:
  default_agent_id: "main"
  rules:
    - channel: "feishu"
      chat_type: "group"
      chat_id: "oc_group_1"
      agent_id: "reviewer"
""",
    )
    return Config.from_yaml(config_path)


class _DummyFeishuClient:
    def __init__(self):
        self.app_id = "cli_test"
        self.bot_open_id = None


def _build_inbound(chat_id: str, chat_type: FeishuChatType) -> FeishuIncomingMessage:
    return FeishuIncomingMessage(
        message_id="om_in",
        chat_id=chat_id,
        chat_type=chat_type,
        message_type=FeishuMessageType.TEXT,
        content="hi",
        raw_content='{"text":"hi"}',
        sender_open_id="ou_u",
        sender_user_id="ou_u",
    )


def test_bridge_resolve_route_hits_rule(tmp_path):
    cfg = _build_config(tmp_path)
    bridge = FeishuAgentBridge(
        feishu_client=_DummyFeishuClient(),
        agent_config=cfg,
        workspace_root=tmp_path / "feishu-workspaces",
    )
    inbound = _build_inbound(chat_id="oc_group_1", chat_type=FeishuChatType.GROUP)
    route = bridge._resolve_route(inbound)
    assert route.agent_id == "reviewer"
    assert route.matched_by == "rule:0"
    assert route.session_key == "agent:reviewer:feishu:oc_group_1"


@pytest.mark.asyncio
async def test_bridge_get_or_create_session_uses_routed_key(tmp_path, monkeypatch):
    cfg = _build_config(tmp_path)
    bridge = FeishuAgentBridge(
        feishu_client=_DummyFeishuClient(),
        agent_config=cfg,
        workspace_root=tmp_path / "feishu-workspaces",
    )

    class _DummyBundle:
        def __init__(self):
            self.base_tools = []
            self.llm_client = object()
            self.system_prompt = "test"

    async def _fake_get_or_create_runtime_bundle(_agent_id: str):
        return _DummyBundle()

    monkeypatch.setattr(bridge, "_get_or_create_runtime_bundle", _fake_get_or_create_runtime_bundle)

    session = await bridge._get_or_create_session("reviewer", "feishu", "oc_group_1")
    assert session.key == "agent:reviewer:feishu:oc_group_1"
    assert session.agent_id == "reviewer"
