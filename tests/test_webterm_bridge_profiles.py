"""Tests for webterm bridge profile loading and matching."""

from mini_agent.webterm_bridge.profile_store import load_profiles, resolve_profile_context


def test_load_profiles_and_resolve(tmp_path):
    path = tmp_path / "profiles.yaml"
    path.write_text(
        """
profiles:
  - id: default
    match:
      host: "*"
      scope: "*"
      user: "*"
    summary: "default profile"
    log_paths:
      - "/var/log/messages"
  - id: prod-log
    match:
      host: "example-bastion.local"
      scope: "example-log-center"
      user: "example-user"
    summary: "example service logs"
    log_paths:
      - "/data/logs/example-service/app.log"
    command_hints:
      - "grep -nE 'ERROR|Exception' /data/logs/example-service/app.log | tail -n 200"
""",
        encoding="utf-8",
    )

    profiles = load_profiles(str(path))
    assert len(profiles) == 2

    context = resolve_profile_context(profiles, "example-bastion.local", "example-log-center", "example-user")
    assert "profile_id: prod-log" in context
    assert "/data/logs/example-service/app.log" in context
