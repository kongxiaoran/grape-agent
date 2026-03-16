"""Utility helpers for webterm bridge."""

from __future__ import annotations

import json
import re
from uuid import uuid4


def extract_json_object(text: str) -> dict | None:
    """Best-effort JSON object extraction from model output."""
    content = text.strip()
    if not content:
        return None

    # Direct parse first.
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Extract fenced JSON block.
    fenced = re.search(r"```json\s*([\s\S]*?)```", content, re.IGNORECASE)
    if fenced:
        block = fenced.group(1).strip()
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Extract first object-like block.
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        block = content[start : end + 1]
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def wrap_command(command: str, trace_id: str | None = None) -> tuple[str, str]:
    """Wrap command with begin/end markers for output boundary detection."""
    cleaned = command.strip()
    marker = trace_id or f"tr_{uuid4().hex[:12]}"
    wrapped = (
        f"echo __MA_BEGIN_{marker}__\n"
        f"{cleaned}\n"
        "rc=$?\n"
        f"echo __MA_END_{marker}__$rc\n"
    )
    return marker, wrapped


def classify_command_risk(command: str, denylist: list[str], allowlist: list[str]) -> str:
    """Classify command into low/medium/high risk by simple token matching."""
    lower = command.strip().lower()
    if not lower:
        return "high"

    first = lower.split()[0]
    if first in set(denylist):
        return "high"
    if first in set(allowlist):
        return "low"
    return "medium"
