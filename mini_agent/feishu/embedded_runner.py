"""Embedded Feishu bot lifecycle runner for grape-agent process."""

from __future__ import annotations

import threading
from pathlib import Path

from mini_agent.agents.orchestrator import SessionOrchestrator
from mini_agent.channels.logging import log_channel_event
from mini_agent.channels.plugins.feishu.accounts import FeishuAccountRegistry
from mini_agent.config import Config
from mini_agent.session_store import AgentSessionStore

from .rendering import build_text_payload
from .server_ws import FeishuWebSocketServer


class EmbeddedFeishuRunner:
    """Manage Feishu bot in a background thread bound to process lifecycle."""

    def __init__(
        self,
        config: Config,
        config_path: Path,
        account_id: str,
        session_store: AgentSessionStore | None = None,
        subagent_orchestrator: SessionOrchestrator | None = None,
        on_inbound_message=None,
    ):
        self.config = config
        self.config_path = config_path
        self.account_id = account_id
        self.session_store = session_store
        self.subagent_orchestrator = subagent_orchestrator
        self.on_inbound_message = on_inbound_message
        self.server: FeishuWebSocketServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        """Start embedded Feishu bot if enabled and configured."""
        feishu_cfg = self.config.channels.feishu
        if not feishu_cfg.enabled:
            log_channel_event("feishu", "runner.start.skipped", reason="disabled", account_id=self.account_id)
            return

        registry = FeishuAccountRegistry(feishu_cfg)
        account = registry.get(self.account_id)
        if not account.app_id or not account.app_secret:
            log_channel_event("feishu", "runner.start.skipped", reason="missing_credentials", account_id=self.account_id)
            return

        if self.thread is not None and self.thread.is_alive():
            log_channel_event("feishu", "runner.start.skipped", reason="already_running", account_id=self.account_id)
            return

        workspace_base = Path(feishu_cfg.workspace_base).expanduser() if feishu_cfg.workspace_base else None
        self.server = FeishuWebSocketServer(
            app_id=account.app_id,
            app_secret=account.app_secret,
            domain=account.domain,
            config_path=self.config_path,
            workspace_base=workspace_base,
            account_id=account.account_id,
            group_require_mention=feishu_cfg.policy.require_mention,
            group_session_scope=feishu_cfg.policy.group_session_scope,
            reply_in_thread=feishu_cfg.policy.reply_in_thread,
            install_signal_handlers=False,
            session_store=self.session_store,
            subagent_orchestrator=self.subagent_orchestrator,
            on_inbound_message=self.on_inbound_message,
        )

        def run_server() -> None:
            try:
                self.server.start()
            except Exception as exc:
                log_channel_event(
                    "feishu",
                    "runner.thread.error",
                    account_id=self.account_id,
                    error=f"{type(exc).__name__}: {exc}",
                )

        self.thread = threading.Thread(target=run_server, name=f"grape-agent-feishu-{self.account_id}", daemon=True)
        self.thread.start()

        log_channel_event("feishu", "runner.start.ok", account_id=self.account_id, thread=self.thread.name)

    def stop(self) -> None:
        """Stop embedded Feishu bot and wait briefly for thread exit."""
        if self.server is not None:
            try:
                self.server.stop()
            except Exception as exc:
                log_channel_event(
                    "feishu",
                    "runner.stop.warning",
                    account_id=self.account_id,
                    error=f"{type(exc).__name__}: {exc}",
                )

        if self.thread is not None and self.thread.is_alive():
            try:
                self.thread.join(timeout=5)
            except KeyboardInterrupt:
                log_channel_event(
                    "feishu",
                    "runner.stop.interrupt",
                    account_id=self.account_id,
                )
        log_channel_event("feishu", "runner.stop.ok", account_id=self.account_id, running=self.is_running())

    async def send_text(
        self,
        target: str,
        text: str,
        receive_id_type: str = "chat_id",
    ) -> dict:
        """Send proactive text message via Feishu OpenAPI."""
        content = build_text_payload(text)
        return await self.send_payload(
            target=target,
            msg_type="text",
            content=content,
            receive_id_type=receive_id_type,
        )

    async def send_payload(
        self,
        target: str,
        msg_type: str,
        content: str,
        receive_id_type: str = "chat_id",
    ) -> dict:
        """Send proactive message payload via Feishu OpenAPI."""
        if self.server is None:
            return {"ok": False, "error": "feishu runner is not initialized"}

        result = await self.server.feishu_client.send_message_content(
            receive_id=target,
            msg_type=msg_type,
            content=content,
            receive_id_type=receive_id_type,
        )
        return self._normalize_send_result(result)

    async def reply_text(
        self,
        message_id: str,
        text: str,
        reply_in_thread: bool = False,
    ) -> dict:
        """Reply to existing Feishu message by message_id."""
        content = build_text_payload(text)
        return await self.reply_payload(
            message_id=message_id,
            msg_type="text",
            content=content,
            reply_in_thread=reply_in_thread,
        )

    async def reply_payload(
        self,
        message_id: str,
        msg_type: str,
        content: str,
        reply_in_thread: bool = False,
    ) -> dict:
        """Reply using raw Feishu payload."""
        if self.server is None:
            return {"ok": False, "error": "feishu runner is not initialized"}

        result = await self.server.feishu_client.reply_message_content(
            message_id=message_id,
            msg_type=msg_type,
            content=content,
            reply_in_thread=reply_in_thread,
        )
        return self._normalize_send_result(result)

    @staticmethod
    def _normalize_send_result(result) -> dict:
        return {
            "ok": bool(result.success),
            "message_id": result.message_id,
            "error": result.error,
            "raw": result.raw,
        }

    def is_running(self) -> bool:
        return bool(self.thread is not None and self.thread.is_alive())

    def snapshot(self) -> dict:
        account = FeishuAccountRegistry(self.config.channels.feishu).get(self.account_id)
        return {
            "enabled": self.config.channels.feishu.enabled,
            "running": self.is_running(),
            "account_id": self.account_id,
            "domain": account.domain,
            "render_mode": self.config.channels.feishu.render_mode,
            "policy": {
                "require_mention": self.config.channels.feishu.policy.require_mention,
                "reply_in_thread": self.config.channels.feishu.policy.reply_in_thread,
                "group_session_scope": self.config.channels.feishu.policy.group_session_scope,
            },
        }
