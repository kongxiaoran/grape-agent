"""Tests for embedded Feishu configuration parsing."""

from pathlib import Path

from mini_agent.config import Config


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_feishu_config_defaults(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
api_base: "https://api.minimax.io"
model: "MiniMax-M2.5"
provider: "anthropic"
""",
    )

    cfg = Config.from_yaml(config_path)
    assert cfg.feishu.enabled is False
    assert cfg.feishu.app_id == ""
    assert cfg.feishu.group_require_mention is True


def test_feishu_config_custom_values(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
api_base: "https://api.minimax.io"
model: "MiniMax-M2.5"
provider: "anthropic"
feishu:
  enabled: true
  app_id: "cli_xxx"
  app_secret: "secret"
  domain: "lark"
  group_require_mention: false
  workspace_base: "~/.mini-agent/feishu_workspaces"
""",
    )

    cfg = Config.from_yaml(config_path)
    assert cfg.feishu.enabled is True
    assert cfg.feishu.app_id == "cli_xxx"
    assert cfg.feishu.app_secret == "secret"
    assert cfg.feishu.domain == "lark"
    assert cfg.feishu.group_require_mention is False
    assert cfg.feishu.workspace_base == "~/.mini-agent/feishu_workspaces"
