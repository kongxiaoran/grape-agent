"""Tests for gateway config parsing."""

from pathlib import Path

import pytest

from grape_agent.config import Config


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_gateway_config_defaults(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
""",
    )
    cfg = Config.from_yaml(config_path)
    assert cfg.gateway.enabled is False
    assert cfg.gateway.host == "127.0.0.1"
    assert cfg.gateway.port == 8765
    assert cfg.gateway.auth.enabled is True
    assert cfg.gateway.auth.token == ""


def test_gateway_config_custom_values(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
gateway:
  enabled: true
  host: "0.0.0.0"
  port: 9900
  auth:
    enabled: true
    token: "secret-token"
""",
    )
    cfg = Config.from_yaml(config_path)
    assert cfg.gateway.enabled is True
    assert cfg.gateway.host == "0.0.0.0"
    assert cfg.gateway.port == 9900
    assert cfg.gateway.auth.enabled is True
    assert cfg.gateway.auth.token == "secret-token"


def test_gateway_enabled_requires_auth_token(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
gateway:
  enabled: true
  auth:
    enabled: true
    token: ""
""",
    )
    with pytest.raises(ValueError, match="gateway.auth.token is required"):
        Config.from_yaml(config_path)

