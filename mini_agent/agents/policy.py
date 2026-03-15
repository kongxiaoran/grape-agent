"""Subagent orchestration policy."""

from __future__ import annotations

from dataclasses import dataclass

from mini_agent.config import Config


@dataclass(slots=True, frozen=True)
class SubagentPolicy:
    """Policy controls for subagent orchestration."""

    enabled: bool = True
    max_depth: int = 2
    deny_tools_leaf: tuple[str, ...] = (
        "sessions_spawn",
        "sessions_list",
        "sessions_history",
        "sessions_send",
    )

    @classmethod
    def from_config(cls, config: Config) -> "SubagentPolicy":
        raw = config.subagents
        return cls(
            enabled=raw.enabled,
            max_depth=max(0, int(raw.max_depth)),
            deny_tools_leaf=tuple(raw.deny_tools_leaf),
        )

    def can_spawn(self, depth: int) -> bool:
        if not self.enabled:
            return False
        return int(depth) < self.max_depth

    def is_leaf(self, depth: int) -> bool:
        return int(depth) >= self.max_depth
