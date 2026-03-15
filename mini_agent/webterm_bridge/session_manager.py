"""In-memory webterm bridge session manager."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from mini_agent.config import WebtermBridgeConfig

from .gateway_client import GatewayClientError, GatewayTcpClient
from .models import BridgeSessionView
from .profile_store import load_profiles, resolve_profile_context
from .utils import classify_command_risk, extract_json_object, wrap_command


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class BridgeSession:
    bridge_session_id: str
    session_key: str
    host: str
    scope: str
    user: str
    created_at: str
    updated_at: str
    profile_context: str = ""
    output_lines: deque[str] = field(default_factory=deque)
    last_suggestion: dict | None = None


class WebtermSessionManager:
    """Manage bridge sessions and route requests to gateway sessions.* methods."""

    def __init__(self, config: WebtermBridgeConfig, gateway: GatewayTcpClient):
        self._config = config
        self._gateway = gateway
        self._sessions: dict[str, BridgeSession] = {}
        self._session_key_index: dict[str, str] = {}
        self._logical_index: dict[str, str] = {}
        self._profiles = load_profiles(config.profile_path)

    async def open_session(
        self,
        *,
        host: str,
        scope: str,
        user: str,
        agent_id: str | None = None,
        reuse_existing: bool = True,
    ) -> tuple[BridgeSession, bool]:
        logical_key = f"{host.strip()}|{scope.strip()}|{user.strip()}"
        if reuse_existing and logical_key in self._logical_index:
            sid = self._logical_index[logical_key]
            existing = self._sessions.get(sid)
            if existing is not None:
                return existing, False

        spawn_result = await self._gateway.call(
            "sessions.spawn",
            {
                "parent_session_key": self._config.parent_session_key,
                "task": f"bootstrap webterm session host={host} scope={scope} user={user}",
                "mode": "create",
                "agent_id": (agent_id or self._config.default_agent_id),
            },
        )
        if not spawn_result.get("ok"):
            raise GatewayClientError(spawn_result.get("error", "sessions.spawn failed"))

        session_key = str(spawn_result.get("child_session_key", "")).strip()
        if not session_key:
            raise GatewayClientError("sessions.spawn succeeded but child_session_key is empty")

        sid = f"wbs_{uuid4().hex[:12]}"
        now = _utc_now()
        created = BridgeSession(
            bridge_session_id=sid,
            session_key=session_key,
            host=host.strip(),
            scope=scope.strip(),
            user=user.strip(),
            created_at=now,
            updated_at=now,
            profile_context=resolve_profile_context(self._profiles, host.strip(), scope.strip(), user.strip()),
            output_lines=deque(maxlen=self._config.max_buffer_lines),
        )
        self._sessions[sid] = created
        self._session_key_index[session_key] = sid
        self._logical_index[logical_key] = sid
        return created, True

    def ingest(self, bridge_session_id: str, text: str, stream: str = "stdout") -> BridgeSession:
        session = self._require_session(bridge_session_id)
        cleaned = text.rstrip("\n")
        if not cleaned:
            return session
        prefixed = f"[{stream}] {cleaned}"
        for line in prefixed.splitlines():
            if line.strip():
                session.output_lines.append(line)
        session.updated_at = _utc_now()
        return session

    async def suggest(self, bridge_session_id: str, question: str | None = None, max_lines: int = 200) -> dict:
        session = self._require_session(bridge_session_id)
        lines = list(session.output_lines)[-max(1, min(max_lines, len(session.output_lines) or 1)) :]
        context = "\n".join(lines)
        if len(context) > self._config.max_context_chars:
            context = context[-self._config.max_context_chars :]

        prompt = self._build_suggestion_prompt(
            context=context,
            question=question,
            profile_context=session.profile_context,
        )
        send_result = await self._gateway.call(
            "sessions.send",
            {
                "session_key": session.session_key,
                "message": prompt,
                "wait": True,
            },
            timeout_sec=90.0,
        )
        if not send_result.get("ok"):
            raise GatewayClientError(send_result.get("error", "sessions.send failed"))

        raw = str(send_result.get("result") or "")
        parsed = extract_json_object(raw) or {}
        command = str(parsed.get("command", "")).strip()
        risk = str(parsed.get("risk", "medium")).strip().lower()
        reason = str(parsed.get("reason", parsed.get("analysis", ""))).strip()
        summary = str(parsed.get("summary", "")).strip()
        if risk not in {"low", "medium", "high"}:
            risk = "medium"

        suggestion = {
            "command": command,
            "risk": risk,
            "reason": reason,
            "summary": summary,
            "requires_confirm": bool(self._config.command_require_confirm or risk != "low"),
            "raw_response": raw,
        }
        session.last_suggestion = suggestion
        session.updated_at = _utc_now()
        return suggestion

    def prepare_execute(self, bridge_session_id: str, command: str, wrap_markers: bool, trace_id: str | None) -> dict:
        session = self._require_session(bridge_session_id)
        cleaned = command.strip()
        if not cleaned:
            raise ValueError("command cannot be empty")

        risk = classify_command_risk(
            cleaned,
            denylist=self._config.command_denylist,
            allowlist=self._config.command_allowlist,
        )
        if wrap_markers and self._config.command_wrap_markers:
            marker, wrapped = wrap_command(cleaned, trace_id=trace_id)
        else:
            marker = trace_id or f"tr_{uuid4().hex[:12]}"
            wrapped = cleaned

        session.updated_at = _utc_now()
        return {
            "command": cleaned,
            "wrapped_command": wrapped,
            "trace_id": marker,
            "risk": risk,
            "requires_confirm": bool(self._config.command_require_confirm or risk != "low"),
        }

    def get_session_view(self, bridge_session_id: str) -> BridgeSessionView:
        session = self._require_session(bridge_session_id)
        preview = "\n".join(list(session.output_lines)[-20:])
        return BridgeSessionView(
            bridge_session_id=session.bridge_session_id,
            session_key=session.session_key,
            host=session.host,
            scope=session.scope,
            user=session.user,
            created_at=session.created_at,
            updated_at=session.updated_at,
            buffered_lines=len(session.output_lines),
            recent_output_preview=preview,
        )

    def close_session(self, bridge_session_id: str) -> bool:
        session = self._sessions.pop(bridge_session_id, None)
        if session is None:
            return False
        self._session_key_index.pop(session.session_key, None)
        logical = f"{session.host}|{session.scope}|{session.user}"
        self._logical_index.pop(logical, None)
        return True

    def _require_session(self, bridge_session_id: str) -> BridgeSession:
        sid = bridge_session_id.strip()
        session = self._sessions.get(sid)
        if session is None:
            raise KeyError(f"bridge session not found: {bridge_session_id}")
        return session

    @staticmethod
    def _build_suggestion_prompt(context: str, question: str | None = None, profile_context: str = "") -> str:
        ask = (question or "请给出下一条最有价值的排障命令").strip()
        profile_block = profile_context.strip() or "(无)"
        context_block = context or "(空)"
        return (
            "你是生产排障助手。基于用户问题、环境画像与可用上下文，给出下一条建议命令。\n"
            "要求：\n"
            "1) 命令必须可直接在 Linux shell 执行。\n"
            "2) 避免破坏性命令（如 rm/reboot/shutdown）。\n"
            "3) 只返回 JSON 对象，不要额外文本。\n"
            "4) JSON schema: "
            '{"summary":"", "command":"", "risk":"low|medium|high", "reason":""}\n'
            "5) 优先利用“环境画像”里的日志路径、命名规则、项目约定。\n"
            f"用户问题: {ask}\n"
            "环境画像如下：\n"
            "-----\n"
            f"{profile_block}\n"
            "-----\n"
            "可用上下文如下（可能为空）：\n"
            "-----\n"
            f"{context_block}\n"
            "-----\n"
        )
