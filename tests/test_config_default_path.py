"""Tests for default config path resolution."""

from pathlib import Path

from grape_agent.config import Config


def test_default_config_prefers_grape_user_settings(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True)
    grape_dir = home / ".grape"
    grape_dir.mkdir(parents=True)
    settings = grape_dir / "settings.json"
    settings.write_text('{"api_key":"k"}', encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: home)

    resolved = Config.get_default_config_path()
    assert resolved == settings


def test_default_config_falls_back_to_legacy_yaml_before_template(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    project_root = tmp_path / "project"
    dev_cfg_dir = project_root / "grape_agent" / "config"
    dev_cfg_dir.mkdir(parents=True)

    legacy_yaml = dev_cfg_dir / "config.yaml"
    legacy_yaml.write_text('api_key: "k"\n', encoding="utf-8")

    # Package template exists but should not override existing legacy config.
    settings_json = dev_cfg_dir / "settings.json"
    settings_json.write_text('{"api_key":"YOUR_API_KEY_HERE"}', encoding="utf-8")

    monkeypatch.chdir(project_root)
    resolved = Config.get_default_config_path()
    assert resolved == legacy_yaml
