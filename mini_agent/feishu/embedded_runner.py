"""Embedded Feishu bot lifecycle runner for mini-agent process."""

from __future__ import annotations

import threading
from pathlib import Path

from mini_agent.config import Config

from .server_ws import FeishuWebSocketServer


class EmbeddedFeishuRunner:
    """Manage Feishu bot in a background thread bound to process lifecycle."""

    def __init__(self, config: Config, config_path: Path):
        self.config = config
        self.config_path = config_path
        self.server: FeishuWebSocketServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        """Start embedded Feishu bot if enabled and configured."""
        feishu_cfg = self.config.feishu
        if not feishu_cfg.enabled:
            return

        if not feishu_cfg.app_id or not feishu_cfg.app_secret:
            print("[Feishu] Embedded bot enabled but app_id/app_secret missing, skip startup.")
            return

        if self.thread is not None and self.thread.is_alive():
            return

        workspace_base = Path(feishu_cfg.workspace_base).expanduser() if feishu_cfg.workspace_base else None
        self.server = FeishuWebSocketServer(
            app_id=feishu_cfg.app_id,
            app_secret=feishu_cfg.app_secret,
            domain=feishu_cfg.domain,
            config_path=self.config_path,
            workspace_base=workspace_base,
            group_require_mention=feishu_cfg.group_require_mention,
            install_signal_handlers=False,
        )

        def run_server() -> None:
            try:
                self.server.start()
            except Exception as exc:
                print(f"[Feishu] Embedded bot stopped with error: {exc}")

        self.thread = threading.Thread(target=run_server, name="mini-agent-feishu", daemon=True)
        self.thread.start()

        print("[Feishu] Embedded bot thread started.")

    def stop(self) -> None:
        """Stop embedded Feishu bot and wait briefly for thread exit."""
        if self.server is not None:
            try:
                self.server.stop()
            except Exception as exc:
                print(f"[Feishu] Embedded bot stop warning: {exc}")

        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=5)
