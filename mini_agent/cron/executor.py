"""Cron job executor."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable
from uuid import uuid4

from mini_agent.channels.logging import log_channel_event
from mini_agent.session_store import AgentSession

from .models import CronJob, CronRun, utc_now_iso


class CronExecutor:
    """Execute one cron job in isolated or sticky session."""

    def __init__(
        self,
        create_session: Callable[..., Awaitable[AgentSession]],
        default_timeout_sec: int = 300,
    ):
        self._create_session = create_session
        self._default_timeout_sec = max(5, int(default_timeout_sec))

    async def execute(self, job: CronJob, scheduled_at: str) -> CronRun:
        run_id = f"cronrun_{uuid4().hex[:12]}"
        session_id = self._session_id_for(job)
        session = await self._create_session(
            agent_id=job.agent_id,
            channel="cron",
            session_id=session_id,
            depth=0,
            parent_key=None,
        )

        run = CronRun(
            run_id=run_id,
            job_id=job.id,
            status="running",
            scheduled_at=scheduled_at,
            started_at=utc_now_iso(),
            session_key=session.key,
        )

        timeout_sec = int(job.timeout_sec or self._default_timeout_sec)
        try:
            async with session.lock:
                session.agent.add_user_message(job.task)
                result = await asyncio.wait_for(session.agent.run(), timeout=timeout_sec)
            text = result if isinstance(result, str) else str(result)
            run.status = "completed"
            run.result_preview = text[:500]
            run.finished_at = utc_now_iso()
            return run
        except asyncio.TimeoutError:
            run.status = "timeout"
            run.error = f"timeout after {timeout_sec}s"
            run.finished_at = utc_now_iso()
            return run
        except Exception as exc:
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished_at = utc_now_iso()
            return run
        finally:
            log_channel_event(
                "cron",
                "executor.run",
                job_id=job.id,
                run_id=run_id,
                status=run.status,
                session_key=run.session_key,
            )

    @staticmethod
    def _session_id_for(job: CronJob) -> str:
        if job.session_target == "sticky":
            return f"job_{job.id}"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"job_{job.id}_{stamp}_{uuid4().hex[:6]}"
