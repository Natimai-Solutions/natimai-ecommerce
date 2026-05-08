"""Unit tests for JSON serialization and outbox payload compatibility."""

import datetime
import json
import uuid

from sqlmodel import SQLModel

from app.features.base.crud import CrudBase


class SerializationModel(SQLModel):
    pass


class SerializationSchema(SQLModel):
    pass


def _build_crud() -> CrudBase[
    SerializationModel, SerializationSchema, SerializationSchema
]:
    return CrudBase(
        model=SerializationModel,
        schema_create=SerializationSchema,
        schema_update=SerializationSchema,
    )


def test_datetime_serialization() -> None:
    """Datetime and UUID values must be converted to JSON-safe strings."""
    crud = _build_crud()

    test_data = {
        "name": "test",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "updated_at": datetime.datetime(2025, 9, 18, 14, 30, 0),
        "id": uuid.uuid4(),
        "nested": {
            "user_id": uuid.uuid4(),
            "timestamps": [
                datetime.datetime.now(datetime.timezone.utc),
                datetime.datetime(2025, 1, 1),
            ],
        },
    }

    serialized = crud._serialize_for_json(test_data)

    assert isinstance(serialized["created_at"], str)
    assert isinstance(serialized["updated_at"], str)
    assert isinstance(serialized["id"], str)
    assert isinstance(serialized["nested"]["user_id"], str)
    assert isinstance(serialized["nested"]["timestamps"][0], str)
    assert serialized["name"] == "test"

    # Ensure no non-JSON values remain.
    json.dumps(serialized)


def test_payload_json_compatibility() -> None:
    """Outbox payload returned by CrudBase must be fully JSON serializable."""
    crud = _build_crud()

    class MockRecord:
        id = uuid.uuid4()
        name = "test"
        description = "description"
        created_by_id = uuid.uuid4()

    payload = crud._build_outbox_payload(
        action="create",
        record=MockRecord(),
        user=None,
        data={
            "name": "updated",
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "modified_at": datetime.datetime(2025, 9, 18),
            "owner_id": uuid.uuid4(),
        },
    )

    assert payload["action"] == "create"
    assert "timestamp" in payload
    assert "data" in payload
    assert isinstance(payload["data"]["created_at"], str)
    assert isinstance(payload["data"]["owner_id"], str)

    json_str = json.dumps(payload)
    parsed = json.loads(json_str)
    assert parsed["action"] == "create"
