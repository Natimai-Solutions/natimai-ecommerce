from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.outbox.models import OutboxEvent
from app.outbox.poller import poll_outbox_once
from app.outbox.registry import outbox_registry


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_registry_publish_creates_pending_event_with_payload() -> None:
    session = AsyncMock()
    session.add = Mock()
    session.flush = AsyncMock()

    event = await outbox_registry.publish(
        session=session,
        event_type="create.product",
        payload={"id": "p-1", "action": "create"},
        delay_seconds=0,
    )

    assert event.type == "create.product"
    assert event.status == "PENDING"
    assert event.payload == {"id": "p-1", "action": "create"}

    session.add.assert_called_once_with(event)
    session.flush.assert_awaited_once()


@pytest.mark.anyio
async def test_registry_publish_parses_uuid_correlation_id() -> None:
    session = AsyncMock()
    session.add = Mock()
    session.flush = AsyncMock()

    correlation_id = str(uuid4())
    event = await outbox_registry.publish(
        session=session,
        event_type="update.product",
        payload={"id": "p-2", "action": "update"},
        correlation_id=correlation_id,
    )

    assert str(event.correlation_id) == correlation_id


@pytest.mark.anyio
async def test_registry_publish_rejects_invalid_correlation_id() -> None:
    session = AsyncMock()
    session.add = Mock()
    session.flush = AsyncMock()

    with pytest.raises(ValueError):
        await outbox_registry.publish(
            session=session,
            event_type="delete.product",
            payload={"id": "p-3", "action": "delete"},
            correlation_id="not-a-uuid",
        )


@pytest.mark.anyio
async def test_poll_outbox_once_marks_done_when_enqueue_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    event = OutboxEvent(type="create.product", payload={"id": "p-1"})
    result = SimpleNamespace(first=Mock(return_value=event))
    session.exec = AsyncMock(return_value=result)

    async def _commit_and_refresh(
        _session: AsyncMock, current: OutboxEvent
    ) -> OutboxEvent:
        return current

    monkeypatch.setattr(
        "app.outbox.poller.commit_and_refresh",
        AsyncMock(side_effect=_commit_and_refresh),
    )
    monkeypatch.setattr(
        "app.outbox.poller.outbox_registry.get_handlers",
        Mock(return_value=[object()]),
    )
    monkeypatch.setattr(
        "app.outbox.poller.enqueue_jobs_for_event",
        AsyncMock(return_value=None),
    )

    processed = await poll_outbox_once(session)

    assert processed is True
    assert event.status == "DONE"
    assert event.attempts == 1


@pytest.mark.anyio
async def test_poll_outbox_once_schedules_retry_when_enqueue_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    event = OutboxEvent(type="create.product", payload={"id": "p-1"})
    result = SimpleNamespace(first=Mock(return_value=event))
    session.exec = AsyncMock(return_value=result)

    async def _commit_and_refresh(
        _session: AsyncMock, current: OutboxEvent
    ) -> OutboxEvent:
        return current

    monkeypatch.setattr(
        "app.outbox.poller.commit_and_refresh",
        AsyncMock(side_effect=_commit_and_refresh),
    )
    # A handler exists for this type (so we reach the enqueue step, which fails).
    monkeypatch.setattr(
        "app.outbox.poller.outbox_registry.get_handlers",
        Mock(return_value=[object()]),
    )
    monkeypatch.setattr(
        "app.outbox.poller.enqueue_jobs_for_event",
        AsyncMock(side_effect=RuntimeError("enqueue failed")),
    )

    before = datetime.now(timezone.utc)
    processed = await poll_outbox_once(session)

    assert processed is True
    assert event.status == "PENDING"
    assert event.attempts == 1
    assert event.last_error is not None
    assert "enqueue failed" in event.last_error
    assert event.next_run_at >= before


@pytest.mark.anyio
async def test_poll_outbox_once_skips_event_without_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An event whose type has no registered handler is marked DONE, not retried
    forever (otherwise it would starve handled events)."""
    session = AsyncMock()
    session.add = Mock()

    event = OutboxEvent(type="update.product", payload={"id": "p-1"})
    result = SimpleNamespace(first=Mock(return_value=event))
    session.exec = AsyncMock(return_value=result)

    async def _commit_and_refresh(
        _session: AsyncMock, current: OutboxEvent
    ) -> OutboxEvent:
        return current

    monkeypatch.setattr(
        "app.outbox.poller.commit_and_refresh",
        AsyncMock(side_effect=_commit_and_refresh),
    )
    monkeypatch.setattr(
        "app.outbox.poller.outbox_registry.get_handlers",
        Mock(return_value=[]),
    )
    enqueue = AsyncMock()
    monkeypatch.setattr("app.outbox.poller.enqueue_jobs_for_event", enqueue)

    processed = await poll_outbox_once(session)

    assert processed is True
    assert event.status == "DONE"
    enqueue.assert_not_awaited()
