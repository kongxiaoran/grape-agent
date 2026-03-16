"""Cron models and schedule parser."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ScheduleSpec(BaseModel):
    """Parsed schedule model."""

    kind: Literal["interval", "cron"]
    interval_seconds: int | None = None
    minute: set[int] | None = None
    hour: set[int] | None = None
    day_of_month: set[int] | None = None
    month: set[int] | None = None
    day_of_week: set[int] | None = None


def _parse_interval_schedule(schedule: str) -> int | None:
    text = schedule.strip().lower()
    match = re.fullmatch(r"(?:@every|every)\s+(\d+)\s*([smh])", text)
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)
    if value <= 0:
        raise ValueError("interval must be > 0")
    if unit == "s":
        return value
    if unit == "m":
        return value * 60
    return value * 3600


def _normalize_dow(value: int) -> int:
    if value == 7:
        return 0
    return value


def _expand_part(part: str, minimum: int, maximum: int, is_dow: bool = False) -> set[int]:
    base = part.strip()
    if not base:
        raise ValueError("empty schedule part")

    step = 1
    if "/" in base:
        left, right = base.split("/", 1)
        if not right.isdigit():
            raise ValueError(f"invalid step in schedule part: {part}")
        step = int(right)
        if step <= 0:
            raise ValueError(f"invalid step in schedule part: {part}")
        base = left

    if base == "*":
        start, end = minimum, maximum
    elif "-" in base:
        left, right = base.split("-", 1)
        if not left.isdigit() or not right.isdigit():
            raise ValueError(f"invalid range in schedule part: {part}")
        start, end = int(left), int(right)
    else:
        if not base.isdigit():
            raise ValueError(f"invalid value in schedule part: {part}")
        start = int(base)
        end = int(base)

    if is_dow:
        start = _normalize_dow(start)
        end = _normalize_dow(end)
        # cron DOW ranges that include 7 are normalized to 0 (Sunday).
        if start == 0 and end == 0 and base not in {"0", "7"} and "-" in part:
            # Fallback for unsupported wrapped ranges.
            raise ValueError(f"unsupported wrapped day_of_week range: {part}")

    if start < minimum or end > maximum or start > end:
        raise ValueError(f"schedule part out of range: {part}")

    values = set(range(start, end + 1, step))
    if is_dow:
        values = {_normalize_dow(v) for v in values}
    return values


def _parse_field(field: str, minimum: int, maximum: int, is_dow: bool = False) -> set[int] | None:
    token = field.strip()
    if token == "*":
        return None
    parts = token.split(",")
    values: set[int] = set()
    for part in parts:
        values.update(_expand_part(part, minimum, maximum, is_dow=is_dow))
    return values


def parse_schedule(schedule: str) -> ScheduleSpec:
    interval = _parse_interval_schedule(schedule)
    if interval is not None:
        return ScheduleSpec(kind="interval", interval_seconds=interval)

    fields = schedule.strip().split()
    if len(fields) != 5:
        raise ValueError("schedule must be '@every <Ns|Nm|Nh>' or 5-field cron expression")

    minute, hour, dom, month, dow = fields
    return ScheduleSpec(
        kind="cron",
        minute=_parse_field(minute, 0, 59),
        hour=_parse_field(hour, 0, 23),
        day_of_month=_parse_field(dom, 1, 31),
        month=_parse_field(month, 1, 12),
        day_of_week=_parse_field(dow, 0, 7, is_dow=True),
    )


def _matches(spec: ScheduleSpec, current: datetime) -> bool:
    if spec.minute is not None and current.minute not in spec.minute:
        return False
    if spec.hour is not None and current.hour not in spec.hour:
        return False
    if spec.day_of_month is not None and current.day not in spec.day_of_month:
        return False
    if spec.month is not None and current.month not in spec.month:
        return False
    cron_dow = (current.weekday() + 1) % 7  # Monday=1 ... Sunday=0
    if spec.day_of_week is not None and cron_dow not in spec.day_of_week:
        return False
    return True


def compute_next_run_at(schedule: str, after: datetime) -> datetime:
    spec = parse_schedule(schedule)
    now = after.astimezone(timezone.utc)
    if spec.kind == "interval":
        seconds = spec.interval_seconds or 60
        return now + timedelta(seconds=seconds)

    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        if _matches(spec, candidate):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError(f"cannot find next run time for schedule: {schedule}")


class CronJob(BaseModel):
    """Persistent cron job."""

    id: str
    schedule: str
    agent_id: str = "main"
    task: str
    session_target: Literal["isolated", "sticky"] = "isolated"
    channel_target: dict[str, Any] | None = None
    enabled: bool = True
    timeout_sec: int | None = None
    next_run_at: str | None = None
    last_run_at: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("job id cannot be empty")
        return value.strip()

    @field_validator("task")
    @classmethod
    def _validate_task(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("job task cannot be empty")
        return value.strip()

    @field_validator("schedule")
    @classmethod
    def _validate_schedule(cls, value: str) -> str:
        parse_schedule(value)
        return value.strip()


class CronRun(BaseModel):
    """One cron execution record."""

    run_id: str
    job_id: str
    status: Literal["running", "completed", "failed", "timeout"]
    scheduled_at: str
    started_at: str = Field(default_factory=utc_now_iso)
    finished_at: str | None = None
    session_key: str | None = None
    result_preview: str | None = None
    error: str | None = None
