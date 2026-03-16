"""Gateway TCP server."""

from __future__ import annotations

import asyncio
import contextlib
import json

from pydantic import ValidationError

from grape_agent.config import GatewayConfig

from .auth import build_connection_context, is_authorized
from .protocol import ERR_INVALID_REQUEST, ERR_UNAUTHORIZED, GatewayRequest, GatewayResponse, make_err
from .router import GatewayRouter


class GatewayServer:
    """Line-delimited JSON gateway server."""

    def __init__(self, config: GatewayConfig, router: GatewayRouter):
        self._config = config
        self._router = router
        self._server: asyncio.AbstractServer | None = None
        self._serve_task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._config.enabled:
            return
        if self._server is not None:
            return

        self._server = await asyncio.start_server(
            self._handle_client,
            host=self._config.host,
            port=self._config.port,
        )
        self._serve_task = asyncio.create_task(self._server.serve_forever())
        print(f"[Gateway] Listening on {self._config.host}:{self._config.port}")

    async def stop(self) -> None:
        if self._serve_task is not None:
            self._serve_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._serve_task
            self._serve_task = None

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            print("[Gateway] Stopped.")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        remote = f"{peer[0]}:{peer[1]}" if isinstance(peer, tuple) and len(peer) >= 2 else "unknown"

        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break

                payload_text = line.decode("utf-8", errors="replace").strip()
                if not payload_text:
                    continue

                response = await self._dispatch_payload(payload_text, remote)
                await self._write_response(writer, response)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _dispatch_payload(self, payload_text: str, remote: str) -> GatewayResponse:
        request_id = "unknown"
        try:
            raw = json.loads(payload_text)
            if isinstance(raw, dict) and "id" in raw:
                request_id = str(raw["id"])
            req = GatewayRequest.model_validate(raw)
        except json.JSONDecodeError:
            return make_err(request_id, ERR_INVALID_REQUEST, "request must be valid JSON object")
        except ValidationError as exc:
            return make_err(request_id, ERR_INVALID_REQUEST, f"invalid request: {exc.errors()}")

        conn = build_connection_context(req, remote)
        if not is_authorized(req, self._config.auth):
            return make_err(req.id, ERR_UNAUTHORIZED, "invalid or missing auth token")

        print(f"[Gateway] inbound client={conn.client_id} role={conn.role} method={req.method} remote={conn.remote}")
        resp = await self._router.dispatch(req, conn)
        if resp.ok:
            print(f"[Gateway] outbound client={conn.client_id} method={req.method} ok=true")
        else:
            code = resp.error.code if resp.error else "UNKNOWN"
            print(f"[Gateway] outbound client={conn.client_id} method={req.method} ok=false code={code}")
        return resp

    @staticmethod
    async def _write_response(writer: asyncio.StreamWriter, response: GatewayResponse) -> None:
        encoded = json.dumps(response.model_dump(), ensure_ascii=False) + "\n"
        writer.write(encoded.encode("utf-8"))
        await writer.drain()

