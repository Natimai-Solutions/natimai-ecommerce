"""Unit tests for standardized outbox payload structure."""

import datetime
import json
import uuid

from sqlmodel import Field, SQLModel

from app.features.base.crud import CrudBase


class PayloadTestModel(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str | None = None
    description: str | None = None
    created_by_id: uuid.UUID | None = None


class PayloadTestSchema(SQLModel):
    name: str | None = None


def _build_crud() -> CrudBase[PayloadTestModel, PayloadTestSchema, PayloadTestSchema]:
    return CrudBase(
        model=PayloadTestModel,
        schema_create=PayloadTestSchema,
        schema_update=PayloadTestSchema,
    )


def test_payload_structure_create_update_is_consistent() -> None:
    """Create/update payloads expose stable keys and JSON-compatible values."""
    crud = _build_crud()
    record = PayloadTestModel(name="demo")

    create_data = {
        "when": datetime.datetime(2026, 5, 7, 9, 30, 0, tzinfo=datetime.UTC),
        "owner_id": uuid.uuid4(),
    }
    create_payload = crud._build_outbox_payload(
        action="create",
        record=record,
        data=create_data,
    )

    assert create_payload["id"] == str(record.id)
    assert create_payload["model"] == "PayloadTestModel"
    assert create_payload["action"] == "create"
    assert create_payload["user_id"] is None
    assert "timestamp" in create_payload
    assert isinstance(create_payload["data"]["when"], str)
    assert isinstance(create_payload["data"]["owner_id"], str)

    update_data = {
        "name": "demo-updated",
        "updated_at": datetime.datetime.now(datetime.UTC),
    }
    update_payload = crud._build_outbox_payload(
        action="update",
        record=record,
        data=update_data,
    )

    assert update_payload["action"] == "update"
    assert update_payload["data"]["name"] == "demo-updated"
    assert isinstance(update_payload["data"]["updated_at"], str)


def test_payload_structure_delete_is_json_serializable() -> None:
    """Delete payload keeps a minimal dict and can be JSON serialized."""
    crud = _build_crud()
    record = PayloadTestModel(name="demo", description="sample")

    payload = crud._build_outbox_payload(action="delete", record=record)

    assert payload["action"] == "delete"
    assert "data" in payload
    assert payload["data"]["id"] == str(record.id)
    assert payload["data"]["name"] == "demo"
    assert payload["data"]["description"] == "sample"

    # Must not raise TypeError for non-JSON types.
    json.dumps(payload)
