"""Shared helpers for tool allow/deny policy."""

from __future__ import annotations

from mini_agent.tools.base import Tool


def filter_tools_by_name(tools: list[Tool], deny_names: set[str]) -> tuple[list[Tool], list[str]]:
    """Return filtered tools and removed tool names."""
    if not deny_names:
        return tools, []

    filtered: list[Tool] = []
    removed: list[str] = []
    for tool in tools:
        if tool.name in deny_names:
            removed.append(tool.name)
            continue
        filtered.append(tool)
    return filtered, removed
