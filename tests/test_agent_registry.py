"""Tests for agent profile registry."""

from pathlib import Path

from grape_agent.agents import AgentRegistry
from grape_agent.config import Config


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_registry_uses_default_workspace_override(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
workspace_dir: "./workspace"
agents:
  default_agent_id: "main"
""",
    )
    cfg = Config.from_yaml(config_path)
    registry = AgentRegistry(cfg, default_workspace=tmp_path / "feishu-workspace")
    main_profile = registry.get("main")
    assert main_profile.id == "main"
    assert main_profile.workspace == (tmp_path / "feishu-workspace").resolve()


def test_registry_resolves_custom_profile_overrides(tmp_path):
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
""",
    )
    cfg = Config.from_yaml(config_path)
    registry = AgentRegistry(cfg)
    reviewer = registry.get("reviewer")
    assert reviewer.id == "reviewer"
    assert reviewer.workspace == (Path.cwd() / "workspace-reviewer").resolve()
    assert reviewer.model == "GLM-5-plus"
    assert reviewer.system_prompt_path == "reviewer_prompt.md"
    assert registry.default_agent_id == "reviewer"
