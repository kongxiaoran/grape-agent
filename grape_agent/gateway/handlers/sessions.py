"""Gateway sessions handlers."""

from __future__ import annotations


def handle_sessions_list(params: dict, ctx, _conn) -> dict:
    channel_filter = params.get("channel")
    rows: list[dict] = []
    for session in ctx.session_store.all_sessions():
        if channel_filter and session.channel != channel_filter:
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

    return {"total": len(rows), "items": rows}


async def handle_sessions_spawn(params: dict, ctx, _conn) -> dict:
    orchestrator = ctx.subagent_orchestrator
    if orchestrator is None:
        return {"ok": False, "error": "subagent orchestrator is not available"}

    parent_session_key = str(params.get("parent_session_key", "")).strip()
    task = str(params.get("task", "")).strip()
    if not parent_session_key:
        return {"ok": False, "error": "missing required param: parent_session_key"}
    if not task:
        return {"ok": False, "error": "missing required param: task"}

    agent_id = params.get("agent_id")
    mode = str(params.get("mode", "run"))
    wait = bool(params.get("wait", False))
    return await orchestrator.spawn(
        parent_session_key=parent_session_key,
        task=task,
        agent_id=(str(agent_id).strip() if isinstance(agent_id, str) else None),
        mode=mode,
        wait=wait,
    )


def handle_sessions_history(params: dict, ctx, _conn) -> dict:
    orchestrator = ctx.subagent_orchestrator
    if orchestrator is None:
        return {"ok": False, "error": "subagent orchestrator is not available"}

    session_key = str(params.get("session_key", "")).strip()
    if not session_key:
        return {"ok": False, "error": "missing required param: session_key"}
    limit = int(params.get("limit", 50))
    return orchestrator.history(session_key=session_key, limit=limit)


async def handle_sessions_send(params: dict, ctx, _conn) -> dict:
    orchestrator = ctx.subagent_orchestrator
    if orchestrator is None:
        return {"ok": False, "error": "subagent orchestrator is not available"}

    session_key = str(params.get("session_key", "")).strip()
    message = str(params.get("message", "")).strip()
    if not session_key:
        return {"ok": False, "error": "missing required param: session_key"}
    if not message:
        return {"ok": False, "error": "missing required param: message"}
    wait = bool(params.get("wait", False))
    return await orchestrator.send(session_key=session_key, message=message, wait=wait)


def handle_sessions_run_get(params: dict, ctx, _conn) -> dict:
    orchestrator = ctx.subagent_orchestrator
    if orchestrator is None:
        return {"ok": False, "error": "subagent orchestrator is not available"}

    run_id = str(params.get("run_id", "")).strip()
    if not run_id:
        return {"ok": False, "error": "missing required param: run_id"}
    run = orchestrator.get_run(run_id)
    if run is None:
        return {"ok": False, "error": f"run not found: {run_id}"}
    return {"ok": True, "run": run}


def handle_sessions_runs_list(params: dict, ctx, _conn) -> dict:
    orchestrator = ctx.subagent_orchestrator
    if orchestrator is None:
        return {"ok": False, "error": "subagent orchestrator is not available"}

    session_key = params.get("session_key")
    limit = int(params.get("limit", 20))
    items = orchestrator.list_runs(
        session_key=(str(session_key).strip() if isinstance(session_key, str) and session_key.strip() else None),
        limit=limit,
    )
    return {"ok": True, "total": len(items), "items": items}
