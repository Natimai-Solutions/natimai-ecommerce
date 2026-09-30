"""The Ingram adapter translates the generic purchase order (R4 / S4)."""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services.suppliers.base import PurchaseOrderLine, ShipTo
from app.services.suppliers.ingram_micro import IngramMicroAdapter


@pytest.mark.asyncio
async def test_generic_order_becomes_an_ingram_body() -> None:
    service = AsyncMock()
    service.create_purchase_order = AsyncMock(
        return_value={"ingramOrderNumber": "IM-1", "orderStatus": "CREATED"}
    )
    adapter = IngramMicroAdapter(service=service)
    assert adapter.supports_purchase_orders is True

    result = await adapter.create_purchase_order(
        customer_order_number="abc",
        lines=[
            PurchaseOrderLine(
                supplier_sku="IM-SKU",
                quantity=2,
                unit_price=Decimal("12.50"),
                vendor_part_number="MPN",
            ),
            PurchaseOrderLine(supplier_sku="IM-2", quantity=1),
        ],
        ship_to=ShipTo(
            address_line1="1 rue du Port",
            city="Papeete",
            country_code="PF",
            postal_code="98714",
        ),
        notes="Local order x",
    )

    kwargs: dict[str, Any] = service.create_purchase_order.await_args.kwargs
    assert kwargs["lines"] == [
        {
            "ingramPartNumber": "IM-SKU",
            "quantity": 2,
            "unitPrice": 12.5,
            "vendorPartNumber": "MPN",
        },
        {"ingramPartNumber": "IM-2", "quantity": 1},
    ]
    assert kwargs["ship_to"] == {
        "addressLine1": "1 rue du Port",
        "city": "Papeete",
        "countryCode": "PF",
        "postalCode": "98714",
    }
    assert (result.order_number, result.status_label) == ("IM-1", "CREATED")
