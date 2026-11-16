import datetime
import json
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product, ProductCreate, ProductUpdate


def test_product_writes_publish_no_unconsumed_event() -> None:
    """No handler reads the product CRUD events: published on every write,
    a supplier sync queued one per product ahead of the payment events
    (functional audit, November 2026)."""
    assert crud_product.outbox_events == {}


def test_product_create_payload_is_json_serializable() -> None:
    record = cast(
        Product,
        SimpleNamespace(
            id=uuid4(),
            name="Phone",
            description="Demo",
            created_by_id=uuid4(),
        ),
    )
    payload = crud_product._build_outbox_payload(
        action="create",
        record=record,
        user=None,
        data={
            "name": "Phone",
            "synced_at": datetime.datetime.now(datetime.UTC),
            "owner_id": uuid4(),
        },
    )

    assert payload["action"] == "create"
    assert payload["model"] == "Product"
    assert isinstance(payload["data"]["synced_at"], str)
    assert isinstance(payload["data"]["owner_id"], str)

    json.dumps(payload)


def test_product_delete_payload_contains_minimal_safe_data() -> None:
    record = cast(
        Product,
        SimpleNamespace(
            id=uuid4(),
            name="Laptop",
            description="Legacy",
            created_by_id=uuid4(),
        ),
    )

    payload = crud_product._build_outbox_payload(
        action="delete",
        record=record,
        user=None,
    )

    assert payload["action"] == "delete"
    assert payload["data"]["id"] == str(record.id)
    assert payload["data"]["name"] == "Laptop"
    assert payload["data"]["description"] == "Legacy"


def test_extract_data_dict_handles_product_schemas() -> None:
    create_data = ProductCreate(name="Device", base_price=Decimal("99.99"))
    update_data = ProductUpdate(name="Device Pro", base_price=Decimal("129.99"))

    create_dict = crud_product._extract_data_dict(create_data)
    update_dict = crud_product._extract_data_dict(update_data)

    assert create_dict["name"] == "Device"
    assert create_dict["base_price"] == Decimal("99.99")
    assert update_dict["name"] == "Device Pro"
    assert update_dict["base_price"] == Decimal("129.99")
