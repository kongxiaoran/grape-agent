"""Tool: list accessible sessions."""

from __future__ import annotations

import json
from typing import Any

from mini_agent.agents.orchestrator import SessionOrchestrator
from mini_agent.tools.base import Tool, ToolResult


class SessionsListTool(Tool):
    """List child sessions visible to current session."""

    def __init__(self, orchestrator: SessionOrchestrator, owner_session_key: str):
        self._orchestrator = orchestrator
        self._owner_session_key = owner_session_key

    @property
    def name(self) -> str:
        return "sessions_list"

    @property
    def description(self) -> str:
        return "List sessions accessible from current session (self + descendants)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "agent_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            },
        }

    async def execute(self, channel: str | None = None, agent_id: str | None = None, limit: int = 20) -> ToolResult:
        items = self._orchestrator.list_accessible_sessions(
            owner_session_key=self._owner_session_key,
            channel=channel,
            agent_id=agent_id,
            limit=limit,
        )
        payload = {"total": len(items), "items": items}
        return ToolResult(success=True, content=json.dumps(payload, ensure_ascii=False, indent=2))
