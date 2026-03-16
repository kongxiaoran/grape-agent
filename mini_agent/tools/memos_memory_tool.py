"""MemOS Cloud Memory Tool - Enhanced agent memory with MemOS SDK.

Installation:
    pip install grape-agent[memos]
    # or
    pip install MemoryOS

Usage:
    Set memos.enabled=true and memos.api_key in config.yaml
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
import warnings
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from typing import Any

from mini_agent.tools.base import Tool, ToolResult

# Lazy import to avoid startup errors if SDK not installed
_memos_clients: dict[str, Any] = {}
_memos_available = None


@contextmanager
def _suppress_memos_noise():
    """Suppress noisy third-party startup logs/warnings from MemOS dependencies."""
    logger_names = (
        "Lark",
        "memos",
        "memos.api",
        "memos.api.config",
        "memos.mem_reader",
        "memos.mem_reader.read_multi_modal.utils",
        "transformers",
    )
    logger_states: list[tuple[logging.Logger, int, bool, list[int]]] = []
    for name in logger_names:
        logger = logging.getLogger(name)
        logger_states.append((logger, logger.level, logger.propagate, [h.level for h in logger.handlers]))
        logger.setLevel(logging.ERROR)
        logger.propagate = False
        for handler in logger.handlers:
            try:
                handler.setLevel(logging.ERROR)
            except Exception:
                pass

    prev_transformers_verbosity = os.environ.get("TRANSFORMERS_VERBOSITY")
    prev_transformers_advisory = os.environ.get("TRANSFORMERS_NO_ADVISORY_WARNINGS")
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"
    os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"

    sink = io.StringIO()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="None of PyTorch, TensorFlow >= 2.0, or Flax.*")
        warnings.filterwarnings("ignore", message="Pydantic serializer warnings.*")
        warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
        with redirect_stdout(sink), redirect_stderr(sink):
            try:
                yield
            finally:
                if prev_transformers_verbosity is None:
                    os.environ.pop("TRANSFORMERS_VERBOSITY", None)
                else:
                    os.environ["TRANSFORMERS_VERBOSITY"] = prev_transformers_verbosity

                if prev_transformers_advisory is None:
                    os.environ.pop("TRANSFORMERS_NO_ADVISORY_WARNINGS", None)
                else:
                    os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = prev_transformers_advisory

                for logger, level, propagate, handler_levels in logger_states:
                    logger.setLevel(level)
                    logger.propagate = propagate
                    for handler, handler_level in zip(logger.handlers, handler_levels):
                        try:
                            handler.setLevel(handler_level)
                        except Exception:
                            pass


def _call_quietly(func, /, *args, **kwargs):
    """Call MemOS SDK APIs while suppressing noisy dependency output."""
    with _suppress_memos_noise():
        return func(*args, **kwargs)


def _check_memos_available() -> bool:
    """Check if MemOS SDK is available."""
    global _memos_available
    if _memos_available is None:
        try:
            with _suppress_memos_noise():
                from memos.api.client import MemOSClient  # noqa: F401
            _memos_available = True
        except ImportError:
            _memos_available = False
    return _memos_available


def _get_client(api_key: str | None = None):
    """Get or create MemOS client instance keyed by API key."""
    if not _check_memos_available():
        raise ImportError(
            "MemOS SDK not installed. Install with: pip install grape-agent[memos] or pip install MemoryOS"
        )
    resolved_api_key = str(api_key or os.environ.get("MEMOS_API_KEY") or "").strip()
    cache_key = resolved_api_key or "__default__"
    cached = _memos_clients.get(cache_key)
    if cached is not None:
        return cached

    with _suppress_memos_noise():
        from memos.api.client import MemOSClient

        client = MemOSClient(api_key=resolved_api_key or None)
    _memos_clients[cache_key] = client
    return client


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


def build_memos_conversation_id(
    channel: str | None = None,
    chat_id: str | None = None,
    sender_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Build stable MemOS conversation_id from session context."""
    if chat_id:
        if channel:
            return f"{channel}:{chat_id}"
        return chat_id
    if channel == "cli":
        return f"cli:{agent_id or 'default'}"
    if channel and sender_id:
        return f"{channel}:{sender_id}"
    if channel:
        return f"{channel}:default"
    return "default_conversation"


MEMOS_USER_QUERY_MARKER = "Original user query:\n"


def _to_plain_dict(value: Any) -> dict[str, Any]:
    """Best-effort conversion for pydantic model / dataclass-like objects."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="python")
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return dict(value.__dict__)
        except Exception:
            return {}
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return " ".join(text.split())


def _pick_text(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        candidate = _clean_text(item.get(key))
        if candidate:
            return candidate
    return ""


def _truncate(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def _format_timestamp(raw_value: Any) -> str:
    """Format common timestamp representations to YYYY-MM-DD HH:MM."""
    if raw_value in (None, ""):
        return ""
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if text.isdigit():
            raw_value = int(text)
        else:
            return text[:16]
    if isinstance(raw_value, (int, float)):
        value = float(raw_value)
        if value > 10_000_000_000:
            value = value / 1000.0
        try:
            import datetime as _dt

            return _dt.datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""
    return ""


class MemOSAutoMemoryHook:
    """OpenClaw-style auto memory lifecycle for one Agent session.

    - prepare_user_message: recall relevant memories and prepend context
    - record_turn: store (user, assistant) pair after successful turn
    """

    def __init__(
        self,
        *,
        api_key: str,
        user_id: str,
        conversation_id: str,
        channel: str | None = None,
        agent_id: str | None = None,
        query_prefix: str = "",
        auto_recall_enabled: bool = True,
        auto_add_enabled: bool = True,
        add_include_assistant: bool = True,
        add_async_mode: bool = True,
        add_throttle_sec: float = 0.0,
        recall_memory_limit_number: int = 6,
        recall_preference_limit_number: int = 4,
        recall_include_preference: bool = True,
        recall_include_tool_memory: bool = False,
        recall_tool_memory_limit_number: int = 4,
        recall_max_items: int = 8,
        recall_max_item_chars: int = 220,
        recall_min_relativity: float = 0.0,
        source: str = "grape-agent",
        tags: list[str] | None = None,
    ):
        self.api_key = api_key
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.channel = channel
        self.agent_id = agent_id
        self.query_prefix = query_prefix
        self.auto_recall_enabled = auto_recall_enabled
        self.auto_add_enabled = auto_add_enabled
        self.add_include_assistant = add_include_assistant
        self.add_async_mode = add_async_mode
        self.add_throttle_sec = max(0.0, float(add_throttle_sec))
        self.recall_memory_limit_number = max(1, int(recall_memory_limit_number))
        self.recall_preference_limit_number = max(0, int(recall_preference_limit_number))
        self.recall_include_preference = recall_include_preference
        self.recall_include_tool_memory = recall_include_tool_memory
        self.recall_tool_memory_limit_number = max(0, int(recall_tool_memory_limit_number))
        self.recall_max_items = max(1, int(recall_max_items))
        self.recall_max_item_chars = max(80, int(recall_max_item_chars))
        self.recall_min_relativity = float(recall_min_relativity)
        self.source = source or "grape-agent"
        self.tags = [tag for tag in (tags or []) if _clean_text(tag)]
        self._last_add_ts = 0.0

    @classmethod
    def from_config(
        cls,
        *,
        api_key: str,
        memos_config: Any,
        channel: str | None = None,
        chat_id: str | None = None,
        sender_id: str | None = None,
        agent_id: str | None = None,
    ) -> "MemOSAutoMemoryHook":
        user_id = build_memos_user_id(
            channel=channel,
            chat_id=chat_id,
            sender_id=sender_id,
            agent_id=agent_id,
        )
        conversation_override = _clean_text(getattr(memos_config, "conversation_id", ""))
        conversation_id = conversation_override or build_memos_conversation_id(
            channel=channel,
            chat_id=chat_id,
            sender_id=sender_id,
            agent_id=agent_id,
        )
        return cls(
            api_key=api_key,
            user_id=user_id,
            conversation_id=conversation_id,
            channel=channel,
            agent_id=agent_id,
            query_prefix=_clean_text(getattr(memos_config, "query_prefix", "")),
            auto_recall_enabled=bool(getattr(memos_config, "auto_recall_enabled", True)),
            auto_add_enabled=bool(getattr(memos_config, "auto_add_enabled", True)),
            add_include_assistant=bool(getattr(memos_config, "add_include_assistant", True)),
            add_async_mode=bool(getattr(memos_config, "add_async_mode", True)),
            add_throttle_sec=float(getattr(memos_config, "add_throttle_sec", 0.0) or 0.0),
            recall_memory_limit_number=int(getattr(memos_config, "recall_memory_limit_number", 6) or 6),
            recall_preference_limit_number=int(getattr(memos_config, "recall_preference_limit_number", 4) or 4),
            recall_include_preference=bool(getattr(memos_config, "recall_include_preference", True)),
            recall_include_tool_memory=bool(getattr(memos_config, "recall_include_tool_memory", False)),
            recall_tool_memory_limit_number=int(getattr(memos_config, "recall_tool_memory_limit_number", 4) or 4),
            recall_max_items=int(getattr(memos_config, "recall_max_items", 8) or 8),
            recall_max_item_chars=int(getattr(memos_config, "recall_max_item_chars", 220) or 220),
            recall_min_relativity=float(getattr(memos_config, "recall_min_relativity", 0.0) or 0.0),
            source=_clean_text(getattr(memos_config, "source", "grape-agent")) or "grape-agent",
            tags=list(getattr(memos_config, "tags", []) or []),
        )

    async def prepare_user_message(self, user_query: str) -> str:
        """Return augmented user text with recalled memory context."""
        clean_query = _clean_text(user_query)
        if not clean_query or not self.auto_recall_enabled:
            return user_query

        try:
            client = _get_client(self.api_key)
            query = f"{self.query_prefix} {clean_query}".strip() if self.query_prefix else clean_query
            result = await asyncio.to_thread(
                _call_quietly,
                client.search_memory,
                query=query,
                user_id=self.user_id,
                conversation_id=self.conversation_id,
                memory_limit_number=self.recall_memory_limit_number,
                include_preference=self.recall_include_preference,
                include_tool_memory=self.recall_include_tool_memory,
                preference_limit_number=self.recall_preference_limit_number,
                tool_memory_limit_number=self.recall_tool_memory_limit_number,
                source=self.source,
            )
            memory_block = self._build_recall_block(result)
            if not memory_block:
                return user_query
            return f"{memory_block}\n\n{MEMOS_USER_QUERY_MARKER}{clean_query}"
        except Exception:
            return user_query

    async def record_turn(self, user_query: str, assistant_response: str, *, success: bool = True) -> None:
        """Persist one successful turn to MemOS."""
        if not success or not self.auto_add_enabled:
            return

        clean_query = _clean_text(user_query)
        if not clean_query:
            return

        now = time.time()
        if self.add_throttle_sec > 0 and now - self._last_add_ts < self.add_throttle_sec:
            return

        messages = [{"role": "user", "content": clean_query}]
        clean_assistant = _clean_text(assistant_response)
        if self.add_include_assistant and clean_assistant:
            messages.append({"role": "assistant", "content": clean_assistant})

        client = _get_client(self.api_key)
        await asyncio.to_thread(
            _call_quietly,
            client.add_message,
            messages=messages,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            source=self.source,
            agent_id=self.agent_id,
            async_mode=self.add_async_mode,
            tags=self.tags or None,
        )
        self._last_add_ts = now

    def _build_recall_block(self, search_result: Any) -> str:
        data = self._extract_search_data(search_result)
        if not data:
            return ""

        fact_lines = self._extract_lines(
            data.get("memory_detail_list"),
            text_keys=(
                "memory_value",
                "memory_key",
                "content",
                "text",
                "summary",
                "value",
            ),
        )
        # Fallback for providers returning message style details only.
        if not fact_lines:
            fact_lines = self._extract_lines(
                data.get("message_detail_list"),
                text_keys=("content", "text", "summary", "value", "memory_value"),
            )

        pref_lines: list[str] = []
        if self.recall_include_preference:
            pref_lines = self._extract_lines(
                data.get("preference_detail_list"),
                text_keys=("preference", "content", "text", "summary", "value"),
            )

        tool_lines: list[str] = []
        if self.recall_include_tool_memory:
            tool_lines = self._extract_lines(
                data.get("tool_memory_detail_list"),
                text_keys=("tool_value", "content", "text", "summary", "value"),
            )

        has_memory = bool(fact_lines or pref_lines or tool_lines)
        if not has_memory:
            return ""

        lines: list[str] = ["<memories>"]
        if fact_lines:
            lines.append("  <facts>")
            for text in fact_lines:
                lines.append(f"   - {text}")
            lines.append("  </facts>")

        if pref_lines:
            lines.append("  <preferences>")
            for text in pref_lines:
                lines.append(f"   - {text}")
            lines.append("  </preferences>")

        if tool_lines:
            lines.append("  <tool_memories>")
            for text in tool_lines:
                lines.append(f"   - {text}")
            lines.append("  </tool_memories>")

        lines.append("</memories>")
        return "\n".join(lines)

    def _extract_search_data(self, search_result: Any) -> dict[str, Any]:
        if search_result is None:
            return {}
        result_dict = _to_plain_dict(search_result)
        raw_data = result_dict.get("data")
        if raw_data is None and hasattr(search_result, "data"):
            raw_data = getattr(search_result, "data")
        data_dict = _to_plain_dict(raw_data)
        return data_dict if isinstance(data_dict, dict) else {}

    def _extract_lines(self, raw_items: Any, *, text_keys: tuple[str, ...]) -> list[str]:
        lines: list[str] = []
        for entry in _as_list(raw_items):
            item = _to_plain_dict(entry)
            if not item:
                continue
            relativity = item.get("relativity")
            if isinstance(relativity, (int, float)) and float(relativity) < self.recall_min_relativity:
                continue

            text = _pick_text(item, text_keys)
            if not text:
                continue
            text = _truncate(text, self.recall_max_item_chars)
            ts = _format_timestamp(
                item.get("create_time")
                or item.get("created_at")
                or item.get("timestamp")
                or item.get("time")
            )
            if ts:
                text = f"[{ts}] {text}"
            lines.append(text)
            if len(lines) >= self.recall_max_items:
                break
        return lines


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
            res = _call_quietly(
                client.add_message,
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
            res = _call_quietly(
                client.search_memory,
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
        return "memos_record_note"

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
            res = _call_quietly(
                client.add_message,
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
        return "memos_recall_notes"

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
            res = _call_quietly(
                client.search_memory,
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
        return "memos_record_note"

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
            res = _call_quietly(
                client.add_message,
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
        return "memos_recall_notes"

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
            res = _call_quietly(
                client.search_memory,
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
