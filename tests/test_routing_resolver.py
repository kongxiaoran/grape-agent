"""Tests for routing resolver."""

from pathlib import Path

from grape_agent.config import Config
from grape_agent.routing import RoutingInput, RoutingResolver


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_routing_resolver_matches_first_rule(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
routing:
  default_agent_id: "main"
  rules:
    - channel: "feishu"
      chat_type: "group"
      agent_id: "ops"
    - channel: "feishu"
      agent_id: "fallback"
""",
    )
    cfg = Config.from_yaml(config_path)
    resolver = RoutingResolver.from_config(cfg)
    result = resolver.resolve(
        RoutingInput(channel="feishu", account_id="cli_x", chat_id="oc_1", chat_type="group")
    )
    assert result.agent_id == "ops"
    assert result.matched_by == "rule:0"
    assert result.session_key == "agent:ops:feishu:oc_1"


def test_routing_resolver_uses_default_when_no_match(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
routing:
  default_agent_id: "reviewer"
  rules:
    - channel: "terminal"
      agent_id: "main"
""",
    )
    cfg = Config.from_yaml(config_path)
    resolver = RoutingResolver.from_config(cfg)
    result = resolver.resolve(
        RoutingInput(channel="feishu", account_id=None, chat_id="oc_x", chat_type="direct")
    )
    assert result.agent_id == "reviewer"
    assert result.matched_by == "default"
    assert result.session_key == "agent:reviewer:feishu:oc_x"
