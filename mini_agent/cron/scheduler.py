"""Cron scheduler loop."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from mini_agent.channels.logging import log_channel_event

from .delivery import CronDelivery
from .executor import CronExecutor
from .models import CronRun, utc_now_iso
from .store import CronStore


class CronScheduler:
    """Poll store for due jobs and execute them."""

    def __init__(
        self,
        store: CronStore,
        executor: CronExecutor,
        delivery: CronDelivery,
        poll_interval_sec: float = 5.0,
        max_concurrency: int = 2,
    ):
        self._store = store
        self._executor = executor
        self._delivery = delivery
        self._poll_interval = max(0.5, float(poll_interval_sec))
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._loop_task: asyncio.Task | None = None
        self._running_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        if self._loop_task is not None:
            return
        self._loop_task = asyncio.create_task(self._loop(), name="grape-agent-cron-scheduler")
        log_channel_event("cron", "scheduler.start", poll_interval=self._poll_interval)

    async def stop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
            self._loop_task = None

        tasks = list(self._running_tasks)
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._running_tasks.clear()
        log_channel_event("cron", "scheduler.stop")

    async def trigger_job(self, job_id: str) -> CronRun | None:
        job = await self._store.get_job(job_id)
        if job is None:
            return None
        now_iso = utc_now_iso()
        await self._store.mark_job_scheduled(job.id, now_iso)
        return await self._run_job(job, scheduled_at=now_iso)

    def snapshot(self) -> dict:
        return {
            "running": self._loop_task is not None and not self._loop_task.done(),
            "active_jobs": len(self._running_tasks),
        }

    async def _loop(self) -> None:
        while True:
            now_iso = utc_now_iso()
            due = await self._store.due_jobs(now_iso)
            for job in due:
                if self._semaphore.locked():
                    break
                await self._store.mark_job_scheduled(job.id, now_iso)
                task = asyncio.create_task(self._run_job_guarded(job, now_iso))
                self._running_tasks.add(task)
                task.add_done_callback(lambda done: self._running_tasks.discard(done))
            await asyncio.sleep(self._poll_interval)

    async def _run_job_guarded(self, job, scheduled_at: str) -> None:
        async with self._semaphore:
            await self._run_job(job, scheduled_at=scheduled_at)

    async def _run_job(self, job, scheduled_at: str) -> CronRun:
        run = await self._executor.execute(job, scheduled_at=scheduled_at)
        await self._store.append_run(run)
        delivery_res = await self._delivery.deliver(job, run)
        if not delivery_res.get("ok"):
            log_channel_event(
                "cron",
                "scheduler.delivery.error",
                job_id=job.id,
                run_id=run.run_id,
                error=delivery_res.get("error"),
            )
        return run
