"""Gateway status handler."""

from __future__ import annotations

from .utils import uptime_seconds


def handle_status(_params: dict, ctx, _conn) -> dict:
    channels_snapshot = (
        ctx.channels_runtime.snapshot()
        if ctx.channels_runtime is not None
        else {"started": False, "running_count": 0, "channels": {}}
    )
    feishu_status = channels_snapshot.get("channels", {}).get("feishu", {"enabled": False, "running": False})

    return {
        "service": ctx.app_name,
        "uptime_sec": uptime_seconds(ctx.started_at),
        "model": ctx.config.llm.model,
        "provider": ctx.config.llm.provider,
        "sessions": {"total": len(ctx.session_store.all_keys())},
        "feishu": feishu_status,
        "channels": channels_snapshot,
        "gateway": {
            "enabled": ctx.gateway_config.enabled,
            "host": ctx.gateway_config.host,
            "port": ctx.gateway_config.port,
            "auth_enabled": ctx.gateway_config.auth.enabled,
        },
        "subagents": {
            "enabled": ctx.config.subagents.enabled,
            "max_depth": ctx.config.subagents.max_depth,
        },
        "cron": {
            "enabled": ctx.config.cron.enabled,
            "running": bool(ctx.cron_scheduler is not None and ctx.cron_scheduler.snapshot().get("running")),
        },
    }
