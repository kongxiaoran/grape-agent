"""Tool: send message to a session."""

from __future__ import annotations

import json
from typing import Any

from mini_agent.agents.orchestrator import SessionOrchestrator
from mini_agent.tools.base import Tool, ToolResult


class SessionsSendTool(Tool):
    """Dispatch message to an existing accessible session."""

    def __init__(self, orchestrator: SessionOrchestrator, owner_session_key: str):
        self._orchestrator = orchestrator
        self._owner_session_key = owner_session_key

    @property
    def name(self) -> str:
        return "sessions_send"

    @property
    def description(self) -> str:
        return "Send a message to an accessible session key, optionally waiting for completion."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_key": {"type": "string"},
                "message": {"type": "string"},
                "wait": {"type": "boolean", "default": False},
            },
            "required": ["session_key", "message"],
        }

    async def execute(self, session_key: str, message: str, wait: bool = False) -> ToolResult:
        if not self._orchestrator.is_accessible(self._owner_session_key, session_key):
            return ToolResult(success=False, error=f"access denied: {session_key}", content="")

        result = await self._orchestrator.send(session_key=session_key, message=message, wait=wait)
        if not result.get("ok"):
            return ToolResult(success=False, error=result.get("error", "send failed"), content="")
        return ToolResult(success=True, content=json.dumps(result, ensure_ascii=False, indent=2))
