"""Tests for webterm bridge config parsing."""

from pathlib import Path

import pytest

from mini_agent.config import Config


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_webterm_bridge_defaults(tmp_path):
    cfg = Config.from_yaml(_write(tmp_path / "config.yaml", 'api_key: "k"\n'))
    assert cfg.webterm_bridge.enabled is False
    assert cfg.webterm_bridge.host == "127.0.0.1"
    assert cfg.webterm_bridge.port == 8766
    assert cfg.webterm_bridge.parent_session_key == "agent:main:terminal:main"


def test_webterm_bridge_custom_values(tmp_path):
    cfg = Config.from_yaml(
        _write(
            tmp_path / "config.yaml",
            """
api_key: "k"
webterm_bridge:
  enabled: true
  host: "127.0.0.1"
  port: 9901
  token: "abc"
  gateway_host: "127.0.0.1"
  gateway_port: 9000
  gateway_token: "gt"
  parent_session_key: "agent:main:terminal:main"
  default_agent_id: "ops"
  max_buffer_lines: 1000
  max_context_chars: 50000
  command_wrap_markers: false
  auto_execute_low_risk: true
  profile_path: "/tmp/webterm_profiles.yaml"
""",
        )
    )
    assert cfg.webterm_bridge.enabled is True
    assert cfg.webterm_bridge.port == 9901
    assert cfg.webterm_bridge.gateway_port == 9000
    assert cfg.webterm_bridge.default_agent_id == "ops"
    assert cfg.webterm_bridge.command_wrap_markers is False
    assert cfg.webterm_bridge.auto_execute_low_risk is True
    assert cfg.webterm_bridge.profile_path == "/tmp/webterm_profiles.yaml"


def test_webterm_bridge_enabled_requires_token(tmp_path):
    with pytest.raises(ValueError, match="webterm_bridge.token is required"):
        Config.from_yaml(
            _write(
                tmp_path / "config.yaml",
                """
api_key: "k"
webterm_bridge:
  enabled: true
  token: ""
""",
            )
        )
