"""Gateway method router and dispatcher."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from .protocol import (
    ERR_INTERNAL,
    ERR_METHOD_NOT_FOUND,
    ConnectionContext,
    GatewayContext,
    GatewayRequest,
    GatewayResponse,
    make_err,
    make_ok,
)

Handler = Callable[[dict, GatewayContext, ConnectionContext], Awaitable[dict] | dict]


class GatewayRouter:
    """Simple method router for gateway requests."""

    def __init__(self, context: GatewayContext):
        self._context = context
        self._handlers: dict[str, Handler] = {}

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    async def dispatch(self, req: GatewayRequest, conn: ConnectionContext) -> GatewayResponse:
        handler = self._handlers.get(req.method)
        if handler is None:
            return make_err(req.id, ERR_METHOD_NOT_FOUND, f"unknown method: {req.method}")

        try:
            result = handler(req.params, self._context, conn)
            if inspect.isawaitable(result):
                result = await result
            if result is None:
                result = {}
            if not isinstance(result, dict):
                return make_err(req.id, ERR_INTERNAL, "handler must return dict")
            return make_ok(req.id, result)
        except Exception as exc:  # pragma: no cover - exercised by tests via message check
            return make_err(req.id, ERR_INTERNAL, f"{type(exc).__name__}: {exc}")
