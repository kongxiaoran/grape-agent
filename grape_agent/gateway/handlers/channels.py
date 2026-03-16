"""Gateway channel status handlers."""

from __future__ import annotations


def handle_channels_status(_params: dict, ctx, _conn) -> dict:
    if ctx.channels_runtime is None:
        return {
            "started": False,
            "running_count": 0,
            "channels": {},
        }
    return ctx.channels_runtime.snapshot()


async def handle_channels_send(params: dict, ctx, _conn) -> dict:
    if ctx.channels_runtime is None:
        return {"ok": False, "error": "channels runtime is not available"}

    channel = str(params.get("channel", "")).strip()
    target = str(params.get("target", "")).strip()
    content = str(params.get("content", ""))
    options = params.get("options", {})
    if not isinstance(options, dict):
        options = {}

    if not channel:
        return {"ok": False, "error": "missing required param: channel"}
    if not target:
        return {"ok": False, "error": "missing required param: target"}
    if not content:
        return {"ok": False, "error": "missing required param: content"}

    send_result = await ctx.channels_runtime.send(
        channel_id=channel,
        target=target,
        content=content,
        **options,
    )
    return {
        "channel": channel,
        "target": target,
        **send_result,
    }
