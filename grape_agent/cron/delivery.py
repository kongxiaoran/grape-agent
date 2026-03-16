"""Cron result delivery."""

from __future__ import annotations

from grape_agent.channels.logging import log_channel_event

from .models import CronJob, CronRun


class CronDelivery:
    """Deliver cron run results to configured channels."""

    def __init__(self, channels_runtime=None):
        self._channels_runtime = channels_runtime

    async def deliver(self, job: CronJob, run: CronRun) -> dict:
        target = job.channel_target
        if not target:
            return {"ok": True, "skipped": True, "reason": "channel_target_not_configured"}
        if self._channels_runtime is None:
            return {"ok": False, "error": "channels runtime unavailable"}

        channel = str(target.get("channel", "")).strip()
        receive = str(target.get("target", "")).strip()
        options = target.get("options", {})
        if not isinstance(options, dict):
            options = {}
        if not channel or not receive:
            return {"ok": False, "error": "invalid channel_target, require channel and target"}

        body = self._build_message(job, run)
        result = await self._channels_runtime.send(
            channel_id=channel,
            target=receive,
            content=body,
            **options,
        )
        log_channel_event(
            "cron",
            "delivery.send",
            job_id=job.id,
            run_id=run.run_id,
            channel=channel,
            target=receive,
            ok=result.get("ok"),
        )
        return result

    @staticmethod
    def _build_message(job: CronJob, run: CronRun) -> str:
        lines = [
            f"[cron] job={job.id}",
            f"status={run.status}",
            f"run_id={run.run_id}",
        ]
        if run.result_preview:
            lines.append(f"result:\n{run.result_preview}")
        if run.error:
            lines.append(f"error:\n{run.error}")
        return "\n".join(lines)
