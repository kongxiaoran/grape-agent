"""Tests for UI config parsing."""

from pathlib import Path

from grape_agent.config import Config


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_ui_config_defaults(tmp_path):
    cfg = Config.from_yaml(_write(tmp_path / "config.yaml", 'api_key: "k"\n'))
    assert cfg.ui.style == "claude"
    assert cfg.ui.show_thinking is True
    assert cfg.ui.show_tool_args is False
    assert cfg.ui.show_timing is False
    assert cfg.ui.show_steps is False
    assert cfg.ui.render_markdown is True


def test_ui_config_custom_values(tmp_path):
    cfg = Config.from_yaml(
        _write(
            tmp_path / "config.yaml",
            """
api_key: "k"
ui:
  style: "compact"
  show_thinking: false
  show_tool_args: true
  show_timing: true
  show_steps: true
  render_markdown: false
""",
        )
    )
    assert cfg.ui.style == "compact"
    assert cfg.ui.show_thinking is False
    assert cfg.ui.show_tool_args is True
    assert cfg.ui.show_timing is True
    assert cfg.ui.show_steps is True
    assert cfg.ui.render_markdown is False
