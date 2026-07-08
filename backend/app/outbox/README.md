# Outbox Pattern (Current Implementation)

## Overview

This module implements the outbox pattern used by the backend to publish domain
events inside database transactions, then process them asynchronously through ARQ.

This document describes the current runtime contract in code, including the C7
consumer-side idempotency behavior.

## Directory

```
app/outbox/
├── models.py      # OutboxEvent SQLModel
├── registry.py    # Event publication + handler registry
├── decorators.py  # @outbox_handler, @bulk_outbox_handler
├── loader.py      # Auto-load handlers from app/handlers
├── poller.py      # Poll pending events and enqueue ARQ jobs
├── consumer.py    # Worker entrypoint + consumer idempotency
└── README.md
```

## Event Naming

Event types follow this format:

- `{action}.{model}`

Examples:

- `create.product`
- `update.product`
- `delete.product`

## OutboxEvent Model

`OutboxEvent` is stored in table `outbox_event` with these important fields:

- `id: UUID`
- `type: str`
- `correlation_id: UUID | None`
- `payload: dict[str, Any]` (JSON column)
- `status: "PENDING" | "RUNNING" | "DONE" | "FAILED"`
- `attempts: int`
- `next_run_at: datetime`
- `last_error: str | None`
- `created_at`, `updated_at`

## Publishing Contract

Use `outbox_registry.publish(...)`:

```python
event = await outbox_registry.publish(
    session=session,
    event_type="create.product",
    payload={"id": "...", "action": "create"},
    delay_seconds=0,
    correlation_id="4b6b2e4d-2f0f-4dd0-a6be-54fdcb8d5db6",
)
```

Behavior:

- Persists an `OutboxEvent` in the same DB session/transaction.
- `correlation_id` accepts `str | UUID | None`.
- If `correlation_id` is a string, it is parsed into UUID and raises `ValueError`
  for invalid UUID strings.

## CRUD Integration Contract

`CrudBase` publishes from `create_draft`, `update_draft`, `delete_draft` when
`outbox_events` is configured.

Expected mapping keys:

- `create`
- `update`
- `delete`

Example (current product CRUD):

```python
crud_product = ProductCrud(
    model=Product,
    schema_create=ProductCreate,
    schema_update=ProductUpdate,
    outbox_events={
        "create": "create.product",
        "update": "update.product",
        "delete": "delete.product",
    },
)
```

Notes:

- Legacy hooks (`after_create`/`after_update`/`after_delete`) do not publish.
- The outbox payload is built centrally by `_build_outbox_payload(...)`.

Standard payload shape:

```python
{
    "id": str,
    "model": str,
    "action": str,
    "user_id": str | None,
    "timestamp": str,
    "data": dict,
}
```

For delete events, `data` is minimal/safe:

```python
{
    "id": str,
    "name": str | None,
    "description": str | None,
    "created_by_id": Any,
}
```

## Handler Contract

Handlers are registered with `@outbox_handler(...)` and loaded from
`app/handlers/*.py`.

Current handler call signature used by the worker:

```python
@outbox_handler("create.product")
async def create_notification(session: Any, payload: dict[str, Any]) -> None:
    ...
```

Important:

- Handler functions are called with `(session, payload)`.
- They are not called with expanded payload kwargs.

## Loader Behavior

`load_handlers()` imports all modules in `app/handlers` (except `__init__.py`).
Importing the module triggers decorator registration into `outbox_registry`.

Handlers are loaded at API startup (`app/main.py`) and also before starting the
worker in `app/scripts/entrypoint.sh`.

## Poller to Worker Contract

The poller enqueues one ARQ job per `(event, handler)` using a fixed job ID:

```python
job_id = f"outbox:{event.id}:{handler.__name__}"
```

ARQ function and kwargs:

```python
await arq_pool.enqueue_job(
    "execute_outbox_handler",
    handler_path="module.path:function_name",
    event_id=str(event.id),
    event_type=event.type,
    payload=event.payload,
    _job_id=job_id,
)
```

This keeps the payload contract and idempotency logic centralized in
`app/outbox/consumer.py`.

## Consumer-Side Idempotency (C7)

`execute_outbox_handler` checks Redis key:

```python
outbox:consumer:processed:{event_id}:{handler_path}
```

Behavior:

- If key exists: skip execution.
- If key does not exist: execute handler, then set key with TTL.

TTL constant:

- `OUTBOX_CONSUMER_IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24 * 30` (30 days)

This protects against duplicate deliveries even if the same ARQ payload is
replayed.

## State Transitions and Retries

Current `poll_outbox_once(...)` and batch processing behavior:

- Select due `PENDING` event (`next_run_at <= now`).
- Set `RUNNING`.
- Enqueue handler jobs.
- On enqueue success: set `DONE`, increment `attempts`.
- On enqueue failure: set back to `PENDING`, increment `attempts`, set
  `next_run_at` with exponential backoff, set `last_error`.

Backoff schedule in seconds:

- `[10, 30, 60, 300, 900]`

Important implementation note:

- `MAX_ATTEMPTS` is defined in `poller.py` but automatic transition to `FAILED`
  is not currently enforced in `poll_outbox_once(...)` or
  `process_pending_events(...)`.
- `retry_failed_events(...)` exists for events already marked `FAILED`.

## Operational Commands

From `backend/`:

```bash
# Start ARQ worker
uv run arq app.core.arq_worker.WorkerSettings

# Start poller continuously
uv run python app/scripts/outbox_poller.py --mode continuous --interval 10

# Process one batch
uv run python app/scripts/outbox_poller.py --mode once
```

In containerized runtime, the entrypoint also supports `api`, `worker`, and
`poller` modes.

## Minimal Validation Checklist

After changing outbox behavior, validate at least:

- Handlers are loaded: `outbox_registry.list_event_types()` contains expected keys.
- Poller enqueues `execute_outbox_handler` with expected kwargs.
- Duplicate delivery is skipped by consumer idempotency key.
- CRUD event types match configured `outbox_events` keys (`create/update/delete`).

## Related Tests

Useful test files:

- `app/tests/api/test_outbox_consumer_idempotency.py`
- `app/tests/test_outbox_integration.py`
- `app/tests/validate_outbox.py`
- `app/tests/test_real_outbox.py`
