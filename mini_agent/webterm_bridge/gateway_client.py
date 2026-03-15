"""Async gateway TCP client for webterm bridge."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4


class GatewayClientError(RuntimeError):
    """Raised when gateway request fails."""


class GatewayTcpClient:
    """Simple line-delimited JSON TCP client for grape-agent gateway."""

    def __init__(self, host: str, port: int, token: str, client_id: str = "webterm-bridge"):
        self._host = host
        self._port = port
        self._token = token
        self._client_id = client_id

    async def call(self, method: str, params: dict | None = None, timeout_sec: float = 15.0) -> dict:
        request = {
            "id": f"wbg_{uuid4().hex[:12]}",
            "method": method,
            "params": params or {},
            "auth": {
                "token": self._token,
                "client_id": self._client_id,
                "role": "operator",
            },
        }

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=timeout_sec,
            )
        except Exception as exc:
            raise GatewayClientError(f"gateway connect failed: {type(exc).__name__}: {exc}") from exc

        try:
            wire = json.dumps(request, ensure_ascii=False) + "\n"
            writer.write(wire.encode("utf-8"))
            await asyncio.wait_for(writer.drain(), timeout=timeout_sec)
            raw = await asyncio.wait_for(reader.readline(), timeout=timeout_sec)
            if not raw:
                raise GatewayClientError("gateway closed connection without response")

            response = json.loads(raw.decode("utf-8", errors="replace"))
            if not isinstance(response, dict):
                raise GatewayClientError("invalid gateway response shape")
            if not response.get("ok", False):
                error = response.get("error") or {}
                code = error.get("code", "UNKNOWN")
                message = error.get("message", "request failed")
                raise GatewayClientError(f"gateway error {code}: {message}")
            result = response.get("result", {})
            if not isinstance(result, dict):
                raise GatewayClientError("invalid gateway result shape")
            return result
        except asyncio.TimeoutError as exc:
            raise GatewayClientError(f"gateway timeout after {timeout_sec:.1f}s during {method}") from exc
        except json.JSONDecodeError as exc:
            raise GatewayClientError(f"invalid gateway response JSON: {exc}") from exc
        except GatewayClientError:
            raise
        except Exception as exc:
            raise GatewayClientError(f"gateway request failed: {type(exc).__name__}: {exc}") from exc
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
