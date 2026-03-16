"""Feishu long-connection server entrypoint for Grape-Agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from mini_agent.agents.orchestrator import SessionOrchestrator
from mini_agent.channels.logging import log_channel_event
from mini_agent.config import Config
from mini_agent.session_store import AgentSessionStore

from .bridge import FeishuAgentBridge
from .client import FeishuClient


class FeishuWebSocketServer:
    """Run Feishu long-connection and dispatch events to Agent bridge."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str = "feishu",
        config_path: Path | None = None,
        workspace_base: Path | None = None,
        account_id: str | None = None,
        group_require_mention: bool = True,
        group_session_scope: str = "group",
        reply_in_thread: bool = True,
        install_signal_handlers: bool = True,
        session_store: AgentSessionStore | None = None,
        subagent_orchestrator: SessionOrchestrator | None = None,
        on_inbound_message=None,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.domain = domain
        self.config_path = config_path or Config.get_default_config_path()
        self.workspace_base = workspace_base
        self.account_id = account_id or app_id
        self.group_require_mention = group_require_mention
        self.group_session_scope = group_session_scope
        self.reply_in_thread = reply_in_thread
        self.install_signal_handlers = install_signal_handlers
        self.session_store = session_store
        self.subagent_orchestrator = subagent_orchestrator
        self.on_inbound_message = on_inbound_message

        self.feishu_client = FeishuClient(app_id=app_id, app_secret=app_secret, domain=domain)
        self.bridge: FeishuAgentBridge | None = None

        self._ws_client: Any = None
        self._bridge_loop: asyncio.AbstractEventLoop | None = None
        self._bridge_thread: threading.Thread | None = None
        self._stop_flag = threading.Event()

    def _start_bridge_loop(self) -> None:
        loop = asyncio.new_event_loop()

        def run_loop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=run_loop, name="feishu-bridge-loop", daemon=True)
        thread.start()

        self._bridge_loop = loop
        self._bridge_thread = thread

    def _run_bridge_coro(self, coro) -> Any:
        if self._bridge_loop is None:
            raise RuntimeError("Bridge loop not initialized")
        future: Future = asyncio.run_coroutine_threadsafe(coro, self._bridge_loop)
        return future.result()

    def start(self) -> None:
        """Start WS connection and block until stopped."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")

        # Import SDK in main thread before any running event loop exists.
        # lark_oapi.ws.client captures a module-level loop at import time.
        self.feishu_client.get_sdk()

        cfg = Config.from_yaml(self.config_path)

        self._start_bridge_loop()

        self.bridge = FeishuAgentBridge(
            feishu_client=self.feishu_client,
            agent_config=cfg,
            workspace_root=self.workspace_base,
            account_id=self.account_id,
            group_require_mention=self.group_require_mention,
            group_session_scope=self.group_session_scope,
            reply_in_thread=self.reply_in_thread,
            session_store=self.session_store,
            subagent_orchestrator=self.subagent_orchestrator,
            on_inbound_message=self.on_inbound_message,
        )
        self._run_bridge_coro(self.bridge.initialize())

        bot_open_id, bot_name = self.feishu_client.get_bot_info_sync()
        log_channel_event(
            "feishu",
            "ws.start.info",
            config=str(self.config_path),
            domain=self.domain,
            account_id=self.account_id,
            bot=f"{bot_name or 'unknown'} ({bot_open_id or 'unknown'})",
        )

        lark = self.feishu_client.get_sdk()
        self._configure_sdk_logging(lark)
        domain = lark.LARK_DOMAIN if self.domain == "lark" else lark.FEISHU_DOMAIN

        event_dispatcher = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message_event)
            .build()
        )

        self._ws_client = lark.ws.Client(
            app_id=self.app_id,
            app_secret=self.app_secret,
            domain=domain,
            event_handler=event_dispatcher,
            log_level=lark.LogLevel.ERROR,
        )

        if self.install_signal_handlers:
            self._install_signal_handlers()
        log_channel_event("feishu", "ws.connect.begin", account_id=self.account_id)

        try:
            self._ws_client.start()
        finally:
            self.stop()

    @staticmethod
    def _configure_sdk_logging(lark_sdk) -> None:
        """Reduce Lark SDK console noise in interactive CLI mode.

        The SDK defaults to INFO logs like:
        [Lark] [INFO] connected to wss://...
        which can break prompt-toolkit input rendering when emitted from a background thread.
        """
        try:
            import logging

            for logger_name in ("Lark", "lark", "lark_oapi"):
                logger = logging.getLogger(logger_name)
                logger.setLevel(logging.ERROR)
                logger.propagate = False
                for handler in logger.handlers:
                    try:
                        handler.setLevel(logging.ERROR)
                    except Exception:
                        pass
            if hasattr(lark_sdk, "logger"):
                lark_sdk.logger.setLevel(logging.ERROR)
                lark_sdk.logger.propagate = False
        except Exception:
            pass

    def stop(self) -> None:
        """Graceful shutdown."""
        if self._stop_flag.is_set():
            return
        self._stop_flag.set()

        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception:
                pass

        if self.bridge is not None and self._bridge_loop is not None:
            try:
                self._run_bridge_coro(self.bridge.shutdown())
            except Exception as exc:
                log_channel_event("feishu", "ws.stop.warning", error=f"bridge_shutdown: {type(exc).__name__}: {exc}")

        if self._bridge_loop is not None:
            self._bridge_loop.call_soon_threadsafe(self._bridge_loop.stop)

        if self._bridge_thread is not None:
            self._bridge_thread.join(timeout=2)
        log_channel_event("feishu", "ws.stop.ok", account_id=self.account_id)

    def _install_signal_handlers(self) -> None:
        def _on_signal(_sig, _frame) -> None:
            self.stop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, _on_signal)

    def _extract_event_data(self, event: Any) -> dict[str, Any] | None:
        lark = self.feishu_client.get_sdk()
        event_data = getattr(event, "event", None)
        if event_data is None:
            return None

        if isinstance(event_data, dict):
            return event_data

        try:
            dumped = lark.JSON.marshal(event_data)
            if isinstance(dumped, str):
                parsed = json.loads(dumped)
                if isinstance(parsed, dict):
                    return parsed
        except Exception:
            pass

        return None

    def _handle_message_event(self, event: Any) -> None:
        if self.bridge is None or self._bridge_loop is None:
            return

        event_data = self._extract_event_data(event)
        if event_data is None:
            log_channel_event("feishu", "ws.event.skipped", reason="parse_failed")
            return

        msg = event_data.get("message", {}) if isinstance(event_data, dict) else {}
        if isinstance(msg, dict):
            message_id = msg.get("message_id", "")
            chat_id = msg.get("chat_id", "")
            message_type = msg.get("message_type", "")
            log_channel_event(
                "feishu",
                "ws.event.inbound",
                account_id=self.account_id,
                message_id=message_id,
                chat_id=chat_id,
                message_type=message_type,
            )

        future: Future = asyncio.run_coroutine_threadsafe(self.bridge.handle_event(event_data), self._bridge_loop)

        def _done_callback(fut: Future) -> None:
            exc = fut.exception()
            if exc is not None:
                log_channel_event("feishu", "ws.event.error", error=f"{type(exc).__name__}: {exc}")

        future.add_done_callback(_done_callback)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Grape-Agent Feishu long-connection server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  grape-agent-feishu --app-id cli_xxx --app-secret xxx\n"
            "  grape-agent-feishu --app-id cli_xxx --app-secret xxx --domain lark\n"
            "  grape-agent-feishu --app-id cli_xxx --app-secret xxx --config ~/.grape/settings.json"
        ),
    )

    parser.add_argument("--app-id", required=True, help="Feishu app id (cli_xxx)")
    parser.add_argument("--app-secret", required=True, help="Feishu app secret")
    parser.add_argument("--domain", default="feishu", choices=["feishu", "lark"], help="Platform domain")
    parser.add_argument("--config", default=None, help="Grape settings.json path")
    parser.add_argument("--workspace-base", default=None, help="Per-chat workspace base directory")
    parser.add_argument(
        "--group-open",
        action="store_true",
        help="Allow all group messages without @bot mention",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config_path = Path(args.config).expanduser() if args.config else None
    workspace_base = Path(args.workspace_base).expanduser() if args.workspace_base else None

    server = FeishuWebSocketServer(
        app_id=args.app_id,
        app_secret=args.app_secret,
        domain=args.domain,
        config_path=config_path,
        workspace_base=workspace_base,
        group_require_mention=not args.group_open,
    )

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
    except Exception as exc:
        log_channel_event("feishu", "ws.fatal", error=f"{type(exc).__name__}: {exc}")
        server.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
