"""Tests for M3 agents/routing configuration parsing."""

from pathlib import Path

from mini_agent.config import Config


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_agents_routing_defaults(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
""",
    )
    cfg = Config.from_yaml(config_path)
    assert cfg.agents.default_agent_id == "main"
    assert cfg.agents.profiles == {}
    assert cfg.routing.default_agent_id == "main"
    assert cfg.routing.rules == []


def test_agents_routing_custom_values(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
agents:
  default_agent_id: "reviewer"
  profiles:
    reviewer:
      workspace: "./workspace-reviewer"
      model: "GLM-5-plus"
      system_prompt_path: "reviewer_prompt.md"
routing:
  default_agent_id: "reviewer"
  rules:
    - channel: "feishu"
      chat_type: "group"
      chat_id: "oc_group_1"
      agent_id: "reviewer"
    - channel: "feishu"
      account_id: "cli_xxx"
      agent_id: "main"
""",
    )
    cfg = Config.from_yaml(config_path)
    assert cfg.agents.default_agent_id == "reviewer"
    assert "reviewer" in cfg.agents.profiles
    reviewer = cfg.agents.profiles["reviewer"]
    assert reviewer.workspace == "./workspace-reviewer"
    assert reviewer.model == "GLM-5-plus"
    assert reviewer.system_prompt_path == "reviewer_prompt.md"

    assert cfg.routing.default_agent_id == "reviewer"
    assert len(cfg.routing.rules) == 2
    assert cfg.routing.rules[0].channel == "feishu"
    assert cfg.routing.rules[0].chat_type == "group"
    assert cfg.routing.rules[0].chat_id == "oc_group_1"
    assert cfg.routing.rules[0].agent_id == "reviewer"
