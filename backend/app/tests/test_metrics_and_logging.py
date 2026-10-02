"""``/metrics`` and the shared logging configuration (R8 / U3)."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.logging_config import JsonFormatter
from app.core.metrics import HttpMetrics, http_metrics
from app.main import app


def test_http_metrics_render_counters_and_histogram() -> None:
    metrics = HttpMetrics()
    metrics.observe("GET", "/api/v1/product/{product_id}", 200, 0.03)
    metrics.observe("GET", "/api/v1/product/{product_id}", 404, 0.3)
    text = "\n".join(metrics.render())
    assert (
        'http_requests_total{method="GET",route="/api/v1/product/{product_id}",status="2xx"} 1'
        in text
    )
    assert (
        'http_requests_total{method="GET",route="/api/v1/product/{product_id}",status="4xx"} 1'
        in text
    )
    # 0.03 s lands in the 0.05 bucket, 0.3 s only from the 0.5 bucket on.
    assert 'le="0.05"} 1' in text
    assert 'le="0.5"} 2' in text
    assert 'le="+Inf"} 2' in text
    assert "http_request_duration_seconds_count" in text
    assert "process_start_time_seconds" in text


def test_json_formatter_emits_one_object_per_line_with_extras() -> None:
    record = logging.LogRecord(
        "app.test", logging.WARNING, __file__, 1, "Hello %s", ("world",), None
    )
    record.order_id = "abc"
    line = JsonFormatter("api").format(record)
    payload = json.loads(line)
    assert payload["message"] == "Hello world"
    assert payload["level"] == "WARNING"
    assert payload["service"] == "api"
    assert payload["order_id"] == "abc"
    assert payload["time"].endswith("+00:00")


def test_metrics_endpoint_requires_the_token_outside_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert client.get("/metrics").status_code == 404

    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    assert client.get("/metrics").status_code == 401
    assert (
        client.get("/metrics", headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )
    ok = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in ok.text
    # The background gauges come from Redis and the database; without them the
    # scrape still answers and says so.
    assert "outbox_oldest_pending_seconds" in ok.text or "database_up 0" in ok.text
    assert "arq_queue_depth" in ok.text or "redis_up 0" in ok.text


def test_requests_are_measured_by_route_template() -> None:
    client = TestClient(app)
    http_metrics.reset()
    client.get("/api/v1/healthz/liveness")
    client.get("/api/v1/no-such-route-here")
    text = "\n".join(http_metrics.render())
    assert 'route="/api/v1/healthz/liveness",status="2xx"} 1' in text
    assert 'route="unmatched",status="4xx"} 1' in text
