from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.routes import suppliers as suppliers_routes
from app.features.user.models.user import User
from app.services.suppliers.base import (
    NormalizedPricing,
    NormalizedProductData,
    SupplierAdapter,
    SupplierHealth,
)


class FakeAdapter(SupplierAdapter):
    name = "demo_supplier"
    display_name = "Demo Supplier"

    def is_sync_enabled(self) -> bool:
        return True

    def is_configured(self) -> bool:
        return False

    async def fetch_catalog(
        self, category: str, **filters: Any
    ) -> AsyncIterator[list[NormalizedProductData]]:
        del category, filters
        if False:
            yield []

    async def fetch_price_and_availability(
        self, skus: list[str]
    ) -> dict[str, NormalizedPricing]:
        del skus
        return {}

    async def health_check(self) -> SupplierHealth:
        return SupplierHealth(
            healthy=False,
            configured=False,
            message="Not used in this test",
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_trigger_inventory_sync_requires_configured_supplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = User(
        email="admin@example.com",
        hashed_password="hashed-password",
        is_superuser=True,
    )

    trigger_inventory_refresh_mock = AsyncMock()
    monkeypatch.setattr(
        suppliers_routes,
        "trigger_inventory_refresh",
        trigger_inventory_refresh_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await suppliers_routes.trigger_inventory_sync(
            adapter=FakeAdapter(),
            request=suppliers_routes.InventoryRefreshRequest(skus=["SKU-1"]),
            _current_user=current_user,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Demo Supplier credentials not configured"
    trigger_inventory_refresh_mock.assert_not_awaited()
