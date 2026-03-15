"""Channel plugin registry."""

from __future__ import annotations

from collections.abc import Callable

from .types import ChannelPlugin

PluginFactory = Callable[[], ChannelPlugin]


class ChannelRegistry:
    """Registry for channel plugin factories."""

    def __init__(self):
        self._factories: dict[str, PluginFactory] = {}

    def register(self, channel_id: str, factory: PluginFactory) -> None:
        if channel_id in self._factories:
            raise ValueError(f"channel already registered: {channel_id}")
        self._factories[channel_id] = factory

    def create(self, channel_id: str) -> ChannelPlugin:
        factory = self._factories.get(channel_id)
        if factory is None:
            raise KeyError(f"channel not registered: {channel_id}")
        return factory()

    def has(self, channel_id: str) -> bool:
        return channel_id in self._factories

    def registered_ids(self) -> list[str]:
        return sorted(self._factories.keys())

