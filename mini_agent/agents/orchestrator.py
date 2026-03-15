"""Subagent session orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Awaitable, Callable
from uuid import uuid4

from mini_agent.session_store import AgentSession, AgentSessionStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SessionRun:
    """One asynchronous run record."""

    run_id: str
    session_key: str
    status: str
    created_at: str
    updated_at: str
    result: str | None = None
    error: str | None = None


class SessionOrchestrator:
    """Create/list/send subagent sessions with depth control."""

    def __init__(
        self,
        session_store: AgentSessionStore,
        create_session: Callable[..., Awaitable[AgentSession]],
        enabled: bool = True,
        max_depth: int = 2,
    ):
        self._store = session_store
        self._create_session = create_session
        self._enabled = bool(enabled)
        self._max_depth = max(0, int(max_depth))
        self._runs: dict[str, SessionRun] = {}
        self._run_tasks: dict[str, asyncio.Task] = {}

    @property
    def max_depth(self) -> int:
        return self._max_depth

    async def spawn(
        self,
        *,
        parent_session_key: str,
        task: str,
        agent_id: str | None = None,
        mode: str = "run",
        wait: bool = False,
    ) -> dict:
        if not self._enabled:
            return {"ok": False, "error": "subagent orchestration is disabled"}

        parent = self._store.get_by_key(parent_session_key.strip())
        if parent is None:
            return {"ok": False, "error": f"parent session not found: {parent_session_key}"}

        if parent.depth >= self._max_depth:
            return {
                "ok": False,
                "error": f"max subagent depth reached: current={parent.depth}, max={self._max_depth}",
            }

        mode = mode.strip().lower()
        if mode not in {"run", "create"}:
            return {"ok": False, "error": f"unsupported mode: {mode}"}

        target_agent = (agent_id or parent.agent_id).strip() or parent.agent_id
        child_session_id = f"sub_{uuid4().hex[:10]}"

        child = await self._create_session(
            agent_id=target_agent,
            channel=parent.channel,
            session_id=child_session_id,
            parent_key=parent.key,
            depth=parent.depth + 1,
        )

        result = {
            "ok": True,
            "status": "created" if mode == "create" else "running",
            "child_session_key": child.key,
            "parent_session_key": parent.key,
            "agent_id": child.agent_id,
            "depth": child.depth,
        }
        if mode == "create":
            return result

        send_res = await self.send(session_key=child.key, message=task, wait=wait)
        result.update({"dispatch": send_res})
        return result

    def list_sessions(self, *, channel: str | None = None, agent_id: str | None = None, limit: int = 20) -> list[dict]:
        rows: list[dict] = []
        for session in self._store.all_sessions():
            if channel and session.channel != channel:
                continue
            if agent_id and session.agent_id != agent_id:
                continue
            rows.append(
                {
                    "key": session.key,
                    "agent_id": session.agent_id,
                    "channel": session.channel,
                    "session_id": session.session_id,
                    "depth": session.depth,
                    "parent_key": session.parent_key,
                    "created_at": session.created_at,
                }
            )
        rows.sort(key=lambda x: x["created_at"], reverse=True)
        return rows[: max(1, limit)]

    def list_accessible_sessions(
        self,
        *,
        owner_session_key: str,
        channel: str | None = None,
        agent_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        rows = self.list_sessions(channel=channel, agent_id=agent_id, limit=10_000)
        filtered = [row for row in rows if self.is_accessible(owner_session_key, row["key"])]
        return filtered[: max(1, limit)]

    def history(self, *, session_key: str, limit: int = 50) -> dict:
        session = self._store.get_by_key(session_key.strip())
        if session is None:
            return {"ok": False, "error": f"session not found: {session_key}"}

        messages = session.agent.messages[-max(1, limit) :]
        items: list[dict] = []
        for msg in messages:
            raw = msg.content if isinstance(msg.content, str) else str(msg.content)
            preview = self._sanitize_message(raw)
            items.append(
                {
                    "role": msg.role,
                    "content_preview": preview,
                    "tool_calls": len(msg.tool_calls or []),
                }
            )
        return {"ok": True, "session_key": session.key, "total": len(items), "items": items}

    async def send(self, *, session_key: str, message: str, wait: bool = False) -> dict:
        session = self._store.get_by_key(session_key.strip())
        if session is None:
            return {"ok": False, "error": f"session not found: {session_key}"}

        if wait:
            run_id = f"run_{uuid4().hex[:12]}"
            run = self._create_run(run_id, session_key)
            await self._run_once(session, message, run)
            return {
                "ok": True,
                "accepted": True,
                "wait": True,
                "run_id": run_id,
                "status": run.status,
                "result": run.result,
                "error": run.error,
            }

        run_id = f"run_{uuid4().hex[:12]}"
        run = self._create_run(run_id, session_key)
        task = asyncio.create_task(self._run_once(session, message, run))
        self._run_tasks[run_id] = task
        task.add_done_callback(lambda _: self._run_tasks.pop(run_id, None))
        return {"ok": True, "accepted": True, "wait": False, "run_id": run_id, "status": "queued"}

    def get_run(self, run_id: str) -> dict | None:
        run = self._runs.get(run_id)
        if run is None:
            return None
        return {
            "run_id": run.run_id,
            "session_key": run.session_key,
            "status": run.status,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "result": run.result,
            "error": run.error,
        }

    def is_accessible(self, owner_session_key: str, target_session_key: str) -> bool:
        owner = owner_session_key.strip()
        target = target_session_key.strip()
        if not owner or not target:
            return False
        if owner == target:
            return True

        current = self._store.get_by_key(target)
        while current is not None and current.parent_key:
            if current.parent_key == owner:
                return True
            current = self._store.get_by_key(current.parent_key)
        return False

    def list_runs(self, *, session_key: str | None = None, limit: int = 20) -> list[dict]:
        rows = [self.get_run(run_id) for run_id in self._runs]
        rows = [row for row in rows if row is not None]
        if session_key:
            rows = [row for row in rows if row["session_key"] == session_key]
        rows.sort(key=lambda item: item["created_at"], reverse=True)
        return rows[: max(1, limit)]

    def _create_run(self, run_id: str, session_key: str) -> SessionRun:
        now = _utc_now()
        run = SessionRun(
            run_id=run_id,
            session_key=session_key,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        self._runs[run_id] = run
        return run

    async def _run_once(self, session: AgentSession, message: str, run: SessionRun) -> None:
        run.status = "running"
        run.updated_at = _utc_now()
        try:
            async with session.lock:
                session.agent.add_user_message(message)
                result = await session.agent.run()
            run.status = "completed"
            run.result = result if isinstance(result, str) else str(result)
            run.updated_at = _utc_now()
        except Exception as exc:  # pragma: no cover - exercised in integration
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            run.updated_at = _utc_now()

    @staticmethod
    def _sanitize_message(content: str) -> str:
        text = content.strip()
        text = re.sub(r"(?i)(api[_-]?key\s*[:=]\s*)\S+", r"\1[REDACTED]", text)
        text = re.sub(r"(?i)(token\s*[:=]\s*)\S+", r"\1[REDACTED]", text)
        if len(text) > 500:
            return text[:500] + "..."
        return text
