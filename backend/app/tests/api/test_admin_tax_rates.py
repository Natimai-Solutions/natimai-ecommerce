"""Unit tests for the admin tax-rate endpoints (direct calls, mocked session)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.admin_tax_rates import (
    TaxRateAssignBody,
    _get_active_tax_rate,
    assign_tax_rate_to_category,
    assign_tax_rate_to_product,
    create_tax_rate,
    list_tax_rates,
    update_tax_rate,
)
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.product.crud.category import crud_category
from app.features.product.crud.product import crud_product
from app.features.product.models.tax_rate import TaxRate, TaxRateCreate, TaxRateUpdate
from app.features.user.models.user import User


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _admin() -> User:
    return cast(User, SimpleNamespace(id=uuid4()))


_DEFAULT_VALID_FROM = date(2026, 1, 1)


def _rate(
    *,
    code: str = "TGC_NORMAL",
    valid_from: date = _DEFAULT_VALID_FROM,
    is_active: bool = True,
) -> TaxRate:
    return TaxRate(
        id=uuid4(),
        code=code,
        label="TGC 16%",
        rate_pct=Decimal("16.00"),
        territory_code="PF",
        valid_from=valid_from,
        valid_until=None,
        is_active=is_active,
    )


@pytest.mark.anyio
async def test_get_active_tax_rate_found() -> None:
    rate = _rate()
    session = AsyncMock()
    session.get = AsyncMock(return_value=rate)
    assert await _get_active_tax_rate(session, rate.id) is rate


@pytest.mark.anyio
@pytest.mark.parametrize("returned", [None, "inactive"])
async def test_get_active_tax_rate_404(returned: object) -> None:
    session = AsyncMock()
    value = None if returned is None else _rate(is_active=False)
    session.get = AsyncMock(return_value=value)
    with pytest.raises(AppError) as exc:
        await _get_active_tax_rate(session, uuid4())
    assert exc.value.status_code == 404
    assert exc.value.code == "tax_rate.not_found"


@pytest.mark.anyio
@pytest.mark.parametrize("valid", [None, True, False])
async def test_list_tax_rates_filters(valid: bool | None) -> None:
    rates = [_rate(), _rate(code="TGC_REDUCED")]
    session = AsyncMock()
    session.exec = AsyncMock(return_value=SimpleNamespace(all=Mock(return_value=rates)))
    resp = await list_tax_rates(
        session=session,
        _current_user=_admin(),
        territory_code="pf",
        valid=valid,
    )
    assert resp.count == 2
    assert {r.code for r in resp.data} == {"TGC_NORMAL", "TGC_REDUCED"}


@pytest.mark.anyio
async def test_create_tax_rate() -> None:
    session = AsyncMock()
    session.add = Mock()
    payload = TaxRateCreate(
        code="TGC_NORMAL",
        label="TGC 16%",
        rate_pct=Decimal("16.00"),
        territory_code="PF",
        valid_from=date(2026, 1, 1),
    )
    resp = await create_tax_rate(
        payload=payload, session=session, current_user=_admin()
    )
    assert resp.code == "TGC_NORMAL"
    assert resp.rate_pct == Decimal("16.00")
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_update_tax_rate_label_and_valid_until() -> None:
    rate = _rate()
    session = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=rate)
    resp = await update_tax_rate(
        tax_rate_id=rate.id,
        payload=TaxRateUpdate(label="TGC normal", valid_until=date(2026, 12, 31)),
        session=session,
        _current_user=_admin(),
    )
    assert resp.label == "TGC normal"
    assert resp.valid_until == date(2026, 12, 31)


@pytest.mark.anyio
async def test_update_tax_rate_rejects_valid_until_before_valid_from() -> None:
    rate = _rate(valid_from=date(2026, 6, 1))
    session = AsyncMock()
    session.add = Mock()
    session.get = AsyncMock(return_value=rate)
    with pytest.raises(AppError) as exc:
        await update_tax_rate(
            tax_rate_id=rate.id,
            payload=TaxRateUpdate(valid_until=date(2026, 1, 1)),
            session=session,
            _current_user=_admin(),
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "tax_rate.invalid_valid_until"


@pytest.mark.anyio
async def test_assign_tax_rate_to_product_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    monkeypatch.setattr(
        crud_product, "read", AsyncMock(side_effect=RecordNotFoundError("nope"))
    )
    with pytest.raises(AppError) as exc:
        await assign_tax_rate_to_product(
            product_id=uuid4(),
            payload=TaxRateAssignBody(tax_rate_id=None),
            session=session,
            current_user=_admin(),
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "product.not_found"


@pytest.mark.anyio
async def test_assign_tax_rate_to_category_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    monkeypatch.setattr(
        crud_category, "read", AsyncMock(side_effect=RecordNotFoundError("nope"))
    )
    with pytest.raises(AppError) as exc:
        await assign_tax_rate_to_category(
            category_id=uuid4(),
            payload=TaxRateAssignBody(tax_rate_id=None),
            session=session,
            current_user=_admin(),
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "category.not_found"
