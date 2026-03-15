"""Tests for cron config parsing."""

from pathlib import Path

from mini_agent.config import Config


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_cron_config_defaults(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
""",
    )
    cfg = Config.from_yaml(config_path)
    assert cfg.cron.enabled is False
    assert cfg.cron.poll_interval_sec == 5.0
    assert cfg.cron.max_concurrency == 2


def test_cron_config_custom_values(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
cron:
  enabled: true
  store_path: "./workspace/cron-jobs.json"
  poll_interval_sec: 1.2
  max_concurrency: 3
  default_timeout_sec: 120
""",
    )
    cfg = Config.from_yaml(config_path)
    assert cfg.cron.enabled is True
    assert cfg.cron.store_path == "./workspace/cron-jobs.json"
    assert cfg.cron.poll_interval_sec == 1.2
    assert cfg.cron.max_concurrency == 3
    assert cfg.cron.default_timeout_sec == 120
