"""Tests for native web search config parsing."""

from pathlib import Path

from grape_agent.config import Config


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_native_web_search_defaults(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
""",
    )
    cfg = Config.from_yaml(config_path)
    assert cfg.llm.native_web_search.enabled is True
    assert cfg.llm.native_web_search.model_patterns == ["glm-5"]
    assert cfg.llm.native_web_search.tool_type == "web_search"
    assert cfg.llm.native_web_search.web_search == {"enable": "True"}


def test_native_web_search_custom_values(tmp_path):
    config_path = _write_config(
        tmp_path / "config.yaml",
        """
api_key: "test-key"
native_web_search:
  enabled: true
  model_patterns: ["glm-5", "glm-4.5"]
  tool_type: "web_search"
  web_search:
    enable: "True"
    search_result: true
""",
    )
    cfg = Config.from_yaml(config_path)
    assert cfg.llm.native_web_search.enabled is True
    assert cfg.llm.native_web_search.model_patterns == ["glm-5", "glm-4.5"]
    assert cfg.llm.native_web_search.web_search == {"enable": "True", "search_result": True}
