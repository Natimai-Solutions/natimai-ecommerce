from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.routes.utils as utils_routes
from app.api.deps import get_current_active_superuser
from app.core.db import get_db
from app.core.observability import (
    get_checkout_metrics_snapshot,
    log_structured_event,
    observe_checkout_result,
    reset_checkout_metrics_for_tests,
)
from app.main import app


@pytest.fixture(autouse=True)
def reset_checkout_metrics() -> Generator[None, None, None]:
    reset_checkout_metrics_for_tests()
    yield
    reset_checkout_metrics_for_tests()


@pytest.fixture(autouse=True)
def override_db_dependency() -> Generator[None, None, None]:
    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield SimpleNamespace()

    # The dashboard is superuser-only since the gating pass.
    async def _override_superuser() -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), is_superuser=True, is_active=True)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_active_superuser] = _override_superuser
    yield
    app.dependency_overrides.clear()


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_checkout_metrics_alert_triggers_with_high_failure_rate() -> None:
    observe_checkout_result(success=False, duration_ms=120, error_code="http_error")
    observe_checkout_result(success=False, duration_ms=80, error_code="internal_error")
    observe_checkout_result(success=True, duration_ms=60, error_code=None)

    snapshot = get_checkout_metrics_snapshot(window_minutes=60)

    assert snapshot["attempts"] == 3
    assert snapshot["failures"] == 2
    assert snapshot["failure_rate"] > 0.2
    assert snapshot["alert_checkout_errors"] is True
    assert snapshot["p95_duration_ms"] is not None


def test_log_structured_event_emits_json_message() -> None:
    logger_name = f"e2-test-{uuid.uuid4()}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    capture_handler = _CaptureHandler()
    logger.handlers.clear()
    logger.addHandler(capture_handler)

    now = datetime.now(timezone.utc)
    log_structured_event(
        logger,
        level="info",
        event="checkout_completed",
        order_id=uuid.uuid4(),
        amount=Decimal("12.50"),
        happened_at=now,
    )

    assert capture_handler.messages
    payload = json.loads(capture_handler.messages[-1])

    assert payload["event"] == "checkout_completed"
    assert payload["amount"] == "12.50"
    assert payload["happened_at"] == now.isoformat()


def test_observability_dashboard_endpoint_returns_expected_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_commerce_metrics(
        _session: object,
        *,
        now: datetime,
    ) -> utils_routes.CommerceObservabilityMetrics:
        _ = now
        return utils_routes.CommerceObservabilityMetrics(
            orders_total=12,
            orders_last_24h=4,
            payments_total=11,
            payments_last_24h=3,
        )

    async def _fake_outbox_metrics(
        _session: object,
        *,
        now: datetime,
    ) -> utils_routes.OutboxObservabilityMetrics:
        _ = now
        return utils_routes.OutboxObservabilityMetrics(
            pending=1,
            running=0,
            done=10,
            failed=2,
            stale_pending=1,
            oldest_pending_age_minutes=21.5,
        )

    monkeypatch.setattr(
        "app.api.routes.utils._collect_commerce_metrics",
        _fake_commerce_metrics,
    )
    monkeypatch.setattr(
        "app.api.routes.utils._collect_outbox_metrics",
        _fake_outbox_metrics,
    )
    monkeypatch.setattr(
        "app.api.routes.utils.get_checkout_metrics_snapshot",
        lambda window_minutes=60: {
            "window_minutes": window_minutes,
            "attempts": 5,
            "successes": 3,
            "failures": 2,
            "failure_rate": 0.4,
            "avg_duration_ms": 95.2,
            "p95_duration_ms": 140,
            "alert_checkout_errors": True,
            "recent_failure_codes": ["http_error", "internal_error"],
        },
    )

    response = client.get("/api/v1/utils/observability/dashboard")

    assert response.status_code == 200
    payload = response.json()

    assert payload["commerce"]["orders_total"] == 12
    assert payload["outbox_jobs"]["failed"] == 2
    assert payload["checkout"]["alert_checkout_errors"] is True
    assert payload["checkout"]["recent_failure_codes"] == [
        "http_error",
        "internal_error",
    ]
