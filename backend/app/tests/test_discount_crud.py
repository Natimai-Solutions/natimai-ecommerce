"""Unit tests for the discount/coupon CRUD (audit item Q3).

`validate_coupon` est la porte d'entrée d'une remise : chacune de ses sorties
est un euro donné ou refusé. Les quatre motifs de refus (inconnu, pas encore
valide, expiré, quota épuisé) sont testés séparément parce qu'ils renvoient
tous `False` — une confusion entre eux passerait inaperçue autrement.

La base est simulée : seule la logique est testée.
"""

from __future__ import annotations

import datetime
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.discount.crud import crud_discount
from app.features.discount.models import DiscountType


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _discount(
    *,
    is_active: bool = True,
    start_date: datetime.datetime | None = None,
    end_date: datetime.datetime | None = None,
    max_uses: int | None = None,
    current_uses: int = 0,
) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        code="PROMO10",
        discount_type=DiscountType.COUPON,
        is_active=is_active,
        start_date=start_date,
        end_date=end_date,
        max_uses=max_uses,
        current_uses=current_uses,
        modify_at=None,
    )


def _session(rows: list[Any]) -> Any:
    """Session dont l'unique `exec` sert `rows`, et qui capture le statement."""
    result = MagicMock()
    result.first.return_value = rows[0] if rows else None
    result.all.return_value = rows

    session = MagicMock()
    session.exec = AsyncMock(return_value=result)
    return session


_YESTERDAY = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
_TOMORROW = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)


# ---------------------------------------------------------------------------
# get_by_code
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_by_code_returns_none_when_nothing_matches() -> None:
    assert await crud_discount.get_by_code(_session([]), "INCONNU") is None


@pytest.mark.anyio
async def test_get_by_code_only_looks_for_active_coupons() -> None:
    """Une promotion n'est pas un coupon : le filtre doit rester dans la requête."""
    session = _session([_discount()])

    found = await crud_discount.get_by_code(session, "PROMO10")

    assert found is not None
    where = str(session.exec.await_args.args[0].whereclause)
    assert "discount_type" in where
    assert "is_active" in where


# ---------------------------------------------------------------------------
# validate_coupon — les quatre refus et l'acceptation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_unknown_code_is_refused() -> None:
    valid, message, discount = await crud_discount.validate_coupon(
        _session([]), "INCONNU"
    )

    assert (valid, discount) == (False, None)
    assert message == "Code coupon invalide"


@pytest.mark.anyio
async def test_coupon_not_yet_valid_is_refused() -> None:
    valid, message, discount = await crud_discount.validate_coupon(
        _session([_discount(start_date=_TOMORROW)]), "PROMO10"
    )

    assert (valid, discount) == (False, None)
    assert message == "Ce coupon n'est pas encore valide"


@pytest.mark.anyio
async def test_expired_coupon_is_refused() -> None:
    valid, message, discount = await crud_discount.validate_coupon(
        _session([_discount(end_date=_YESTERDAY)]), "PROMO10"
    )

    assert (valid, discount) == (False, None)
    assert message == "Ce coupon a expiré"


@pytest.mark.anyio
async def test_coupon_at_its_usage_limit_is_refused() -> None:
    valid, message, discount = await crud_discount.validate_coupon(
        _session([_discount(max_uses=5, current_uses=5)]), "PROMO10"
    )

    assert (valid, discount) == (False, None)
    assert message == "Ce coupon a atteint sa limite d'utilisation"


@pytest.mark.anyio
async def test_deactivated_coupon_is_refused() -> None:
    """Double garde : la requête filtre déjà, le service re-vérifie."""
    valid, message, discount = await crud_discount.validate_coupon(
        _session([_discount(is_active=False)]), "PROMO10"
    )

    assert (valid, discount) == (False, None)
    assert message == "Ce coupon est désactivé"


@pytest.mark.anyio
async def test_coupon_inside_its_window_and_under_its_quota_is_accepted() -> None:
    coupon = _discount(
        start_date=_YESTERDAY, end_date=_TOMORROW, max_uses=5, current_uses=4
    )

    valid, message, discount = await crud_discount.validate_coupon(
        _session([coupon]), "PROMO10"
    )

    assert valid is True
    assert message == "Coupon valide"
    assert discount is coupon


@pytest.mark.anyio
async def test_coupon_without_dates_or_quota_is_accepted() -> None:
    valid, _message, discount = await crud_discount.validate_coupon(
        _session([_discount()]), "PROMO10"
    )

    assert valid is True
    assert discount is not None


# ---------------------------------------------------------------------------
# increment_usage
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_increment_usage_bumps_the_counter_and_commits() -> None:
    coupon = _discount(max_uses=5, current_uses=4)
    session = MagicMock()
    session.get = AsyncMock(return_value=coupon)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    updated = await crud_discount.increment_usage(session, coupon.id)

    assert updated.current_uses == 5
    assert updated.modify_at is not None
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_increment_usage_on_a_missing_discount_commits_nothing() -> None:
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.commit = AsyncMock()

    assert await crud_discount.increment_usage(session, uuid.uuid4()) is None
    session.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_active_promotions
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_active_promotions_filters_on_product_when_given() -> None:
    session = _session([_discount()])

    promotions = await crud_discount.get_active_promotions(
        session, product_id=uuid.uuid4()
    )

    assert len(promotions) == 1
    where = str(session.exec.await_args.args[0].whereclause)
    assert "product_id" in where
    assert "category_id" not in where


@pytest.mark.anyio
async def test_active_promotions_filters_on_category_when_given() -> None:
    session = _session([])

    await crud_discount.get_active_promotions(session, category_id=uuid.uuid4())

    where = str(session.exec.await_args.args[0].whereclause)
    assert "category_id" in where
    assert "product_id" not in where


@pytest.mark.anyio
async def test_active_promotions_without_filter_still_bounds_dates_and_quota() -> None:
    """Sans produit ni catégorie, les garde-fous de validité doivent rester."""
    session = _session([])

    await crud_discount.get_active_promotions(session)

    where = str(session.exec.await_args.args[0].whereclause)
    assert "start_date" in where
    assert "end_date" in where
    assert "max_uses" in where
