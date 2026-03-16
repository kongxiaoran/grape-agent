"""Gateway auth helpers."""

from __future__ import annotations

from grape_agent.config import GatewayAuthConfig

from .protocol import ConnectionContext, GatewayRequest


def build_connection_context(request: GatewayRequest, remote: str) -> ConnectionContext:
    """Build connection context from request auth payload."""
    return ConnectionContext(
        client_id=request.auth.client_id,
        role=request.auth.role,
        remote=remote,
    )


def is_authorized(request: GatewayRequest, auth_config: GatewayAuthConfig) -> bool:
    """Validate request auth token against config."""
    if not auth_config.enabled:
        return True
    token = request.auth.token
    return bool(token) and token == auth_config.token

