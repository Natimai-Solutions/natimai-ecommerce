from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.outbox.consumer import build_outbox_consumer_key
from app.outbox.loader import load_handlers
from app.outbox.models import OutboxEvent
from app.outbox.poller import enqueue_jobs_for_event
from app.outbox.registry import outbox_registry


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_consumer_key_builder_is_deterministic() -> None:
    key_1 = build_outbox_consumer_key(
        "evt-1", "app.handlers.product:create_notification"
    )
    key_2 = build_outbox_consumer_key(
        "evt-1", "app.handlers.product:create_notification"
    )

    assert key_1 == key_2
    assert (
        key_1
        == "outbox:consumer:processed:evt-1:app.handlers.product:create_notification"
    )


def test_load_handlers_registers_product_create_handler() -> None:
    outbox_registry.clear_handlers("create.product")
    load_handlers()

    handlers = outbox_registry.get_handlers("create.product")
    assert handlers


@pytest.mark.anyio
async def test_enqueue_builds_expected_outbox_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_handler(_session: object, _payload: dict[str, object]) -> None:
        return None

    event = OutboxEvent(type="create.product", payload={"id": "p-1"})

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
    kwargs = enqueue_job_mock.await_args.kwargs
    assert kwargs["_job_id"] == f"outbox:{event.id}:{fake_handler.__name__}"
    assert kwargs["event_id"] == str(event.id)
    assert kwargs["event_type"] == "create.product"
