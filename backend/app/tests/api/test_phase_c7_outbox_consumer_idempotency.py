from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlmodel import Field, SQLModel

from app.features.base.crud import CrudBase
from app.outbox.consumer import (
    OUTBOX_CONSUMER_IDEMPOTENCY_TTL_SECONDS,
    execute_outbox_handler,
)
from app.outbox.models import OutboxEvent
from app.outbox.poller import enqueue_jobs_for_event


class _C7TestModel(SQLModel):
    id: UUID = Field(default_factory=uuid4)
    name: str | None = None


class _C7TestSchema(SQLModel):
    name: str | None = None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_create_draft_uses_configured_outbox_event_type_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crud = CrudBase[_C7TestModel, _C7TestSchema, _C7TestSchema](
        model=_C7TestModel,
        schema_create=_C7TestSchema,
        schema_update=_C7TestSchema,
        outbox_events={"create": "create.stock_movement"},
    )

    session = AsyncMock()
    session.add = Mock()
    session.flush = AsyncMock()

    publish_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr("app.features.base.crud.outbox_registry.publish", publish_mock)

    record = await crud.create_draft(
        session=session,
        data=_C7TestSchema(name="demo"),
        user=None,
    )

    assert publish_mock.await_count == 1
    assert publish_mock.await_args is not None
    publish_args = publish_mock.await_args.args
    assert publish_args[1] == "create.stock_movement"
    assert publish_mock.await_args.kwargs.get("correlation_id") == record.id


@pytest.mark.anyio
async def test_update_draft_propagates_record_id_as_correlation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crud = CrudBase[_C7TestModel, _C7TestSchema, _C7TestSchema](
        model=_C7TestModel,
        schema_create=_C7TestSchema,
        schema_update=_C7TestSchema,
        outbox_events={"update": "update.stock_movement"},
    )

    session = AsyncMock()
    record = _C7TestModel(name="before")

    publish_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr("app.features.base.crud.outbox_registry.publish", publish_mock)

    await crud.update_draft(
        session=session,
        id=record.id,
        data=_C7TestSchema(name="after"),
        user=None,
        record=record,
    )

    assert publish_mock.await_count == 1
    assert publish_mock.await_args is not None
    assert publish_mock.await_args.args[1] == "update.stock_movement"
    assert publish_mock.await_args.kwargs.get("correlation_id") == record.id


@pytest.mark.anyio
async def test_delete_draft_propagates_record_id_as_correlation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crud = CrudBase[_C7TestModel, _C7TestSchema, _C7TestSchema](
        model=_C7TestModel,
        schema_create=_C7TestSchema,
        schema_update=_C7TestSchema,
        outbox_events={"delete": "delete.stock_movement"},
    )

    session = AsyncMock()
    session.delete = AsyncMock()
    record = _C7TestModel(name="doomed")

    publish_mock = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr("app.features.base.crud.outbox_registry.publish", publish_mock)

    await crud.delete_draft(
        session=session,
        id=record.id,
        record=record,
        user=None,
    )

    assert publish_mock.await_count == 1
    assert publish_mock.await_args is not None
    assert publish_mock.await_args.args[1] == "delete.stock_movement"
    assert publish_mock.await_args.kwargs.get("correlation_id") == record.id


@pytest.mark.anyio
async def test_enqueue_jobs_for_event_uses_worker_entrypoint_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_handler(_session: Any, _payload: dict[str, Any]) -> None:
        return None

    event = cast(
        OutboxEvent,
        SimpleNamespace(
            id=uuid4(),
            type="create.product",
            payload={"id": "p-1", "action": "create"},
        ),
    )

    enqueue_job_mock = AsyncMock(return_value=SimpleNamespace(job_id="job-1"))
    arq_pool = SimpleNamespace(enqueue_job=enqueue_job_mock)

    monkeypatch.setattr(
        "app.outbox.poller.get_arq_pool",
        AsyncMock(return_value=arq_pool),
    )
    monkeypatch.setattr(
        "app.outbox.poller.outbox_registry.get_handlers",
        Mock(return_value=[fake_handler]),
    )

    await enqueue_jobs_for_event(event)

    assert enqueue_job_mock.await_args is not None
    call_args = enqueue_job_mock.await_args.args
    call_kwargs = enqueue_job_mock.await_args.kwargs

    assert call_args[0] == "execute_outbox_handler"
    assert (
        call_kwargs["handler_path"]
        == f"{fake_handler.__module__}:{fake_handler.__name__}"
    )
    assert call_kwargs["event_id"] == str(event.id)
    assert call_kwargs["event_type"] == event.type
    assert call_kwargs["payload"] == event.payload
    assert call_kwargs["_job_id"] == f"outbox:{event.id}:{fake_handler.__name__}"


@pytest.mark.anyio
async def test_execute_outbox_handler_skips_already_processed_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = SimpleNamespace(
        get=AsyncMock(return_value="1"),
        set=AsyncMock(return_value=True),
    )
    ctx = {"redis": redis}

    import_module_mock = Mock(
        side_effect=AssertionError("handler import should be skipped")
    )
    monkeypatch.setattr(
        "app.outbox.consumer.importlib.import_module", import_module_mock
    )

    await execute_outbox_handler(
        ctx,
        handler_path="app.handlers.product:create_notification",
        event_id="evt-1",
        event_type="create.product",
        payload={"id": "p-1"},
    )

    redis.get.assert_awaited_once_with(
        "outbox:consumer:processed:evt-1:app.handlers.product:create_notification"
    )
    redis.set.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_outbox_handler_sets_idempotency_key_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler_mock = AsyncMock(return_value=None)
    fake_module = SimpleNamespace(test_handler=handler_mock)

    monkeypatch.setattr(
        "app.outbox.consumer.importlib.import_module",
        Mock(return_value=fake_module),
    )

    class _FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(
            self,
            _exc_type: object,
            _exc: object,
            _tb: object,
        ) -> None:
            return None

    monkeypatch.setattr(
        "app.outbox.consumer.AsyncSession",
        Mock(return_value=_FakeSessionContext()),
    )

    redis = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(return_value=True),
    )
    ctx = {"redis": redis}

    payload = {"id": "p-1", "action": "create"}
    await execute_outbox_handler(
        ctx,
        handler_path="app.handlers.any:test_handler",
        event_id="evt-2",
        event_type="create.product",
        payload=payload,
    )

    assert handler_mock.await_args is not None
    handler_args = handler_mock.await_args.args
    assert handler_args[1] == payload

    redis.set.assert_awaited_once_with(
        "outbox:consumer:processed:evt-2:app.handlers.any:test_handler",
        "1",
        ex=OUTBOX_CONSUMER_IDEMPOTENCY_TTL_SECONDS,
    )


@pytest.mark.anyio
async def test_execute_outbox_handler_does_not_set_key_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler_mock = AsyncMock(side_effect=RuntimeError("handler failed"))
    fake_module = SimpleNamespace(test_handler=handler_mock)

    monkeypatch.setattr(
        "app.outbox.consumer.importlib.import_module",
        Mock(return_value=fake_module),
    )

    class _FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(
            self,
            _exc_type: object,
            _exc: object,
            _tb: object,
        ) -> None:
            return None

    monkeypatch.setattr(
        "app.outbox.consumer.AsyncSession",
        Mock(return_value=_FakeSessionContext()),
    )

    redis = SimpleNamespace(
        get=AsyncMock(return_value=None),
        set=AsyncMock(return_value=True),
    )
    ctx = {"redis": redis}

    with pytest.raises(RuntimeError, match="handler failed"):
        await execute_outbox_handler(
            ctx,
            handler_path="app.handlers.any:test_handler",
            event_id="evt-3",
            event_type="create.product",
            payload={"id": "p-1"},
        )

    redis.set.assert_not_awaited()
