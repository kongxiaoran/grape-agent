"""Cron store with JSON persistence."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .models import CronJob, CronRun, compute_next_run_at, utc_now_iso


class CronStore:
    """Persist cron jobs and run history."""

    def __init__(self, store_path: str, max_runs: int = 500):
        self._path = Path(store_path).expanduser()
        self._max_runs = max_runs
        self._lock = asyncio.Lock()
        self._jobs: dict[str, CronJob] = {}
        self._runs: list[CronRun] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        jobs_raw = raw.get("jobs", []) if isinstance(raw, dict) else []
        runs_raw = raw.get("runs", []) if isinstance(raw, dict) else []
        for item in jobs_raw:
            try:
                job = CronJob.model_validate(item)
            except Exception:
                continue
            self._jobs[job.id] = job
        for item in runs_raw:
            try:
                run = CronRun.model_validate(item)
            except Exception:
                continue
            self._runs.append(run)
        self._runs = self._runs[-self._max_runs :]

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "jobs": [job.model_dump(mode="json") for job in self._jobs.values()],
            "runs": [run.model_dump(mode="json") for run in self._runs[-self._max_runs :]],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def list_jobs(self) -> list[CronJob]:
        async with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.id)

    async def get_job(self, job_id: str) -> CronJob | None:
        async with self._lock:
            return self._jobs.get(job_id.strip())

    async def upsert_job(self, payload: dict[str, Any]) -> CronJob:
        async with self._lock:
            job = CronJob.model_validate(payload)
            existing = self._jobs.get(job.id)
            now = utc_now_iso()
            if existing is not None:
                job.created_at = existing.created_at
                if job.next_run_at is None:
                    job.next_run_at = existing.next_run_at
                if job.last_run_at is None:
                    job.last_run_at = existing.last_run_at
            if job.next_run_at is None:
                next_run = compute_next_run_at(job.schedule, after=_parse_iso(now))
                job.next_run_at = next_run.isoformat()
            job.updated_at = now
            self._jobs[job.id] = job
            self._persist()
            return job

    async def delete_job(self, job_id: str) -> bool:
        async with self._lock:
            removed = self._jobs.pop(job_id.strip(), None)
            self._persist()
            return removed is not None

    async def due_jobs(self, now_iso: str) -> list[CronJob]:
        async with self._lock:
            due: list[CronJob] = []
            for job in self._jobs.values():
                if not job.enabled or not job.next_run_at:
                    continue
                if job.next_run_at <= now_iso:
                    due.append(job)
            due.sort(key=lambda item: item.next_run_at or "")
            return due

    async def mark_job_scheduled(self, job_id: str, now_iso: str) -> CronJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            now_dt = _parse_iso(now_iso)
            job.last_run_at = now_iso
            job.next_run_at = compute_next_run_at(job.schedule, after=now_dt).isoformat()
            job.updated_at = now_iso
            self._jobs[job.id] = job
            self._persist()
            return job

    async def append_run(self, run: CronRun) -> None:
        async with self._lock:
            self._runs.append(run)
            self._runs = self._runs[-self._max_runs :]
            self._persist()

    async def update_run(self, run_id: str, **updates: Any) -> CronRun | None:
        async with self._lock:
            for idx, run in enumerate(self._runs):
                if run.run_id != run_id:
                    continue
                merged = run.model_copy(update=updates)
                self._runs[idx] = merged
                self._persist()
                return merged
            return None

    async def list_runs(self, job_id: str | None = None, limit: int = 50) -> list[CronRun]:
        async with self._lock:
            rows = list(self._runs)
        if job_id:
            rows = [row for row in rows if row.job_id == job_id]
        rows.sort(key=lambda item: item.started_at, reverse=True)
        return rows[: max(1, limit)]


def _parse_iso(value: str):
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)
