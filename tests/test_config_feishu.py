"""Tests for Feishu channel config parsing."""

from pathlib import Path

import pytest

from mini_agent.config import Config


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_feishu_config_defaults(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
""",
    )
    cfg = Config.from_yaml(config_path)
    assert cfg.channels.feishu.enabled is False
    assert cfg.channels.feishu.default_account == "main"
    assert cfg.channels.feishu.accounts == {}
    assert cfg.channels.feishu.policy.require_mention is True
    assert cfg.channels.feishu.policy.reply_in_thread is True
    assert cfg.channels.feishu.policy.group_session_scope == "group"
    assert cfg.channels.feishu.streaming.progress_ping_sec == 0
    assert cfg.channels.feishu.streaming.progress_card_enabled is True
    assert cfg.channels.feishu.streaming.progress_card_start_sec == 5
    assert cfg.channels.feishu.streaming.progress_card_update_sec == 3
    assert cfg.channels.feishu.streaming.progress_card_tail_lines == 5


def test_feishu_config_new_structure_custom_values(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
channels:
  feishu:
    enabled: true
    default_account: "ops"
    accounts:
      main:
        app_id: "cli_main"
        app_secret: "secret-main"
      ops:
        app_id: "cli_ops"
        app_secret: "secret-ops"
        domain: "lark"
    render_mode: "card"
    policy:
      require_mention: false
      reply_in_thread: false
      group_session_scope: "topic"
    streaming:
      enabled: true
      chunk_size: 480
      interval_ms: 60
      reply_all_chunks: true
      progress_ping_sec: 9
""",
    )
    cfg = Config.from_yaml(config_path)
    assert cfg.channels.feishu.enabled is True
    assert cfg.channels.feishu.default_account == "ops"
    assert sorted(cfg.channels.feishu.accounts.keys()) == ["main", "ops"]
    assert cfg.channels.feishu.accounts["ops"].domain == "lark"
    assert cfg.channels.feishu.policy.require_mention is False
    assert cfg.channels.feishu.policy.reply_in_thread is False
    assert cfg.channels.feishu.policy.group_session_scope == "topic"


def test_feishu_enabled_requires_accounts(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
channels:
  feishu:
    enabled: true
""",
    )
    with pytest.raises(ValueError, match="channels.feishu.accounts is required"):
        Config.from_yaml(config_path)


def test_feishu_default_account_must_exist(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
channels:
  feishu:
    enabled: true
    default_account: "ops"
    accounts:
      main:
        app_id: "cli_main"
        app_secret: "secret-main"
""",
    )
    with pytest.raises(ValueError, match="channels.feishu.default_account must exist"):
        Config.from_yaml(config_path)


def test_legacy_top_level_feishu_rejected(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
feishu:
  enabled: true
""",
    )

    with pytest.raises(ValueError, match="top-level 'feishu' config is not supported"):
        Config.from_yaml(config_path)
