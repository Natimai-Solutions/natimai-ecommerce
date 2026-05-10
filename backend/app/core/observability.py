from __future__ import annotations

import json
import logging
import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Lock
from typing import Any
from uuid import UUID


def _json_default(value: Any) -> Any:
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
    happened_at: datetime
    success: bool
    duration_ms: int
    error_code: str | None


class CheckoutMetricsStore:
    def __init__(self, max_events: int = 2000) -> None:
        self._events: deque[CheckoutMetricEvent] = deque(maxlen=max_events)
        self._lock = Lock()

    def record(
        self,
        *,
        success: bool,
        duration_ms: int,
        error_code: str | None,
    ) -> None:
        event = CheckoutMetricEvent(
            happened_at=datetime.now(timezone.utc),
            success=success,
            duration_ms=max(duration_ms, 0),
            error_code=error_code,
        )
        with self._lock:
            self._events.append(event)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def snapshot(
        self,
        *,
        window_minutes: int = 60,
        failure_rate_alert_threshold: float = 0.2,
        min_attempts_for_alert: int = 3,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=window_minutes)

        with self._lock:
            window_events = [
                event for event in self._events if event.happened_at >= window_start
            ]

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


_checkout_metrics_store = CheckoutMetricsStore()


def observe_checkout_result(
    *,
    success: bool,
    duration_ms: int,
    error_code: str | None = None,
) -> None:
    _checkout_metrics_store.record(
        success=success,
        duration_ms=duration_ms,
        error_code=error_code,
    )


def get_checkout_metrics_snapshot(
    *,
    window_minutes: int = 60,
) -> dict[str, Any]:
    return _checkout_metrics_store.snapshot(window_minutes=window_minutes)


def reset_checkout_metrics_for_tests() -> None:
    _checkout_metrics_store.reset()
