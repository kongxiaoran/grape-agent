from pathlib import Path

from mini_agent.cli import resolve_cli_user_id


def test_resolve_cli_user_id_prefers_cli_arg(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GRAPE_USER_ID", "from-env")

    value = resolve_cli_user_id("from-cli")
    assert value == "from-cli"


def test_resolve_cli_user_id_falls_back_to_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GRAPE_USER_ID", "env user")

    value = resolve_cli_user_id(None)
    assert value == "env_user"


def test_resolve_cli_user_id_reads_persisted_value(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("GRAPE_USER_ID", raising=False)
    user_file = tmp_path / ".grape" / "user_id"
    user_file.parent.mkdir(parents=True, exist_ok=True)
    user_file.write_text("persisted-user\n", encoding="utf-8")

    value = resolve_cli_user_id(None)
    assert value == "persisted-user"


def test_resolve_cli_user_id_generates_and_persists(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("GRAPE_USER_ID", raising=False)

    value = resolve_cli_user_id(None)
    assert value.startswith("u_")

    user_file = tmp_path / ".grape" / "user_id"
    assert user_file.exists()
    assert user_file.read_text(encoding="utf-8").strip() == value
