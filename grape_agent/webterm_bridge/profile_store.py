"""Profile-based domain knowledge for webterm bridge sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

import yaml


@dataclass(slots=True, frozen=True)
class WebtermProfile:
    """A host/scope/user matched profile with troubleshooting hints."""

    profile_id: str
    host_pattern: str = "*"
    scope_pattern: str = "*"
    user_pattern: str = "*"
    summary: str = ""
    log_paths: list[str] = field(default_factory=list)
    log_patterns: list[str] = field(default_factory=list)
    command_hints: list[str] = field(default_factory=list)
    notes: str = ""

    def matches(self, host: str, scope: str, user: str) -> bool:
        return (
            fnmatch(host, self.host_pattern or "*")
            and fnmatch(scope, self.scope_pattern or "*")
            and fnmatch(user, self.user_pattern or "*")
        )

    def specificity(self) -> int:
        score = 0
        for value in (self.host_pattern, self.scope_pattern, self.user_pattern):
            if value and value != "*":
                score += 1
        return score

    def to_context(self) -> str:
        lines = [f"profile_id: {self.profile_id}"]
        if self.summary:
            lines.append(f"summary: {self.summary}")
        if self.log_paths:
            lines.append("log_paths:")
            lines.extend([f"- {item}" for item in self.log_paths])
        if self.log_patterns:
            lines.append("log_patterns:")
            lines.extend([f"- {item}" for item in self.log_patterns])
        if self.command_hints:
            lines.append("command_hints:")
            lines.extend([f"- {item}" for item in self.command_hints])
        if self.notes:
            lines.append("notes:")
            lines.append(self.notes.strip())
        return "\n".join(lines)


def _to_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def load_profiles(profile_path: str) -> list[WebtermProfile]:
    """Load profile list from YAML. Returns empty list when file is absent/invalid."""
    path = Path(profile_path).expanduser()
    if not path.exists():
        return []

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []

    if isinstance(raw, dict):
        entries = raw.get("profiles", [])
    elif isinstance(raw, list):
        entries = raw
    else:
        entries = []

    profiles: list[WebtermProfile] = []
    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        match = item.get("match", {})
        match = match if isinstance(match, dict) else {}
        profile_id = str(item.get("id", f"profile_{idx + 1}")).strip() or f"profile_{idx + 1}"
        profile = WebtermProfile(
            profile_id=profile_id,
            host_pattern=str(match.get("host", item.get("host", "*"))).strip() or "*",
            scope_pattern=str(match.get("scope", item.get("scope", "*"))).strip() or "*",
            user_pattern=str(match.get("user", item.get("user", "*"))).strip() or "*",
            summary=str(item.get("summary", item.get("description", ""))).strip(),
            log_paths=_to_list(item.get("log_paths")),
            log_patterns=_to_list(item.get("log_patterns")),
            command_hints=_to_list(item.get("command_hints", item.get("commands"))),
            notes=str(item.get("notes", "")).strip(),
        )
        profiles.append(profile)
    return profiles


def resolve_profile_context(profiles: list[WebtermProfile], host: str, scope: str, user: str) -> str:
    """Resolve one best-match profile and render as prompt context."""
    matched = [p for p in profiles if p.matches(host, scope, user)]
    if not matched:
        return ""
    matched.sort(key=lambda item: item.specificity(), reverse=True)
    return matched[0].to_context()

