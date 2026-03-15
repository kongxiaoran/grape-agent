"""MemOS Cloud Memory Tool - Enhanced agent memory with MemOS SDK.

Installation:
    pip install grape-agent[memos]
    # or
    pip install MemoryOS

Usage:
    Set memos.enabled=true and memos.api_key in config.yaml
"""

from __future__ import annotations

import os
from typing import Any

from mini_agent.tools.base import Tool, ToolResult

# Lazy import to avoid startup errors if SDK not installed
_memos_client = None
_memos_available = None


def _check_memos_available() -> bool:
    """Check if MemOS SDK is available."""
    global _memos_available
    if _memos_available is None:
        try:
            from memos.api.client import MemOSClient  # noqa: F401
            _memos_available = True
        except ImportError:
            _memos_available = False
    return _memos_available


def _get_client(api_key: str | None = None):
    """Get or create MemOS client singleton."""
    global _memos_client
    if not _check_memos_available():
        raise ImportError(
            "MemOS SDK not installed. Install with: pip install grape-agent[memos] or pip install MemoryOS"
        )
    if _memos_client is None:
        from memos.api.client import MemOSClient
        _memos_client = MemOSClient(api_key=api_key or os.environ.get("MEMOS_API_KEY"))
    return _memos_client


def build_memos_user_id(
    channel: str | None = None,
    chat_id: str | None = None,
    sender_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Build MemOS user_id from session context.

    Memory isolation strategy:
    - CLI: "cli:{agent_id}"
    - Feishu direct: "feishu:{sender_open_id}"
    - Feishu group: "feishu:{chat_id}:{sender_open_id}"
    - Generic: "channel:{channel}:{chat_id}"

    Args:
        channel: Channel type (cli, feishu, webterm, etc.)
        chat_id: Chat/conversation ID
        sender_id: Sender/user ID within the channel
        agent_id: Agent ID for CLI sessions

    Returns:
        MemOS user_id string
    """
    if channel == "feishu":
        if chat_id and sender_id:
            # Group chat: isolate per user within group
            return f"feishu:{chat_id}:{sender_id}"
        elif sender_id:
            # Direct message: per-user isolation
            return f"feishu:{sender_id}"
        elif chat_id:
            # Fallback to chat-level isolation
            return f"feishu:{chat_id}"
    elif channel == "cli":
        return f"cli:{agent_id or 'default'}"
    elif channel == "webterm":
        return f"webterm:{chat_id or 'default'}"
    elif channel:
        # Generic channel isolation
        if chat_id and sender_id:
            return f"{channel}:{chat_id}:{sender_id}"
        elif chat_id:
            return f"{channel}:{chat_id}"
        return f"{channel}:default"

    # Ultimate fallback
    return "default_user"


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


class ContextAwareMemOSNoteTool(Tool):
    """Context-aware note tool that auto-determines user_id from session context."""

    def __init__(
        self,
        api_key: str | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        sender_id: str | None = None,
        agent_id: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("MEMOS_API_KEY")
        self._channel = channel
        self._chat_id = chat_id
        self._sender_id = sender_id
        self._agent_id = agent_id
        self._user_id = build_memos_user_id(
            channel=channel,
            chat_id=chat_id,
            sender_id=sender_id,
            agent_id=agent_id,
        )

    @property
    def name(self) -> str:
        return "record_note"

    @property
    def description(self) -> str:
        return (
            f"Record important information as a memory note for user '{self._user_id}'. "
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
            },
            "required": ["content"],
        }

    async def execute(self, content: str) -> ToolResult:
        if not self.api_key:
            return ToolResult(
                success=False,
                error="MEMOS_API_KEY not configured",
                content="",
            )

        try:
            client = _get_client(self.api_key)
            messages = [{"role": "user", "content": content}]
            res = client.add_message(
                messages=messages,
                user_id=self._user_id,
                conversation_id="notes",
            )
            return ToolResult(
                success=True,
                content=f"Note recorded for {self._user_id}: {content[:100]}...",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e), content="")


class ContextAwareMemOSRecallTool(Tool):
    """Context-aware recall tool that auto-determines user_id from session context."""

    def __init__(
        self,
        api_key: str | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        sender_id: str | None = None,
        agent_id: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("MEMOS_API_KEY")
        self._channel = channel
        self._chat_id = chat_id
        self._sender_id = sender_id
        self._agent_id = agent_id
        self._user_id = build_memos_user_id(
            channel=channel,
            chat_id=chat_id,
            sender_id=sender_id,
            agent_id=agent_id,
        )

    @property
    def name(self) -> str:
        return "recall_notes"

    @property
    def description(self) -> str:
        return (
            f"Recall previously recorded memories for user '{self._user_id}'. "
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
            },
            "required": ["query"],
        }

    async def execute(self, query: str) -> ToolResult:
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
                user_id=self._user_id,
                conversation_id="recall",
            )
            return ToolResult(
                success=True,
                content=f"Recalled memories for {self._user_id}: {res}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e), content="")


def create_memos_tools_with_context(
    api_key: str | None = None,
    channel: str | None = None,
    chat_id: str | None = None,
    sender_id: str | None = None,
    agent_id: str | None = None,
) -> list[Tool]:
    """Create MemOS tools with session context for automatic user_id determination.

    This is the recommended way to create MemOS tools for multi-channel scenarios.
    The tools will automatically use the correct user_id based on channel context.

    Args:
        api_key: MemOS API key
        channel: Channel type (cli, feishu, webterm, etc.)
        chat_id: Chat/conversation ID
        sender_id: Sender/user ID within the channel
        agent_id: Agent ID for CLI sessions

    Returns:
        List of context-aware MemOS tools

    Example:
        # For Feishu group chat
        tools = create_memos_tools_with_context(
            api_key="mpg-xxx",
            channel="feishu",
            chat_id="oc_xxx",
            sender_id="ou_xxx",
        )

        # For CLI
        tools = create_memos_tools_with_context(
            api_key="mpg-xxx",
            channel="cli",
            agent_id="main",
        )
    """
    return [
        ContextAwareMemOSNoteTool(
            api_key=api_key,
            channel=channel,
            chat_id=chat_id,
            sender_id=sender_id,
            agent_id=agent_id,
        ),
        ContextAwareMemOSRecallTool(
            api_key=api_key,
            channel=channel,
            chat_id=chat_id,
            sender_id=sender_id,
            agent_id=agent_id,
        ),
    ]

