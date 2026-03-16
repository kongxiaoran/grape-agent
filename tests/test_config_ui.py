"""Tests for UI config parsing."""

import json
from pathlib import Path

from grape_agent.config import Config


def _write(path: Path, content: dict) -> Path:
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_ui_config_defaults(tmp_path):
    cfg = Config.from_json(_write(tmp_path / "settings.json", {"api_key": "k"}))
    assert cfg.ui.style == "claude"
    assert cfg.ui.show_thinking is True
    assert cfg.ui.show_tool_args is False
    assert cfg.ui.show_timing is False
    assert cfg.ui.show_steps is False
    assert cfg.ui.render_markdown is True


def test_ui_config_custom_values(tmp_path):
    cfg = Config.from_json(
        _write(
            tmp_path / "settings.json",
            {
                "api_key": "k",
                "ui": {
                    "style": "compact",
                    "show_thinking": False,
                    "show_tool_args": True,
                    "show_timing": True,
                    "show_steps": True,
                    "render_markdown": False,
                },
            },
        )
    )
    assert cfg.ui.style == "compact"
    assert cfg.ui.show_thinking is False
    assert cfg.ui.show_tool_args is True
    assert cfg.ui.show_timing is True
    assert cfg.ui.show_steps is True
    assert cfg.ui.render_markdown is False
