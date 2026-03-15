"""Built-in gateway handlers."""

from __future__ import annotations

from mini_agent.gateway.router import GatewayRouter

from .channels import handle_channels_send, handle_channels_status
from .cron import (
    handle_cron_jobs_delete,
    handle_cron_jobs_list,
    handle_cron_jobs_upsert,
    handle_cron_runs_list,
    handle_cron_status,
    handle_cron_trigger,
)
from .health import handle_health
from .sessions import (
    handle_sessions_history,
    handle_sessions_list,
    handle_sessions_run_get,
    handle_sessions_runs_list,
    handle_sessions_send,
    handle_sessions_spawn,
)
from .status import handle_status


def register_builtin_handlers(router: GatewayRouter) -> None:
    router.register("health", handle_health)
    router.register("status", handle_status)
    router.register("channels.status", handle_channels_status)
    router.register("channels.send", handle_channels_send)
    router.register("cron.status", handle_cron_status)
    router.register("cron.jobs.list", handle_cron_jobs_list)
    router.register("cron.jobs.upsert", handle_cron_jobs_upsert)
    router.register("cron.jobs.delete", handle_cron_jobs_delete)
    router.register("cron.runs.list", handle_cron_runs_list)
    router.register("cron.trigger", handle_cron_trigger)
    router.register("sessions.list", handle_sessions_list)
    router.register("sessions.spawn", handle_sessions_spawn)
    router.register("sessions.history", handle_sessions_history)
    router.register("sessions.send", handle_sessions_send)
    router.register("sessions.run.get", handle_sessions_run_get)
    router.register("sessions.runs.list", handle_sessions_runs_list)


__all__ = ["register_builtin_handlers"]
