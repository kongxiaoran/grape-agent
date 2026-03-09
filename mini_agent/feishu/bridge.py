"""Bridge Feishu events to Mini-Agent sessions."""

from __future__ import annotations

from pathlib import Path

from mini_agent.agent import Agent
from mini_agent.config import Config
from mini_agent.runtime_factory import add_workspace_tools, build_runtime_bundle
from mini_agent.session_store import AgentSession, AgentSessionStore
from mini_agent.tools.mcp_loader import cleanup_mcp_connections

from .client import FeishuClient
from .dedup import FeishuMessageDedup
from .message_utils import chunk_text, parse_incoming_event, strip_bot_mentions
from .types import FeishuChatType, FeishuIncomingMessage


class FeishuAgentBridge:
    """High-level message bridge for Feishu bot and Agent runtime."""

    def __init__(
        self,
        feishu_client: FeishuClient,
        agent_config: Config,
        workspace_root: Path | None = None,
        group_require_mention: bool = True,
    ):
        self.feishu_client = feishu_client
        self.agent_config = agent_config
        self.workspace_root = workspace_root or Path.home() / ".mini-agent" / "feishu_workspaces"
        self.group_require_mention = group_require_mention

        self.workspace_root.mkdir(parents=True, exist_ok=True)

        dedup_file = Path.home() / ".mini-agent" / "feishu" / "dedup.json"
        self.dedup = FeishuMessageDedup(dedup_file)

        self._runtime = None
        self._session_store = AgentSessionStore()

    async def initialize(self) -> None:
        """Initialize shared runtime bundle for Feishu sessions."""

        def _log(message: str) -> None:
            print(f"[Feishu] runtime: {message}")

        self._runtime = await build_runtime_bundle(config=self.agent_config, log=_log)

    async def shutdown(self) -> None:
        """Cleanup long-lived resources."""
        await cleanup_mcp_connections()

    async def handle_event(self, event_data: dict) -> None:
        """Entry point from WS callback."""
        inbound = parse_incoming_event(event_data, bot_open_id=self.feishu_client.bot_open_id)
        if inbound is None:
            print("[Feishu] parse_incoming_event returned None")
            return

        dedup_key = f"{inbound.chat_id}:{inbound.message_id}"
        if self.dedup.seen_or_record(dedup_key):
            print(f"[Feishu] skip duplicate message {dedup_key}")
            return

        # Ignore bot self-messages.
        if self.feishu_client.bot_open_id and inbound.sender_open_id == self.feishu_client.bot_open_id:
            print(f"[Feishu] skip self message {dedup_key}")
            return

        if (
            inbound.chat_type == FeishuChatType.GROUP
            and self.group_require_mention
            and not inbound.mentioned_bot
        ):
            print(f"[Feishu] skip group message without mention {dedup_key}")
            return

        cleaned = strip_bot_mentions(inbound.content, inbound.mentions, self.feishu_client.bot_open_id)
        if not cleaned:
            print(f"[Feishu] empty content after mention stripping {dedup_key}")
            await self._reply(inbound, "我在，请直接发送任务内容。")
            return

        if cleaned.lower() in {"/clear", "/reset", "/new"}:
            self.clear_session(inbound.chat_id)
            await self._reply(inbound, "会话已重置。")
            return

        print(f"[Feishu] processing message {dedup_key}: {cleaned[:80]}")
        await self._send_processing_ack(inbound)

        session = await self._get_or_create_session(inbound.chat_id)
        async with session.lock:
            user_text = self._build_user_message(inbound, cleaned)
            session.agent.add_user_message(user_text)

            try:
                result = await session.agent.run()
            except Exception as exc:
                await self._reply(inbound, f"处理失败：{type(exc).__name__}: {exc}")
                return

            final_text = result.strip() if isinstance(result, str) else str(result)
            if not final_text:
                final_text = "任务执行完成。"

            await self._send_chunked_reply(inbound, final_text)

    def _build_user_message(self, inbound: FeishuIncomingMessage, text: str) -> str:
        sender = inbound.sender_name or inbound.sender_open_id or inbound.sender_user_id or "user"
        if inbound.chat_type == FeishuChatType.GROUP:
            return f"{sender}: {text}"
        return text

    async def _get_or_create_session(self, chat_id: str) -> AgentSession:
        if self._runtime is None:
            raise RuntimeError("FeishuAgentBridge is not initialized")

        def _factory() -> Agent:
            workspace_dir = self.workspace_root / chat_id
            workspace_dir.mkdir(parents=True, exist_ok=True)

            tools = list(self._runtime.base_tools)
            add_workspace_tools(
                tools=tools,
                config=self.agent_config,
                workspace_dir=workspace_dir,
                include_recall_notes=True,
            )

            return Agent(
                llm_client=self._runtime.llm_client,
                system_prompt=self._runtime.system_prompt,
                tools=tools,
                max_steps=self.agent_config.agent.max_steps,
                workspace_dir=str(workspace_dir),
            )

        return await self._session_store.get_or_create("feishu", chat_id, _factory)

    def clear_session(self, chat_id: str) -> None:
        self._session_store.pop("feishu", chat_id)

    async def _send_processing_ack(self, inbound: FeishuIncomingMessage) -> None:
        await self._reply(inbound, "⌨️", prefer_reply=True)

    async def _send_chunked_reply(self, inbound: FeishuIncomingMessage, text: str) -> None:
        chunks = chunk_text(text, limit=3000)
        total = len(chunks)

        for index, chunk in enumerate(chunks, start=1):
            payload = chunk
            if total > 1:
                payload = f"[{index}/{total}]\n{chunk}"

            if index == 1:
                await self._reply(inbound, payload, prefer_reply=True)
            else:
                send_result = await self.feishu_client.send_message(inbound.chat_id, payload, receive_id_type="chat_id")
                if send_result.success:
                    print(f"[Feishu] sent chunk {index}/{total} chat_id={inbound.chat_id}")
                else:
                    print(f"[Feishu] send chunk failed chat_id={inbound.chat_id} err={send_result.error}")

    async def _reply(self, inbound: FeishuIncomingMessage, text: str, prefer_reply: bool = True) -> None:
        reply_in_thread = bool(inbound.thread_id or inbound.root_id)
        if prefer_reply:
            reply_result = await self.feishu_client.reply_message(
                inbound.message_id,
                text,
                reply_in_thread=reply_in_thread,
            )
            if reply_result.success:
                print(f"[Feishu] replied message_id={inbound.message_id} chat_id={inbound.chat_id}")
                return
            print(
                f"[Feishu] reply failed message_id={inbound.message_id} chat_id={inbound.chat_id} "
                f"err={reply_result.error}; fallback send"
            )

        send_result = await self.feishu_client.send_message(inbound.chat_id, text, receive_id_type="chat_id")
        if send_result.success:
            print(f"[Feishu] sent chat_id={inbound.chat_id}")
        else:
            print(f"[Feishu] send failed chat_id={inbound.chat_id} err={send_result.error}")
