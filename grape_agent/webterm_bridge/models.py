"""Pydantic models for webterm bridge API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OpenSessionRequest(BaseModel):
    host: str
    scope: str = "default"
    user: str = "unknown"
    agent_id: str | None = None
    reuse_existing: bool = True


class OpenSessionResponse(BaseModel):
    ok: bool = True
    bridge_session_id: str
    session_key: str
    created: bool


class IngestRequest(BaseModel):
    text: str
    stream: str = "stdout"
    trace_id: str | None = None
    timestamp_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SuggestRequest(BaseModel):
    question: str | None = None
    max_lines: int = Field(default=200, ge=1, le=5000)


class SuggestResponse(BaseModel):
    ok: bool = True
    bridge_session_id: str
    session_key: str
    command: str
    risk: str
    reason: str
    summary: str
    requires_confirm: bool
    raw_response: str


class ExecuteRequest(BaseModel):
    command: str
    wrap_markers: bool = True
    trace_id: str | None = None


class ExecuteResponse(BaseModel):
    ok: bool = True
    bridge_session_id: str
    command: str
    wrapped_command: str
    trace_id: str
    risk: str
    requires_confirm: bool


class BridgeSessionView(BaseModel):
    bridge_session_id: str
    session_key: str
    host: str
    scope: str
    user: str
    created_at: str
    updated_at: str
    buffered_lines: int
    recent_output_preview: str


class SessionStateResponse(BaseModel):
    ok: bool = True
    session: BridgeSessionView
