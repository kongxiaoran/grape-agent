"""Channel plugin interfaces and runtime context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any, Protocol, Callable

from grape_agent.config import Config
from grape_agent.session_store import AgentSessionStore

if TYPE_CHECKING:
    from grape_agent.agents.orchestrator import SessionOrchestrator


@dataclass(slots=True)
class ChannelContext:
    """Shared context passed to channel plugins."""

    config: Config
    config_path: Path
    session_store: AgentSessionStore | None = None
    subagent_orchestrator: "SessionOrchestrator | None" = None
    on_inbound_message: Callable[[str], None] | None = None


class ChannelPlugin(Protocol):
    """Channel plugin lifecycle contract."""

    id: str

    async def start(self, ctx: ChannelContext) -> None:
        """Start plugin and subscribe inbound events."""

    async def stop(self) -> None:
        """Stop plugin and release resources."""

    async def send(self, target: str, content: str, **kwargs: Any) -> dict[str, Any]:
        """Send outbound message to a channel target."""

    def snapshot(self) -> dict[str, Any]:
        """Return plugin runtime status snapshot."""
