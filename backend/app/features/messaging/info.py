"""What the customer is told about the messaging: channels and topics, opening
hours and the response time (fixed, or measured on the last 90 days).

The measured time is the 80th percentile of the team's first answer, counted
in **business hours** (a message received on Friday at 16:00 and answered on
Monday at 09:00 took two business hours), rounded up to a step (2 h, 4 h,
8 h, 1 business day, 2 business days). Below 20 conversations, or when it is
longer than the set time, the set time is shown: never promise better than
what is kept. It is computed at most once an hour per process.
"""

from __future__ import annotations

import datetime
import math
import time
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.core.datetimes import as_utc, utcnow
from app.features.messaging.models import CHANNEL_TOPICS, Conversation

MEASURE_WINDOW_DAYS = 90
MEASURE_MIN_SAMPLES = 20
MEASURE_PERCENTILE = 0.8
_CACHE_SECONDS = 3600
_cache: dict[str, Any] = {}


@dataclass(frozen=True)
class Hours:
    start: datetime.time
    end: datetime.time
    days: frozenset[int]  # ISO weekdays, 1 = Monday

    @property
    def per_day(self) -> float:
        start = self.start.hour + self.start.minute / 60
        end = self.end.hour + self.end.minute / 60
        return max(end - start, 0.0)


def _parse_time(value: Any, fallback: str) -> datetime.time:
    for candidate in (str(value or ""), fallback):
        try:
            hours, minutes = candidate.strip().split(":")
            return datetime.time(int(hours), int(minutes))
        except (ValueError, TypeError):
            continue
    return datetime.time(8, 0)


async def opening_hours(session: AsyncSession) -> Hours:
    start = _parse_time(
        await runtime_settings.get("messaging_hours_start", session), "08:00"
    )
    end = _parse_time(
        await runtime_settings.get("messaging_hours_end", session), "17:00"
    )
    raw_days = await runtime_settings.get("messaging_days", session) or []
    days = frozenset(int(d) for d in raw_days if str(d).isdigit() and 1 <= int(d) <= 7)
    return Hours(start=start, end=end, days=days or frozenset({1, 2, 3, 4, 5}))


def business_hours_between(
    start: datetime.datetime, end: datetime.datetime, hours: Hours, tz: ZoneInfo
) -> float:
    """Business hours elapsed between two instants, in the shop's time zone."""
    if end <= start:
        return 0.0
    local_start, local_end = as_utc(start).astimezone(tz), as_utc(end).astimezone(tz)
    total = 0.0
    day = local_start.date()
    while day <= local_end.date():
        if day.isoweekday() in hours.days:
            open_at = datetime.datetime.combine(day, hours.start, tzinfo=tz)
            close_at = datetime.datetime.combine(day, hours.end, tzinfo=tz)
            lo, hi = max(open_at, local_start), min(close_at, local_end)
            if hi > lo:
                total += (hi - lo).total_seconds() / 3600
        day += datetime.timedelta(days=1)
    return total


def step_of(business_hours: float, per_day: float) -> tuple[str, int]:
    """Round up to a step: (unit, value), unit ``hours`` or ``business_days``."""
    for step in (2, 4, 8):
        if business_hours <= step and step < per_day:
            return "hours", step
    days = max(1, math.ceil(business_hours / per_day)) if per_day else 1
    return "business_days", days


async def measured_response(
    session: AsyncSession, hours: Hours, *, now: datetime.datetime | None = None
) -> tuple[str, int] | None:
    now = now or utcnow()
    rows = (
        await session.exec(
            select(Conversation.created_at, Conversation.first_staff_reply_at).where(
                col(Conversation.first_staff_reply_at).is_not(None),
                col(Conversation.created_at)
                >= now - datetime.timedelta(days=MEASURE_WINDOW_DAYS),
            )
        )
    ).all()
    if len(rows) < MEASURE_MIN_SAMPLES:
        return None
    tz = ZoneInfo(settings.SHOP_TIMEZONE)
    durations = sorted(
        business_hours_between(created, replied, hours, tz)
        for created, replied in rows
        if created is not None and replied is not None
    )
    if not durations:
        return None
    index = min(len(durations) - 1, math.ceil(MEASURE_PERCENTILE * len(durations)) - 1)
    return step_of(durations[index], hours.per_day)


async def response_time(session: AsyncSession, hours: Hours) -> dict[str, Any]:
    """The response time to show: ``{"unit": "hours"|"business_days", "value": n,
    "measured": bool}``."""
    fixed = int(
        await runtime_settings.get("messaging_response_time_hours", session) or 24
    )
    shown: dict[str, Any] = {"unit": "hours", "value": fixed, "measured": False}
    mode = await runtime_settings.get("messaging_response_time_mode", session)
    if mode != "measured":
        return shown
    cached = _cache.get("measured")
    if cached is None or time.monotonic() - cached[0] > _CACHE_SECONDS:
        cached = (time.monotonic(), await measured_response(session, hours))
        _cache["measured"] = cached
    measured = cached[1]
    if measured is None:
        return shown
    unit, value = measured
    wall_hours = value if unit == "hours" else value * 24
    if wall_hours > fixed:
        return shown
    return {"unit": unit, "value": value, "measured": True}


async def public_info(session: AsyncSession) -> dict[str, Any]:
    hours = await opening_hours(session)
    contact = str(await runtime_settings.get("email_contact", session) or "").strip()
    return {
        "channels": [
            {"channel": channel, "topics": list(topics)}
            for channel, topics in CHANNEL_TOPICS.items()
        ],
        "hours_start": hours.start.strftime("%H:%M"),
        "hours_end": hours.end.strftime("%H:%M"),
        "days": sorted(hours.days),
        "timezone": settings.SHOP_TIMEZONE,
        "response_time": await response_time(session, hours),
        "contact_email": contact or None,
    }


def reset_cache() -> None:
    _cache.clear()


__all__ = [
    "Hours",
    "business_hours_between",
    "measured_response",
    "opening_hours",
    "public_info",
    "reset_cache",
    "response_time",
    "step_of",
]
