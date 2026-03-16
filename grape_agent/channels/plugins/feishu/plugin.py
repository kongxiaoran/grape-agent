"""Feishu channel plugin."""

from __future__ import annotations

from typing import Any

from grape_agent.channels.plugins.feishu.accounts import FeishuAccountRegistry
from grape_agent.channels.plugins.feishu.cards import build_card_with_fallback
from grape_agent.channels.logging import log_channel_event
from grape_agent.feishu.embedded_runner import EmbeddedFeishuRunner
from grape_agent.feishu.rendering import (
    MessageType,
    RenderMode,
    build_payload_by_type,
    resolve_message_type,
)

from ...types import ChannelContext


class FeishuChannelPlugin:
    """Channel plugin wrapper around embedded Feishu runner."""

    id = "feishu"

    def __init__(self):
        self._runners: dict[str, EmbeddedFeishuRunner] = {}
        self._enabled = False
        self._render_mode: RenderMode = "auto"
        self._default_account: str = "main"
        self._reply_in_thread_default: bool = True

    async def start(self, ctx: ChannelContext) -> None:
        self._enabled = bool(ctx.config.channels.feishu.enabled)
        self._render_mode = ctx.config.channels.feishu.render_mode
        self._default_account = ctx.config.channels.feishu.default_account
        self._reply_in_thread_default = ctx.config.channels.feishu.policy.reply_in_thread
        if not self._enabled:
            log_channel_event(self.id, "plugin.start.skipped", reason="disabled")
            return
        registry = FeishuAccountRegistry(ctx.config.channels.feishu)
        for account in registry.all():
            runner = EmbeddedFeishuRunner(
                config=ctx.config,
                config_path=ctx.config_path,
                account_id=account.account_id,
                session_store=ctx.session_store,
                subagent_orchestrator=ctx.subagent_orchestrator,
                on_inbound_message=ctx.on_inbound_message,
            )
            runner.start()
            self._runners[account.account_id] = runner
        log_channel_event(self.id, "plugin.start.ok", accounts=list(self._runners.keys()))

    async def stop(self) -> None:
        if not self._runners:
            log_channel_event(self.id, "plugin.stop.skipped", reason="runner_not_initialized")
            return
        for runner in self._runners.values():
            runner.stop()
        self._runners.clear()
        log_channel_event(self.id, "plugin.stop.ok")

    async def send(self, target: str, content: str, **kwargs: Any) -> dict[str, Any]:  # noqa: ARG002
        if not self._enabled or not self._runners:
            return {"ok": False, "error": "feishu channel is not enabled/running"}

        account_id = str(kwargs.get("account_id", self._default_account)).strip() or self._default_account
        runner = self._runners.get(account_id)
        if runner is None:
            return {"ok": False, "error": f"unknown feishu account: {account_id}"}

        mode = str(kwargs.get("mode", "send")).strip().lower()
        outbound_type = self._normalize_outbound_type(kwargs)
        if mode == "reply":
            message_id = str(kwargs.get("message_id", target)).strip()
            if not message_id:
                return {"ok": False, "error": "message_id is required when mode=reply"}
            reply_in_thread = bool(kwargs.get("reply_in_thread", self._reply_in_thread_default))
            return await self._send_reply(
                runner=runner,
                outbound_type=outbound_type,
                message_id=message_id,
                content=content,
                reply_in_thread=reply_in_thread,
            )

        if mode != "send":
            return {"ok": False, "error": f"unsupported mode: {mode}"}

        receive_id_type = str(kwargs.get("receive_id_type", "chat_id"))
        return await self._send_direct(
            runner=runner,
            outbound_type=outbound_type,
            target=target,
            content=content,
            receive_id_type=receive_id_type,
        )

    def snapshot(self) -> dict[str, Any]:
        if not self._runners:
            return {
                "enabled": self._enabled,
                "running": False,
                "plugin": self.id,
            }
        accounts = {account_id: runner.snapshot() for account_id, runner in self._runners.items()}
        running_count = sum(1 for status in accounts.values() if status.get("running"))
        return {
            "enabled": self._enabled,
            "running": running_count > 0,
            "running_count": running_count,
            "default_account": self._default_account,
            "accounts": accounts,
            "plugin": self.id,
        }

    @staticmethod
    def _normalize_outbound_type(kwargs: dict[str, Any]) -> MessageType | None:
        raw = kwargs.get("message_type", kwargs.get("msg_type"))
        if raw is None:
            return None
        message_type = str(raw).strip().lower()
        if message_type == "card":
            return "interactive"
        if message_type in {"text", "post", "interactive"}:
            return message_type
        return None

    async def _send_direct(
        self,
        runner: EmbeddedFeishuRunner,
        outbound_type: MessageType | None,
        target: str,
        content: str,
        receive_id_type: str,
    ) -> dict[str, Any]:
        resolved_type = outbound_type or resolve_message_type(content, self._render_mode)
        payload_type = resolved_type
        try:
            payload = build_payload_by_type(resolved_type, content)
        except Exception:
            if resolved_type == "interactive":
                payload_type, payload = build_card_with_fallback(content)
            else:
                raise
        return await runner.send_payload(
            target=target,
            msg_type=payload_type,
            content=payload,
            receive_id_type=receive_id_type,
        )

    async def _send_reply(
        self,
        runner: EmbeddedFeishuRunner,
        outbound_type: MessageType | None,
        message_id: str,
        content: str,
        reply_in_thread: bool,
    ) -> dict[str, Any]:
        resolved_type = outbound_type or resolve_message_type(content, self._render_mode)
        payload_type = resolved_type
        try:
            payload = build_payload_by_type(resolved_type, content)
        except Exception:
            if resolved_type == "interactive":
                payload_type, payload = build_card_with_fallback(content)
            else:
                raise
        return await runner.reply_payload(
            message_id=message_id,
            msg_type=payload_type,
            content=payload,
            reply_in_thread=reply_in_thread,
        )
