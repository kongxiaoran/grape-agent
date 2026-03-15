"""Gateway protocol and runtime context types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from mini_agent.config import Config, GatewayConfig
from mini_agent.session_store import AgentSessionStore

if TYPE_CHECKING:
    from mini_agent.agents.orchestrator import SessionOrchestrator
    from mini_agent.channels.runtime import ChannelRuntime
    from mini_agent.cron.scheduler import CronScheduler
    from mini_agent.cron.store import CronStore

GatewayRole = Literal["operator", "channel", "node"]

ERR_INVALID_REQUEST = "INVALID_REQUEST"
ERR_UNAUTHORIZED = "UNAUTHORIZED"
ERR_METHOD_NOT_FOUND = "METHOD_NOT_FOUND"
ERR_INTERNAL = "INTERNAL_ERROR"


class RequestAuth(BaseModel):
    """Authentication payload provided by the caller."""

    token: str | None = None
    client_id: str = "anonymous"
    role: GatewayRole = "operator"


class GatewayRequest(BaseModel):
    """Gateway request envelope."""

    id: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    auth: RequestAuth = Field(default_factory=RequestAuth)


class GatewayError(BaseModel):
    """Standardized gateway error payload."""

    code: str
    message: str


class GatewayResponse(BaseModel):
    """Gateway response envelope."""

    id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: GatewayError | None = None


@dataclass(slots=True)
class ConnectionContext:
    """Connection/request identity context."""

    client_id: str
    role: GatewayRole
    remote: str = "unknown"


@dataclass(slots=True)
class GatewayContext:
    """Runtime objects shared by all gateway handlers."""

    app_name: str
    started_at: datetime
    config: Config
    gateway_config: GatewayConfig
    session_store: AgentSessionStore
    channels_runtime: "ChannelRuntime | None" = None
    subagent_orchestrator: "SessionOrchestrator | None" = None
    cron_store: "CronStore | None" = None
    cron_scheduler: "CronScheduler | None" = None


def make_ok(request_id: str, result: dict[str, Any] | None = None) -> GatewayResponse:
    return GatewayResponse(id=request_id, ok=True, result=result or {}, error=None)


def make_err(request_id: str, code: str, message: str) -> GatewayResponse:
    return GatewayResponse(
        id=request_id,
        ok=False,
        result=None,
        error=GatewayError(code=code, message=message),
    )
