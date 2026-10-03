"""``/metrics`` in the Prometheus text format, without a dependency (R8 / U3).

* HTTP: requests counted by method, route template and status class, latency
  as a histogram with fixed buckets — recorded by the middleware in
  ``app.main`` for every request of **this process** (one API replica = one
  series set; a scraper labels them by instance).
* Background: depth of the ARQ queue (Redis) and the outbox — events by
  status, age of the oldest pending event — read at scrape time.

Exposed by ``GET /metrics``, protected by ``METRICS_TOKEN`` (bearer) outside
``local``.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC
from typing import Any

#: Latency buckets in seconds (Prometheus convention, ``+Inf`` implied).
LATENCY_BUCKETS: tuple[float, ...] = (0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

#: arq's default queue key (``arq.constants.default_queue_name``).
ARQ_QUEUE_KEY = "arq:queue"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{_escape(str(v))}"' for k, v in labels.items())
    return "{" + inner + "}"


class HttpMetrics:
    """In-process counters and latency histogram of the HTTP requests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self._buckets: dict[tuple[str, str], list[int]] = defaultdict(
            lambda: [0] * (len(LATENCY_BUCKETS) + 1)
        )
        self._sum: dict[tuple[str, str], float] = defaultdict(float)
        self._count: dict[tuple[str, str], int] = defaultdict(int)
        self.started_at = time.time()

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        status_class = f"{status // 100}xx"
        with self._lock:
            self._requests[(method, route, status_class)] += 1
            key = (method, route)
            buckets = self._buckets[key]
            for index, bound in enumerate(LATENCY_BUCKETS):
                if seconds <= bound:
                    buckets[index] += 1
            buckets[-1] += 1  # +Inf
            self._sum[key] += seconds
            self._count[key] += 1

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._buckets.clear()
            self._sum.clear()
            self._count.clear()

    def render(self) -> list[str]:
        lines = [
            "# HELP http_requests_total Requests handled by this process.",
            "# TYPE http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status_class), count in sorted(self._requests.items()):
                labels = {"method": method, "route": route, "status": status_class}
                lines.append(f"http_requests_total{_labels(labels)} {count}")
            lines += [
                "# HELP http_request_duration_seconds Latency of the requests.",
                "# TYPE http_request_duration_seconds histogram",
            ]
            for (method, route), buckets in sorted(self._buckets.items()):
                base = {"method": method, "route": route}
                for index, bound in enumerate(LATENCY_BUCKETS):
                    lines.append(
                        "http_request_duration_seconds_bucket"
                        f"{_labels({**base, 'le': format(bound, 'g')})} {buckets[index]}"
                    )
                lines.append(
                    f"http_request_duration_seconds_bucket{_labels({**base, 'le': '+Inf'})} "
                    f"{buckets[-1]}"
                )
                lines.append(
                    f"http_request_duration_seconds_sum{_labels(base)} "
                    f"{self._sum[(method, route)]:.6f}"
                )
                lines.append(
                    f"http_request_duration_seconds_count{_labels(base)} "
                    f"{self._count[(method, route)]}"
                )
        lines += [
            "# HELP process_start_time_seconds Start time of this process (unix).",
            "# TYPE process_start_time_seconds gauge",
            f"process_start_time_seconds {self.started_at:.0f}",
        ]
        return lines


http_metrics = HttpMetrics()


def gauge_lines(
    name: str, help_text: str, samples: Iterable[tuple[dict[str, str], Any]]
) -> list[str]:
    """``# HELP`` / ``# TYPE gauge`` and one sample line per labels set."""
    lines = [f"# HELP {name} {help_text}", f"# TYPE {name} gauge"]
    for labels, value in samples:
        lines.append(f"{name}{_labels(labels)} {value}")
    return lines


async def background_lines(session: Any) -> list[str]:
    """ARQ queue depth and outbox state, read now."""
    from datetime import datetime

    from sqlalchemy import func
    from sqlmodel import col, select

    from app.core.cache import RedisCache
    from app.outbox.models import OutboxEvent

    lines: list[str] = []
    try:
        async with RedisCache() as redis:
            depth = await redis.zcard(ARQ_QUEUE_KEY)
        lines += gauge_lines(
            "arq_queue_depth", "Jobs waiting in the ARQ queue.", [({}, int(depth))]
        )
        lines += gauge_lines("redis_up", "Redis answered the scrape.", [({}, 1)])
    except Exception:  # noqa: BLE001 - a scrape never raises
        lines += gauge_lines("redis_up", "Redis answered the scrape.", [({}, 0)])

    try:
        rows = (
            await session.exec(
                select(col(OutboxEvent.status), func.count()).group_by(
                    col(OutboxEvent.status)
                )
            )
        ).all()
        counts = {str(status): int(count) for status, count in rows}
        lines += gauge_lines(
            "outbox_events",
            "Outbox events by status.",
            [
                ({"status": s}, counts.get(s, 0))
                for s in ("PENDING", "RUNNING", "DONE", "FAILED")
            ],
        )
        oldest = (
            await session.exec(
                select(func.min(col(OutboxEvent.created_at))).where(
                    col(OutboxEvent.status) == "PENDING"
                )
            )
        ).one()
        age = 0.0
        if oldest is not None:
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=UTC)
            age = max(0.0, (datetime.now(UTC) - oldest).total_seconds())
        lines += gauge_lines(
            "outbox_oldest_pending_seconds",
            "Age of the oldest pending outbox event (0 when none).",
            [({}, f"{age:.0f}")],
        )
        lines += gauge_lines(
            "database_up", "The database answered the scrape.", [({}, 1)]
        )
    except Exception:  # noqa: BLE001 - a scrape never raises
        lines += gauge_lines(
            "database_up", "The database answered the scrape.", [({}, 0)]
        )
    return lines


async def render_metrics(session: Any) -> str:
    """The whole exposition, ``text/plain; version=0.0.4``."""
    lines = http_metrics.render() + await background_lines(session)
    return "\n".join(lines) + "\n"


__all__ = [
    "ARQ_QUEUE_KEY",
    "LATENCY_BUCKETS",
    "HttpMetrics",
    "background_lines",
    "gauge_lines",
    "http_metrics",
    "render_metrics",
]
