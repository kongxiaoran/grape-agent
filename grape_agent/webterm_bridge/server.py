"""HTTP bridge service for browser terminal plugin integration."""

from __future__ import annotations

import argparse
from pathlib import Path

from grape_agent.config import Config

from .gateway_client import GatewayClientError, GatewayTcpClient
from .models import (
    ExecuteRequest,
    ExecuteResponse,
    IngestRequest,
    OpenSessionRequest,
    OpenSessionResponse,
    SessionStateResponse,
    SuggestRequest,
    SuggestResponse,
)
from .session_manager import WebtermSessionManager


def create_app(config: Config):
    """Create FastAPI app with configured webterm bridge manager."""
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:
        raise RuntimeError("fastapi is required for webterm bridge. Install with `pip install fastapi uvicorn`.") from exc

    bridge_cfg = config.webterm_bridge
    gateway_host = bridge_cfg.gateway_host or config.gateway.host
    gateway_port = bridge_cfg.gateway_port or config.gateway.port
    gateway_token = bridge_cfg.gateway_token or config.gateway.auth.token
    if not gateway_token:
        raise RuntimeError("webterm bridge requires gateway token (webterm_bridge.gateway_token or gateway.auth.token)")

    gateway_client = GatewayTcpClient(
        host=gateway_host,
        port=gateway_port,
        token=gateway_token,
        client_id=bridge_cfg.gateway_client_id,
    )
    manager = WebtermSessionManager(config=bridge_cfg, gateway=gateway_client)

    app = FastAPI(title="Grape-Agent Webterm Bridge", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def _require_auth(
        authorization: str | None = Header(default=None),
        x_bridge_token: str | None = Header(default=None),
    ) -> None:
        token = (x_bridge_token or "").strip()
        auth = (authorization or "").strip()
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
        if token != bridge_cfg.token:
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "webterm-bridge"}

    @app.post("/v1/session/open", response_model=OpenSessionResponse, dependencies=[Depends(_require_auth)])
    async def open_session(body: OpenSessionRequest):
        try:
            session, created = await manager.open_session(
                host=body.host,
                scope=body.scope,
                user=body.user,
                agent_id=body.agent_id,
                reuse_existing=body.reuse_existing,
            )
            return OpenSessionResponse(
                bridge_session_id=session.bridge_session_id,
                session_key=session.session_key,
                created=created,
            )
        except GatewayClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/v1/session/{bridge_session_id}/ingest", dependencies=[Depends(_require_auth)])
    async def ingest_output(bridge_session_id: str, body: IngestRequest):
        try:
            session = manager.ingest(bridge_session_id=bridge_session_id, text=body.text, stream=body.stream)
            return {"ok": True, "bridge_session_id": session.bridge_session_id, "buffered_lines": len(session.output_lines)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/session/{bridge_session_id}/suggest", response_model=SuggestResponse, dependencies=[Depends(_require_auth)])
    async def suggest_command(bridge_session_id: str, body: SuggestRequest):
        try:
            session = manager.get_session_view(bridge_session_id)
            suggestion = await manager.suggest(bridge_session_id=bridge_session_id, question=body.question, max_lines=body.max_lines)
            return SuggestResponse(
                bridge_session_id=bridge_session_id,
                session_key=session.session_key,
                command=suggestion["command"],
                risk=suggestion["risk"],
                reason=suggestion["reason"],
                summary=suggestion["summary"],
                requires_confirm=suggestion["requires_confirm"],
                raw_response=suggestion["raw_response"],
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GatewayClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/v1/session/{bridge_session_id}/execute", response_model=ExecuteResponse, dependencies=[Depends(_require_auth)])
    async def execute_command(bridge_session_id: str, body: ExecuteRequest):
        try:
            prepared = manager.prepare_execute(
                bridge_session_id=bridge_session_id,
                command=body.command,
                wrap_markers=body.wrap_markers,
                trace_id=body.trace_id,
            )
            return ExecuteResponse(
                bridge_session_id=bridge_session_id,
                command=prepared["command"],
                wrapped_command=prepared["wrapped_command"],
                trace_id=prepared["trace_id"],
                risk=prepared["risk"],
                requires_confirm=prepared["requires_confirm"],
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/session/{bridge_session_id}/state", response_model=SessionStateResponse, dependencies=[Depends(_require_auth)])
    async def session_state(bridge_session_id: str):
        try:
            view = manager.get_session_view(bridge_session_id)
            return SessionStateResponse(session=view)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/v1/session/{bridge_session_id}", dependencies=[Depends(_require_auth)])
    async def close_session(bridge_session_id: str):
        removed = manager.close_session(bridge_session_id)
        return {"ok": True, "removed": removed}

    return app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grape-Agent webterm local bridge")
    parser.add_argument("--config", default=None, help="settings.json path")
    parser.add_argument("--host", default=None, help="override webterm bridge host")
    parser.add_argument("--port", type=int, default=None, help="override webterm bridge port")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint for webterm bridge."""
    args = _parse_args()
    config_path = Path(args.config).expanduser() if args.config else Config.get_default_config_path()
    config = Config.from_yaml(config_path)
    bridge_cfg = config.webterm_bridge
    host = args.host or bridge_cfg.host
    port = args.port or bridge_cfg.port

    app = create_app(config)
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required for webterm bridge. Install with `pip install uvicorn`.") from exc
    uvicorn.run(app, host=host, port=port)


__all__ = ["create_app", "main"]
