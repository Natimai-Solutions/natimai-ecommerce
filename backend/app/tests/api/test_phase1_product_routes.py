from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.routes.product_phase1 import (
    feature_product,
    get_featured_products,
    search_products,
    unfeature_product,
)
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.product.crud.product import crud_product
from app.features.product.models.product import (
    Product,
    ProductFeatureRequest,
    ProductSearchRequest,
)
from app.features.user.models.user import User


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_search_products_returns_data_and_facets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    product = Product(name="Laptop", base_price=Decimal("100000.00"))

    search_mock = AsyncMock(
        return_value={
            "data": [product],
            "count": 1,
            "facets": {
                "manufacturers": {"Dell": 1},
                "categories": {},
                "price_ranges": {"100000+": 1},
            },
        }
    )
    monkeypatch.setattr(crud_product, "search_products", search_mock)

    response = await search_products(
        session=session,
        payload=ProductSearchRequest(q="laptop", limit=10),
    )

    assert response.count == 1
    assert len(response.data) == 1
    assert response.data[0].name == "Laptop"
    assert response.facets.manufacturers["Dell"] == 1


@pytest.mark.anyio
async def test_get_featured_products_honors_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    product = Product(name="Featured", base_price=Decimal("9999.00"))

    featured_mock = AsyncMock(return_value=[product])
    monkeypatch.setattr(crud_product, "get_featured", featured_mock)

    response = await get_featured_products(session=session, limit=5)

    assert response.count == 1
    assert response.data[0].name == "Featured"
    assert featured_mock.await_args is not None
    assert featured_mock.await_args.kwargs["limit"] == 5


@pytest.mark.anyio
async def test_feature_product_returns_404_when_product_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    admin = cast(User, SimpleNamespace(id=uuid4(), is_superuser=True))

    monkeypatch.setattr(
        crud_product,
        "set_featured",
        AsyncMock(side_effect=RecordNotFoundError),
    )

    with pytest.raises(AppError) as exc_info:
        await feature_product(
            product_id=uuid4(),
            payload=ProductFeatureRequest(featured_position=1),
            session=session,
            _current_user=admin,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "product.not_found"


@pytest.mark.anyio
async def test_unfeature_product_returns_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    admin = cast(User, SimpleNamespace(id=uuid4(), is_superuser=True))
    product = Product(name="Featured", base_price=Decimal("1000.00"))

    monkeypatch.setattr(crud_product, "clear_featured", AsyncMock(return_value=product))

    response = await unfeature_product(
        product_id=uuid4(),
        session=session,
        _current_user=admin,
    )

    assert response.name == "Featured"
