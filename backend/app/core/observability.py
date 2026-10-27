from __future__ import annotations

import json
import logging
import math
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Lock
from typing import Any
from uuid import UUID


def _json_default(value: Any) -> Any:
    """Execute json default."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def log_structured_event(
    logger: logging.Logger,
    *,
    level: str,
    event: str,
    **fields: Any,
) -> None:
    """Execute log structured event."""
    payload = {
        "event": event,
        **fields,
    }
    message = json.dumps(
        payload, default=_json_default, ensure_ascii=True, sort_keys=True
    )
    log_method = getattr(logger, level, logger.info)
    log_method(message)


@dataclass(frozen=True)
class CheckoutMetricEvent:
    """Represents checkout metric event."""

    happened_at: datetime
    success: bool
    duration_ms: int
    error_code: str | None

    def to_json(self) -> str:
        return json.dumps(
            {
                "at": self.happened_at.isoformat(),
                "ok": self.success,
                "ms": self.duration_ms,
                "code": self.error_code,
            }
        )

    @classmethod
    def from_json(cls, raw: bytes | str) -> CheckoutMetricEvent:
        data = json.loads(raw)
        return cls(
            happened_at=datetime.fromisoformat(data["at"]),
            success=bool(data["ok"]),
            duration_ms=int(data["ms"]),
            error_code=data.get("code"),
        )


def summarize_checkout_events(
    events: list[CheckoutMetricEvent],
    *,
    window_minutes: int = 60,
    failure_rate_alert_threshold: float = 0.2,
    min_attempts_for_alert: int = 3,
) -> dict[str, Any]:
    """Attempts, failures, durations and alert over the last minutes."""
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=window_minutes)
    window_events = [event for event in events if event.happened_at >= window_start]
    window_events.sort(key=lambda event: event.happened_at)

    attempts = len(window_events)
    successes = sum(1 for event in window_events if event.success)
    failures = attempts - successes

    durations = [event.duration_ms for event in window_events]
    avg_duration_ms = (sum(durations) / len(durations)) if durations else 0.0

    p95_duration_ms: int | None = None
    if durations:
        ordered_durations = sorted(durations)
        p95_index = max(0, math.ceil(0.95 * len(ordered_durations)) - 1)
        p95_duration_ms = ordered_durations[p95_index]

    failure_rate = (failures / attempts) if attempts else 0.0
    alert_checkout_errors = (
        attempts >= min_attempts_for_alert
        and failure_rate >= failure_rate_alert_threshold
    )

    recent_failure_codes = [
        event.error_code
        for event in window_events
        if (not event.success) and event.error_code
    ]

    return {
        "window_minutes": window_minutes,
        "attempts": attempts,
        "successes": successes,
        "failures": failures,
        "failure_rate": round(failure_rate, 4),
        "avg_duration_ms": round(avg_duration_ms, 2),
        "p95_duration_ms": p95_duration_ms,
        "alert_checkout_errors": alert_checkout_errors,
        "recent_failure_codes": recent_failure_codes[-5:],
    }


class CheckoutMetricsStore:
    """In-process fallback of the checkout metrics, when Redis is down."""

    def __init__(self, max_events: int = 2000) -> None:
        """Initialize the checkout metrics store instance."""
        self._events: deque[CheckoutMetricEvent] = deque(maxlen=max_events)
        self._lock = Lock()

    def record(self, event: CheckoutMetricEvent) -> None:
        with self._lock:
            self._events.append(event)

    def events(self) -> list[CheckoutMetricEvent]:
        with self._lock:
            return list(self._events)

    def reset(self) -> None:
        """Execute reset."""
        with self._lock:
            self._events.clear()


_checkout_metrics_store = CheckoutMetricsStore()

#: Shared by every replica of the API: the in-process store only saw the
#: checkouts of the replica that answered the dashboard.
CHECKOUT_EVENTS_KEY = "metrics:checkout:events"
_CHECKOUT_EVENTS_MAX = 2000


async def observe_checkout_result(
    *,
    success: bool,
    duration_ms: int,
    error_code: str | None = None,
) -> None:
    """Record one checkout attempt (best effort: metrics never fail a checkout)."""
    event = CheckoutMetricEvent(
        happened_at=datetime.now(UTC),
        success=success,
        duration_ms=max(duration_ms, 0),
        error_code=error_code,
    )
    from app.core.rate_limit import shared_redis

    try:
        async with shared_redis().pipeline(transaction=True) as pipe:
            pipe.lpush(CHECKOUT_EVENTS_KEY, event.to_json())
            pipe.ltrim(CHECKOUT_EVENTS_KEY, 0, _CHECKOUT_EVENTS_MAX - 1)
            pipe.expire(CHECKOUT_EVENTS_KEY, 86400)
            await pipe.execute()
    except Exception:  # noqa: BLE001 — fall back to this process
        _checkout_metrics_store.record(event)


async def get_checkout_metrics_snapshot(
    *,
    window_minutes: int = 60,
) -> dict[str, Any]:
    """Checkout metrics of every replica (this process only if Redis is down)."""
    from app.core.rate_limit import shared_redis

    try:
        raw: list[bytes] = await shared_redis().lrange(  # type: ignore[misc]
            CHECKOUT_EVENTS_KEY, 0, -1
        )
        events = [CheckoutMetricEvent.from_json(item) for item in raw]
    except Exception:  # noqa: BLE001
        events = []
    events.extend(_checkout_metrics_store.events())
    return summarize_checkout_events(events, window_minutes=window_minutes)


async def reset_checkout_metrics_for_tests() -> None:
    """Execute reset checkout metrics for tests."""
    from app.core.rate_limit import shared_redis

    _checkout_metrics_store.reset()
    try:
        await shared_redis().delete(CHECKOUT_EVENTS_KEY)
    except Exception:  # noqa: BLE001
        pass
