"""Gateway cron handlers."""

from __future__ import annotations

from grape_agent.cron.models import CronJob


def handle_cron_status(_params: dict, ctx, _conn) -> dict:
    if ctx.cron_store is None or ctx.cron_scheduler is None:
        return {"enabled": False}
    return {
        "enabled": True,
        "scheduler": ctx.cron_scheduler.snapshot(),
    }


async def handle_cron_jobs_list(params: dict, ctx, _conn) -> dict:
    if ctx.cron_store is None:
        return {"ok": False, "error": "cron store unavailable"}
    jobs = await ctx.cron_store.list_jobs()
    return {"ok": True, "total": len(jobs), "items": [job.model_dump(mode="json") for job in jobs]}


async def handle_cron_jobs_upsert(params: dict, ctx, _conn) -> dict:
    if ctx.cron_store is None:
        return {"ok": False, "error": "cron store unavailable"}

    payload = params.get("job", {})
    if not isinstance(payload, dict):
        return {"ok": False, "error": "job must be an object"}

    try:
        CronJob.model_validate(payload)
    except Exception as exc:
        return {"ok": False, "error": f"invalid job payload: {exc}"}

    job = await ctx.cron_store.upsert_job(payload)
    return {"ok": True, "job": job.model_dump(mode="json")}


async def handle_cron_jobs_delete(params: dict, ctx, _conn) -> dict:
    if ctx.cron_store is None:
        return {"ok": False, "error": "cron store unavailable"}

    job_id = str(params.get("job_id", "")).strip()
    if not job_id:
        return {"ok": False, "error": "missing required param: job_id"}

    removed = await ctx.cron_store.delete_job(job_id)
    return {"ok": True, "removed": removed}


async def handle_cron_runs_list(params: dict, ctx, _conn) -> dict:
    if ctx.cron_store is None:
        return {"ok": False, "error": "cron store unavailable"}

    job_id = params.get("job_id")
    limit = int(params.get("limit", 50))
    runs = await ctx.cron_store.list_runs(
        job_id=(str(job_id).strip() if isinstance(job_id, str) and job_id.strip() else None),
        limit=limit,
    )
    return {"ok": True, "total": len(runs), "items": [run.model_dump(mode="json") for run in runs]}


async def handle_cron_trigger(params: dict, ctx, _conn) -> dict:
    if ctx.cron_scheduler is None:
        return {"ok": False, "error": "cron scheduler unavailable"}
    job_id = str(params.get("job_id", "")).strip()
    if not job_id:
        return {"ok": False, "error": "missing required param: job_id"}
    run = await ctx.cron_scheduler.trigger_job(job_id)
    if run is None:
        return {"ok": False, "error": f"job not found: {job_id}"}
    return {"ok": True, "run": run.model_dump(mode="json")}
