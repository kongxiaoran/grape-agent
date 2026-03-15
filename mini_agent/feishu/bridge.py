"""Bridge Feishu events to Grape-Agent sessions."""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, strftime
from typing import Any

from mini_agent.agent import Agent
from mini_agent.agents import AgentRegistry, SessionOrchestrator
from mini_agent.channels.plugins.feishu.policy import resolve_session_scope_id
from mini_agent.channels.plugins.feishu.streaming import FeishuChunkStreamer
from mini_agent.channels.plugins.feishu.threading import resolve_reply_in_thread
from mini_agent.channels.logging import log_channel_event
from mini_agent.config import Config, FeishuPolicyConfig
from mini_agent.runtime_factory import add_workspace_tools, build_runtime_bundle
from mini_agent.routing import RoutingInput, RoutingResolver
from mini_agent.session_store import AgentSession, AgentSessionStore
from mini_agent.tools.mcp_loader import cleanup_mcp_connections
from mini_agent.tools.sessions_history_tool import SessionsHistoryTool
from mini_agent.tools.sessions_list_tool import SessionsListTool
from mini_agent.tools.sessions_send_tool import SessionsSendTool
from mini_agent.tools.sessions_spawn_tool import SessionsSpawnTool

from .client import FeishuClient
from .dedup import FeishuMessageDedup
from .message_utils import chunk_text, parse_incoming_event, strip_bot_mentions
from .rendering import build_markdown_card, build_payload_by_type, build_progress_card, build_text_payload, resolve_message_type
from .types import FeishuChatType, FeishuIncomingMessage, FeishuSendResult


@dataclass
class _ProgressCardState:
    started_at: float
    next_message_index: int
    history: list[str]  # All messages for collapsible panel
    recent: deque[str]  # Recent messages to always show
    recent_limit: int  # Number of recent messages to display
    card_message_id: str | None = None


class FeishuAgentBridge:
    """High-level message bridge for Feishu bot and Agent runtime."""

    def __init__(
        self,
        feishu_client: FeishuClient,
        agent_config: Config,
        workspace_root: Path | None = None,
        account_id: str | None = None,
        group_require_mention: bool = True,
        group_session_scope: str = "group",
        reply_in_thread: bool = True,
        session_store: AgentSessionStore | None = None,
        subagent_orchestrator: SessionOrchestrator | None = None,
        on_inbound_message=None,
    ):
        self.feishu_client = feishu_client
        self.agent_config = agent_config
        self.workspace_root = workspace_root or Path.home() / ".grape-agent" / "feishu_workspaces"
        self.account_id = account_id or feishu_client.app_id
        self._policy = FeishuPolicyConfig(
            require_mention=group_require_mention,
            reply_in_thread=reply_in_thread,
            group_session_scope=group_session_scope,
        )
        self.group_require_mention = self._policy.require_mention
        self.group_session_scope = self._policy.group_session_scope
        self.reply_in_thread = self._policy.reply_in_thread
        self.render_mode = self.agent_config.channels.feishu.render_mode
        self.streaming_config = self.agent_config.channels.feishu.streaming
        self.progress_ping_sec = self.streaming_config.progress_ping_sec
        self.agent_registry = AgentRegistry(agent_config, default_workspace=self.workspace_root)
        self.routing_resolver = RoutingResolver.from_config(
            agent_config,
            default_agent_id=self.agent_registry.default_agent_id,
        )

        self.workspace_root.mkdir(parents=True, exist_ok=True)

        dedup_file = Path.home() / ".grape-agent" / "feishu" / "dedup.json"
        self.dedup = FeishuMessageDedup(dedup_file)

        self._runtime_by_agent: dict[str, object] = {}
        self._session_store = session_store or AgentSessionStore()
        self._subagent_orchestrator = subagent_orchestrator
        self._on_inbound_message = on_inbound_message

    async def initialize(self) -> None:
        """Initialize shared runtime bundle for Feishu sessions."""
        default_profile = self.agent_registry.get(self.agent_registry.default_agent_id)
        await self._get_or_create_runtime_bundle(default_profile.id)
        log_channel_event(
            "feishu",
            "bridge.runtime.init",
            default_agent=default_profile.id,
            profile_count=len(self.agent_registry.all()),
        )

    async def _get_or_create_runtime_bundle(self, agent_id: str):
        existing = self._runtime_by_agent.get(agent_id)
        if existing is not None:
            return existing

        def _log(message: str) -> None:
            log_channel_event("feishu", "bridge.runtime", agent_id=agent_id, message=message)

        profile = self.agent_registry.get(agent_id)
        runtime_config = self.agent_config.model_copy(deep=True)
        if profile.model:
            runtime_config.llm.model = profile.model
        if profile.system_prompt_path:
            runtime_config.agent.system_prompt_path = profile.system_prompt_path

        built = await build_runtime_bundle(config=runtime_config, log=_log)
        self._runtime_by_agent[agent_id] = built
        return built

    async def shutdown(self) -> None:
        """Cleanup long-lived resources."""
        await cleanup_mcp_connections()

    async def handle_event(self, event_data: dict) -> None:
        """Entry point from WS callback."""
        inbound = parse_incoming_event(event_data, bot_open_id=self.feishu_client.bot_open_id)
        if inbound is None:
            log_channel_event("feishu", "bridge.event.skipped", reason="parse_failed")
            return

        dedup_key = f"{inbound.chat_id}:{inbound.message_id}"
        if self.dedup.seen_or_record(dedup_key):
            log_channel_event("feishu", "bridge.event.skipped", reason="duplicate", dedup_key=dedup_key)
            return

        # Ignore bot self-messages.
        if self.feishu_client.bot_open_id and inbound.sender_open_id == self.feishu_client.bot_open_id:
            log_channel_event("feishu", "bridge.event.skipped", reason="self_message", dedup_key=dedup_key)
            return

        if (
            inbound.chat_type == FeishuChatType.GROUP
            and self.group_require_mention
            and not inbound.mentioned_bot
        ):
            log_channel_event("feishu", "bridge.event.skipped", reason="group_without_mention", dedup_key=dedup_key)
            return

        cleaned = strip_bot_mentions(inbound.content, inbound.mentions, self.feishu_client.bot_open_id)
        if not cleaned:
            log_channel_event("feishu", "bridge.event.skipped", reason="empty_after_strip", dedup_key=dedup_key)
            await self._reply(inbound, "我在，请直接发送任务内容。")
            return

        if self._on_inbound_message is not None:
            sender = inbound.sender_name or inbound.sender_open_id or "unknown"
            preview = cleaned.strip()
            self._on_inbound_message(f"Feishu {sender}: {preview}")

        if cleaned.lower() in {"/clear", "/reset", "/new"}:
            self.clear_session(inbound.chat_id)
            await self._reply(inbound, "会话已重置。")
            return

        log_channel_event("feishu", "bridge.process.begin", dedup_key=dedup_key, content_preview=cleaned[:80])
        await self._send_processing_ack(inbound)

        route = self._resolve_route(inbound)
        session_scope_id = resolve_session_scope_id(inbound, self._policy)
        if session_scope_id != inbound.chat_id:
            log_channel_event(
                "feishu",
                "bridge.session.scope",
                account_id=self.account_id,
                policy=self.group_session_scope,
                chat_id=inbound.chat_id,
                scoped_id=session_scope_id,
            )
        session = await self._get_or_create_session(route.agent_id, route.channel, session_scope_id)
        async with session.lock:
            user_text = self._build_user_message(inbound, cleaned)
            session.agent.add_user_message(user_text)

            try:
                result = await self._run_agent_with_progress_ping(session, inbound)
            except Exception as exc:
                log_channel_event("feishu", "bridge.process.error", dedup_key=dedup_key, error=f"{type(exc).__name__}: {exc}")
                await self._reply(inbound, f"处理失败：{type(exc).__name__}: {exc}")
                return

            final_text = result.strip() if isinstance(result, str) else str(result)
            if not final_text:
                final_text = "任务执行完成。"

            await self._send_chunked_reply(inbound, final_text)

    def _resolve_route(self, inbound: FeishuIncomingMessage):
        route_input = RoutingInput(
            channel="feishu",
            account_id=self.account_id,
            chat_id=inbound.chat_id,
            chat_type="group" if inbound.chat_type == FeishuChatType.GROUP else "direct",
        )
        result = self.routing_resolver.resolve(route_input)
        log_channel_event(
            "feishu",
            "bridge.route",
            account_id=self.account_id,
            agent_id=result.agent_id,
            session_key=result.session_key,
            matched_by=result.matched_by,
            chat_id=inbound.chat_id,
        )
        return result

    async def _run_agent_with_progress_ping(self, session: AgentSession, inbound: FeishuIncomingMessage):
        if not self._is_progress_card_enabled() and self.progress_ping_sec <= 0:
            return await session.agent.run()

        progress_task: asyncio.Task | None = None
        progress_state: _ProgressCardState | None = None
        if self._is_progress_card_enabled():
            recent_limit = max(1, int(getattr(self.streaming_config, "progress_card_tail_lines", 5)))
            progress_state = _ProgressCardState(
                started_at=perf_counter(),
                next_message_index=len(session.agent.messages),
                history=[],
                recent=deque(maxlen=recent_limit),
                recent_limit=recent_limit,
            )
            progress_task = asyncio.create_task(self._progress_card_loop(session, inbound, progress_state))
        elif self.progress_ping_sec > 0:
            progress_task = asyncio.create_task(self._progress_ping_loop(inbound))

        try:
            result = await session.agent.run()
            if progress_state is not None:
                await self._finalize_progress_card(session, progress_state, status="completed")
            return result
        except Exception:
            if progress_state is not None:
                await self._finalize_progress_card(session, progress_state, status="failed")
            raise
        finally:
            if progress_task is not None:
                progress_task.cancel()
                with suppress(asyncio.CancelledError):
                    await progress_task

    async def _progress_ping_loop(self, inbound: FeishuIncomingMessage) -> None:
        interval = float(self.progress_ping_sec)
        if interval <= 0:
            return

        await asyncio.sleep(interval)
        while True:
            await self._reply(inbound, "还在处理中，请稍候…", prefer_reply=False, force_text=True)
            log_channel_event("feishu", "bridge.progress.ping", chat_id=inbound.chat_id, interval_sec=self.progress_ping_sec)
            await asyncio.sleep(interval)

    def _is_progress_card_enabled(self) -> bool:
        return bool(getattr(self.streaming_config, "progress_card_enabled", False))

    def _progress_card_start_sec(self) -> float:
        return float(getattr(self.streaming_config, "progress_card_start_sec", 5))

    def _progress_card_update_sec(self) -> float:
        return float(getattr(self.streaming_config, "progress_card_update_sec", 3))

    async def _progress_card_loop(
        self,
        session: AgentSession,
        inbound: FeishuIncomingMessage,
        state: _ProgressCardState,
    ) -> None:
        start_after = self._progress_card_start_sec()
        update_interval = self._progress_card_update_sec()
        if start_after <= 0 or update_interval <= 0:
            return

        await asyncio.sleep(start_after)
        self._collect_progress_lines(session, state)
        first_content = self._build_progress_card_content(state, status="running")
        first_result = await self.feishu_client.reply_message_content(
            message_id=inbound.message_id,
            msg_type="interactive",
            content=first_content,
            reply_in_thread=resolve_reply_in_thread(inbound, enabled=self.reply_in_thread),
        )
        if not first_result.success:
            # Fallback to simple reply
            first_result = await self._reply(
                inbound,
                first_content,
                prefer_reply=True,
                force_message_type="interactive",
            )
        if not first_result.success:
            log_channel_event(
                "feishu",
                "bridge.progress.card.create.error",
                chat_id=inbound.chat_id,
                error=first_result.error,
            )
            return

        state.card_message_id = first_result.message_id
        log_channel_event(
            "feishu",
            "bridge.progress.card.create.ok",
            chat_id=inbound.chat_id,
            message_id=state.card_message_id or "",
            delay_sec=start_after,
        )

        if not state.card_message_id:
            return

        while True:
            await asyncio.sleep(update_interval)
            self._collect_progress_lines(session, state)
            content = self._build_progress_card_content(state, status="running")
            update_result = await self.feishu_client.update_message_content(
                message_id=state.card_message_id,
                content=content,
                msg_type="interactive",
            )
            if update_result.success:
                log_channel_event(
                    "feishu",
                    "bridge.progress.card.update.ok",
                    chat_id=inbound.chat_id,
                    message_id=state.card_message_id,
                    interval_sec=update_interval,
                )
                continue

            log_channel_event(
                "feishu",
                "bridge.progress.card.update.error",
                chat_id=inbound.chat_id,
                message_id=state.card_message_id,
                error=update_result.error,
            )
            return

    async def _finalize_progress_card(
        self,
        session: AgentSession,
        state: _ProgressCardState,
        status: str,
    ) -> None:
        if not state.card_message_id:
            return

        self._collect_progress_lines(session, state)
        content = self._build_progress_card_content(state, status=status)
        result = await self.feishu_client.update_message_content(
            message_id=state.card_message_id,
            content=content,
            msg_type="interactive",
        )
        event_name = "bridge.progress.card.final.ok" if result.success else "bridge.progress.card.final.error"
        log_channel_event(
            "feishu",
            event_name,
            message_id=state.card_message_id,
            status=status,
            error=result.error if not result.success else "",
        )

    def _collect_progress_lines(self, session: AgentSession, state: _ProgressCardState) -> None:
        messages = session.agent.messages
        if state.next_message_index >= len(messages):
            return

        new_messages = messages[state.next_message_index :]
        state.next_message_index = len(messages)

        for message in new_messages:
            for line in self._message_to_progress_lines(message):
                if line:
                    # Add to history (all messages)
                    state.history.append(line)
                    # Add to recent (last N messages)
                    state.recent.append(line)

    def _message_to_progress_lines(self, message: Any) -> list[str]:
        role = str(getattr(message, "role", "")).strip().lower()
        now = strftime("%H:%M:%S")
        if role == "assistant":
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                lines: list[str] = []
                for call in tool_calls:
                    function = getattr(call, "function", None)
                    name = str(getattr(function, "name", "tool"))
                    args = getattr(function, "arguments", {}) or {}
                    lines.append(f"[{now}] 调用 {self._summarize_tool_call(name, args)}")
                return lines

            text = self._extract_message_text(getattr(message, "content", ""))
            if text:
                return [f"[{now}] {self._truncate_progress_text(text)}"]
            return []

        if role == "tool":
            name = str(getattr(message, "name", "tool"))
            text = self._extract_message_text(getattr(message, "content", ""))
            preview = self._truncate_progress_text(text.splitlines()[0] if text else "(no output)")
            return [f"[{now}] {name}: {preview}"]

        return []

    def _extract_message_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(part for part in parts if part).strip()
        return str(content).strip() if content is not None else ""

    def _summarize_tool_call(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "bash":
            command = str(arguments.get("command", "")).replace("\n", " ").strip()
            if len(command) > 72:
                command = command[:72] + "..."
            return f"bash({command})" if command else "bash"
        return name

    def _truncate_progress_text(self, text: str, limit: int = 120) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[:limit] + "..."

    def _build_progress_card_content(self, state: _ProgressCardState, status: str) -> str:
        """Build progress card JSON with collapsible history panel."""
        elapsed_sec = int(max(0.0, perf_counter() - state.started_at))

        # Get recent lines (always shown)
        recent_lines = list(state.recent) if state.recent else []

        # Get history lines (those not in recent)
        # History = all messages except the recent ones
        total_count = len(state.history)
        recent_count = len(recent_lines)
        history_lines = state.history[:-recent_count] if recent_count > 0 else state.history[:]

        return build_progress_card(
            status=status,
            elapsed_sec=elapsed_sec,
            recent_lines=recent_lines,
            history_lines=history_lines if history_lines else None,
            recent_limit=state.recent_limit,
        )

    def _build_user_message(self, inbound: FeishuIncomingMessage, text: str) -> str:
        sender = inbound.sender_name or inbound.sender_open_id or inbound.sender_user_id or "user"
        if inbound.chat_type == FeishuChatType.GROUP:
            return f"{sender}: {text}"
        return text

    async def _get_or_create_session(self, agent_id: str, channel: str, session_id: str) -> AgentSession:
        runtime_bundle = await self._get_or_create_runtime_bundle(agent_id)
        profile = self.agent_registry.get(agent_id)

        def _factory() -> Agent:
            workspace_dir = profile.workspace / channel / session_id
            workspace_dir.mkdir(parents=True, exist_ok=True)

            tools = list(runtime_bundle.base_tools)
            add_workspace_tools(
                tools=tools,
                config=self.agent_config,
                workspace_dir=workspace_dir,
                include_recall_notes=True,
            )
            if self._subagent_orchestrator is not None:
                session_key = self._session_store.make_key(channel, session_id, agent_id=agent_id)
                tools.extend(
                    [
                        SessionsSpawnTool(self._subagent_orchestrator, session_key),
                        SessionsListTool(self._subagent_orchestrator, session_key),
                        SessionsHistoryTool(self._subagent_orchestrator, session_key),
                        SessionsSendTool(self._subagent_orchestrator, session_key),
                    ]
                )

            return Agent(
                llm_client=runtime_bundle.llm_client,
                system_prompt=runtime_bundle.system_prompt,
                tools=tools,
                max_steps=self.agent_config.agent.max_steps,
                workspace_dir=str(workspace_dir),
            )

        return await self._session_store.get_or_create(
            channel=channel,
            session_id=session_id,
            factory=_factory,
            agent_id=agent_id,
        )

    def clear_session(self, chat_id: str) -> None:
        removed = self._session_store.pop_channel_sessions("feishu", chat_id)
        log_channel_event("feishu", "bridge.session.cleared", chat_id=chat_id, removed=len(removed))

    async def _send_processing_ack(self, inbound: FeishuIncomingMessage) -> None:
        await self._reply(inbound, "敲键盘中🧑‍💻", prefer_reply=True, force_text=True)

    async def _send_chunked_reply(self, inbound: FeishuIncomingMessage, text: str) -> None:
        chunk_limit = 3000
        if self.streaming_config.enabled:
            chunk_limit = self.streaming_config.chunk_size
        chunks = chunk_text(text, limit=chunk_limit)
        total = len(chunks)
        stream_enabled = bool(self.streaming_config.enabled and total > 1)
        interval_sec = max(0.0, float(self.streaming_config.interval_ms) / 1000.0)
        reply_all_chunks = bool(self.streaming_config.reply_all_chunks)

        if stream_enabled:
            log_channel_event(
                "feishu",
                "bridge.stream.begin",
                total_chunks=total,
                chunk_size=chunk_limit,
                interval_ms=self.streaming_config.interval_ms,
                reply_all_chunks=reply_all_chunks,
                chat_id=inbound.chat_id,
            )

        async def _emit_chunk(index: int, _total: int, chunk: str) -> None:
            payload = chunk
            if total > 1:
                payload = f"[{index}/{total}]\n{chunk}"

            if index == 1:
                await self._reply(inbound, payload, prefer_reply=True)
            else:
                if reply_all_chunks:
                    await self._reply(inbound, payload, prefer_reply=True)
                else:
                    msg_type, content = self._render_outbound(payload, force_text=False)
                    send_result = await self.feishu_client.send_message_content(
                        receive_id=inbound.chat_id,
                        msg_type=msg_type,
                        content=content,
                        receive_id_type="chat_id",
                    )
                    if send_result.success:
                        log_channel_event("feishu", "bridge.send.chunk.ok", index=f"{index}/{total}", chat_id=inbound.chat_id)
                    else:
                        log_channel_event(
                            "feishu",
                            "bridge.send.chunk.error",
                            index=f"{index}/{total}",
                            chat_id=inbound.chat_id,
                            error=send_result.error,
                        )

        streamer = FeishuChunkStreamer(interval_ms=int(interval_sec * 1000) if stream_enabled else 0)
        await streamer.emit(chunks, _emit_chunk)

        if stream_enabled:
            log_channel_event("feishu", "bridge.stream.end", total_chunks=total, chat_id=inbound.chat_id)

    async def _reply(
        self,
        inbound: FeishuIncomingMessage,
        text: str,
        prefer_reply: bool = True,
        force_text: bool = False,
        force_message_type: str | None = None,
    ) -> FeishuSendResult:
        msg_type, content = self._render_outbound(
            text,
            force_text=force_text,
            force_message_type=force_message_type,
        )
        reply_in_thread = resolve_reply_in_thread(inbound, enabled=self.reply_in_thread)
        if prefer_reply:
            reply_result = await self.feishu_client.reply_message_content(
                message_id=inbound.message_id,
                msg_type=msg_type,
                content=content,
                reply_in_thread=reply_in_thread,
            )
            if reply_result.success:
                log_channel_event("feishu", "bridge.reply.ok", message_id=inbound.message_id, chat_id=inbound.chat_id)
                return reply_result
            log_channel_event(
                "feishu",
                "bridge.reply.error",
                message_id=inbound.message_id,
                chat_id=inbound.chat_id,
                error=reply_result.error,
            )

        send_result = await self.feishu_client.send_message_content(
            receive_id=inbound.chat_id,
            msg_type=msg_type,
            content=content,
            receive_id_type="chat_id",
        )
        if send_result.success:
            log_channel_event("feishu", "bridge.send.ok", chat_id=inbound.chat_id)
        else:
            log_channel_event("feishu", "bridge.send.error", chat_id=inbound.chat_id, error=send_result.error)
        return send_result

    def _render_outbound(
        self,
        text: str,
        force_text: bool = False,
        force_message_type: str | None = None,
    ) -> tuple[str, str]:
        if force_text:
            return "text", build_text_payload(text)
        if force_message_type == "interactive":
            return "interactive", build_markdown_card(text)
        if force_message_type:
            return force_message_type, build_payload_by_type(force_message_type, text)
        message_type = resolve_message_type(text, self.render_mode)
        return message_type, build_payload_by_type(message_type, text)
