"""Agent profile models for multi-agent routing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class AgentProfile:
    """Resolved runtime profile for one logical agent."""

    id: str
    workspace: Path
    model: str | None = None
    system_prompt_path: str | None = None
