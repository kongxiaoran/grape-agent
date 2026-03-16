"""Tool: spawn subagent sessions."""

from __future__ import annotations

import json
from typing import Any

from grape_agent.agents.orchestrator import SessionOrchestrator
from grape_agent.tools.base import Tool, ToolResult


class SessionsSpawnTool(Tool):
    """Spawn a child session for delegated execution."""

    def __init__(self, orchestrator: SessionOrchestrator, parent_session_key: str):
        self._orchestrator = orchestrator
        self._parent_session_key = parent_session_key

    @property
    def name(self) -> str:
        return "sessions_spawn"

    @property
    def description(self) -> str:
        return (
            "Create or run a child session. "
            "Use mode='run' to dispatch task immediately, or mode='create' for empty child session."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task text for child session."},
                "agent_id": {"type": "string", "description": "Optional target agent id."},
                "mode": {
                    "type": "string",
                    "enum": ["run", "create"],
                    "default": "run",
                    "description": "run=create+dispatch, create=only create child session.",
                },
                "wait": {"type": "boolean", "default": False, "description": "Wait for run completion when mode=run."},
            },
            "required": ["task"],
        }

    async def execute(
        self,
        task: str,
        agent_id: str | None = None,
        mode: str = "run",
        wait: bool = False,
    ) -> ToolResult:
        result = await self._orchestrator.spawn(
            parent_session_key=self._parent_session_key,
            task=task,
            agent_id=agent_id,
            mode=mode,
            wait=wait,
        )
        if not result.get("ok"):
            return ToolResult(success=False, error=result.get("error", "spawn failed"), content="")
        return ToolResult(success=True, content=json.dumps(result, ensure_ascii=False, indent=2))
