"""Tool: inspect session history."""

from __future__ import annotations

import json
from typing import Any

from grape_agent.agents.orchestrator import SessionOrchestrator
from grape_agent.tools.base import Tool, ToolResult


class SessionsHistoryTool(Tool):
    """Fetch sanitized history from an accessible session."""

    def __init__(self, orchestrator: SessionOrchestrator, owner_session_key: str):
        self._orchestrator = orchestrator
        self._owner_session_key = owner_session_key

    @property
    def name(self) -> str:
        return "sessions_history"

    @property
    def description(self) -> str:
        return "Read sanitized history from a session key that is accessible to current session."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_key": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            },
            "required": ["session_key"],
        }

    async def execute(self, session_key: str, limit: int = 50) -> ToolResult:
        if not self._orchestrator.is_accessible(self._owner_session_key, session_key):
            return ToolResult(success=False, error=f"access denied: {session_key}", content="")

        result = self._orchestrator.history(session_key=session_key, limit=limit)
        if not result.get("ok"):
            return ToolResult(success=False, error=result.get("error", "history failed"), content="")
        return ToolResult(success=True, content=json.dumps(result, ensure_ascii=False, indent=2))
