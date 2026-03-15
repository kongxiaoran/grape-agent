"""MemOS Cloud Memory Tool - Enhanced agent memory with MemOS SDK."""

from __future__ import annotations

import os
from typing import Any

from mini_agent.tools.base import Tool, ToolResult

# Lazy import to avoid startup errors if SDK not installed
_memos_client = None


def _get_client(api_key: str | None = None):
    """Get or create MemOS client singleton."""
    global _memos_client
    if _memos_client is None:
        try:
            from memos.api.client import MemOSClient
            _memos_client = MemOSClient(api_key=api_key or os.environ.get("MEMOS_API_KEY"))
        except ImportError:
            raise ImportError(
                "MemOS SDK not installed. Run: pip install MemoryOS -U"
            )
    return _memos_client


class MemOSAddMemoryTool(Tool):
    """Store conversation messages to MemOS Cloud."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("MEMOS_API_KEY")

    @property
    def name(self) -> str:
        return "memos_add_memory"

    @property
    def description(self) -> str:
        return (
            "Store conversation messages to MemOS cloud memory. "
            "MemOS will automatically abstract, process and save as memories. "
            "Use this to record important conversations, user preferences, decisions."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["user", "assistant"]},
                            "content": {"type": "string"},
                        },
                        "required": ["role", "content"],
                    },
                    "description": "List of conversation messages with role and content",
                },
                "user_id": {
                    "type": "string",
                    "description": "Unique user identifier",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "Conversation/session identifier (e.g., date like '0610')",
                },
            },
            "required": ["messages", "user_id"],
        }

    async def execute(
        self,
        messages: list[dict],
        user_id: str,
        conversation_id: str | None = None,
    ) -> ToolResult:
        if not self.api_key:
            return ToolResult(
                success=False,
                error="MEMOS_API_KEY not configured",
                content="",
            )

        try:
            client = _get_client(self.api_key)
            res = client.add_message(
                messages=messages,
                user_id=user_id,
                conversation_id=conversation_id or user_id,
            )
            return ToolResult(
                success=True,
                content=f"Memory stored successfully. Result: {res}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e), content="")


class MemOSSearchMemoryTool(Tool):
    """Search memories from MemOS Cloud."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("MEMOS_API_KEY")

    @property
    def name(self) -> str:
        return "memos_search_memory"

    @property
    def description(self) -> str:
        return (
            "Search relevant memories from MemOS cloud. "
            "MemOS will recall related memories to help personalize responses. "
            "Use this to recall user preferences, past conversations, decisions."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant memories",
                },
                "user_id": {
                    "type": "string",
                    "description": "Unique user identifier",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "Current conversation/session identifier",
                },
            },
            "required": ["query", "user_id"],
        }

    async def execute(
        self,
        query: str,
        user_id: str,
        conversation_id: str | None = None,
    ) -> ToolResult:
        if not self.api_key:
            return ToolResult(
                success=False,
                error="MEMOS_API_KEY not configured",
                content="",
            )

        try:
            client = _get_client(self.api_key)
            res = client.search_memory(
                query=query,
                user_id=user_id,
                conversation_id=conversation_id or user_id,
            )
            return ToolResult(
                success=True,
                content=f"Search result: {res}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e), content="")


class MemOSSimpleNoteTool(Tool):
    """Simple tool to store a single note to MemOS."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("MEMOS_API_KEY")

    @property
    def name(self) -> str:
        return "record_note"

    @property
    def description(self) -> str:
        return (
            "Record important information as a memory note. "
            "Use this to remember facts, user preferences, decisions, "
            "or any context that should persist across sessions."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to record as a memory",
                },
                "user_id": {
                    "type": "string",
                    "description": "User identifier (default: 'default_user')",
                },
            },
            "required": ["content"],
        }

    async def execute(
        self,
        content: str,
        user_id: str = "default_user",
    ) -> ToolResult:
        if not self.api_key:
            return ToolResult(
                success=False,
                error="MEMOS_API_KEY not configured",
                content="",
            )

        try:
            client = _get_client(self.api_key)
            # Wrap single content as a conversation message
            messages = [{"role": "user", "content": content}]
            res = client.add_message(
                messages=messages,
                user_id=user_id,
                conversation_id="notes",
            )
            return ToolResult(
                success=True,
                content=f"Note recorded: {content[:100]}...",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e), content="")


class MemOSRecallTool(Tool):
    """Simple tool to recall memories from MemOS."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("MEMOS_API_KEY")

    @property
    def name(self) -> str:
        return "recall_notes"

    @property
    def description(self) -> str:
        return (
            "Recall previously recorded memories. "
            "Use this to retrieve important information, context, or decisions."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant memories",
                },
                "user_id": {
                    "type": "string",
                    "description": "User identifier (default: 'default_user')",
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        user_id: str = "default_user",
    ) -> ToolResult:
        if not self.api_key:
            return ToolResult(
                success=False,
                error="MEMOS_API_KEY not configured",
                content="",
            )

        try:
            client = _get_client(self.api_key)
            res = client.search_memory(
                query=query,
                user_id=user_id,
                conversation_id="recall",
            )
            return ToolResult(
                success=True,
                content=f"Recalled memories: {res}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e), content="")


# Convenience function to create all MemOS tools
def create_memos_tools(api_key: str | None = None) -> list[Tool]:
    """Create all MemOS memory tools with the given API key."""
    return [
        MemOSSimpleNoteTool(api_key=api_key),
        MemOSRecallTool(api_key=api_key),
        MemOSAddMemoryTool(api_key=api_key),
        MemOSSearchMemoryTool(api_key=api_key),
    ]
