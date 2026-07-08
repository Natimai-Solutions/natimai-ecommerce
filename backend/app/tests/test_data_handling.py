"""Unit tests for CRUD data extraction and outbox payload helpers."""

from typing import cast

from sqlmodel import Field, SQLModel

from app.features.base.crud import CrudBase


class DataModel(SQLModel, table=True):
    __tablename__ = "data_model_test"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    value: int


class DataCreateSchema(SQLModel):
    name: str
    value: int


class DataUpdateSchema(SQLModel):
    name: str | None = None
    value: int | None = None


def _build_crud() -> CrudBase[DataModel, DataCreateSchema, DataUpdateSchema]:
    return CrudBase(
        model=DataModel,
        schema_create=DataCreateSchema,
        schema_update=DataUpdateSchema,
    )


def test_data_extraction() -> None:
    """_extract_data_dict should support SQLModel instances and plain dicts."""
    crud = _build_crud()

    schema_obj = DataCreateSchema(name="test", value=42)
    schema_result = crud._extract_data_dict(schema_obj)
    assert isinstance(schema_result, dict)
    assert schema_result["name"] == "test"
    assert schema_result["value"] == 42

    dict_data = {"name": "test_dict", "value": 100}
    dict_result = crud._extract_data_dict(dict_data)
    assert isinstance(dict_result, dict)
    assert dict_result == dict_data

    invalid_result = crud._extract_data_dict("invalid")
    assert invalid_result == {}


def test_payload_building() -> None:
    """_build_outbox_payload should emit the expected contract."""
    crud = _build_crud()

    class MockRecord:
        id = 123
        name = "test"
        value = 42

    record = cast(DataModel, MockRecord())
    data = {"name": "updated", "value": 99}

    payload = crud._build_outbox_payload(
        action="update",
        record=record,
        user=None,
        data=data,
    )

    required_fields = ["id", "model", "action", "timestamp"]
    for field in required_fields:
        assert field in payload

    assert payload["action"] == "update"
    assert payload["id"] == "123"
    assert payload["data"] == data
