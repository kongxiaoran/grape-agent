"""Channel runtime manager."""

from __future__ import annotations

from typing import Any

from .logging import log_channel_event
from .registry import ChannelRegistry
from .types import ChannelContext, ChannelPlugin


class ChannelRuntime:
    """Manage channel plugin lifecycle and status."""

    def __init__(self, registry: ChannelRegistry, context: ChannelContext):
        self._registry = registry
        self._context = context
        self._plugins: dict[str, ChannelPlugin] = {}
        self._started = False

    async def start(self) -> None:
        if self._started:
            return

        log_channel_event("runtime", "start.begin")
        for channel_id in self._enabled_channel_ids():
            if not self._registry.has(channel_id):
                log_channel_event(channel_id, "start.skipped", reason="plugin_not_registered")
                continue
            plugin = self._registry.create(channel_id)
            await plugin.start(self._context)
            self._plugins[channel_id] = plugin
            log_channel_event(channel_id, "start.ok")

        self._started = True
        log_channel_event("runtime", "start.ok", running_count=len(self._plugins))

    async def stop(self) -> None:
        log_channel_event("runtime", "stop.begin", running_count=len(self._plugins))
        ids = list(self._plugins.keys())
        for channel_id in reversed(ids):
            plugin = self._plugins[channel_id]
            try:
                await plugin.stop()
                log_channel_event(channel_id, "stop.ok")
            except Exception as exc:
                log_channel_event(channel_id, "stop.error", error=f"{type(exc).__name__}: {exc}")
        self._plugins.clear()
        self._started = False
        log_channel_event("runtime", "stop.ok")

    async def send(self, channel_id: str, target: str, content: str, **kwargs: Any) -> dict[str, Any]:
        plugin = self._plugins.get(channel_id)
        if plugin is None:
            log_channel_event(channel_id, "send.error", reason="channel_not_running", target=target)
            return {"ok": False, "error": f"channel not running: {channel_id}"}
        log_channel_event(channel_id, "send.begin", target=target, content_preview=content[:80])
        result = await plugin.send(target=target, content=content, **kwargs)
        log_channel_event(
            channel_id,
            "send.ok" if result.get("ok") else "send.error",
            target=target,
            error=result.get("error"),
            message_id=result.get("message_id"),
        )
        return result

    def snapshot(self) -> dict[str, Any]:
        items: dict[str, dict[str, Any]] = {}
        for channel_id in self._configured_channel_ids():
            plugin = self._plugins.get(channel_id)
            if plugin is None:
                items[channel_id] = {
                    "enabled": self._is_channel_enabled(channel_id),
                    "running": False,
                }
                continue

            details = plugin.snapshot()
            details.setdefault("enabled", self._is_channel_enabled(channel_id))
            details.setdefault("running", True)
            items[channel_id] = details

        return {
            "started": self._started,
            "running_count": sum(1 for value in items.values() if value.get("running")),
            "channels": items,
        }

    def _configured_channel_ids(self) -> list[str]:
        # M2 minimal set: only Feishu pluginized.
        return ["feishu"]

    def _enabled_channel_ids(self) -> list[str]:
        return [channel_id for channel_id in self._configured_channel_ids() if self._is_channel_enabled(channel_id)]

    def _is_channel_enabled(self, channel_id: str) -> bool:
        if channel_id == "feishu":
            return bool(self._context.config.channels.feishu.enabled)
        return False


def build_default_registry() -> ChannelRegistry:
    """Build registry with built-in channel plugins."""
    registry = ChannelRegistry()
    from mini_agent.channels.plugins.feishu.plugin import FeishuChannelPlugin

    registry.register("feishu", FeishuChannelPlugin)
    return registry
