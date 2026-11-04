"""A classic shop gets a main warehouse, so its first delivery mode needs nothing.

Delivery modes leave from the main warehouse. The seed never overrides a
flagged one, flags a lone existing warehouse instead of duplicating it, and
leaves the choice to the admin when there are several. The DB is mocked: each
``session.exec`` returns the next prepared result.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.features import initial_data as seed_module
from app.features.place.models import Place


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _session(*results: list[Any]) -> MagicMock:
    """A session whose successive ``exec`` calls yield ``results``."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    rows = []
    for result in results:
        row = MagicMock()
        row.first.return_value = result[0] if result else None
        row.all.return_value = result
        rows.append(row)
    session.exec = AsyncMock(side_effect=rows)
    return session


@pytest.mark.anyio
async def test_flagged_main_warehouse_is_left_alone() -> None:
    main = Place(
        name="Dépôt", type="warehouse", is_warehouse=True, is_main_warehouse=True
    )
    session = _session([main])

    await seed_module._seed_main_warehouse(session)

    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_lone_warehouse_is_flagged_not_duplicated() -> None:
    lone = Place(name="Dépôt Lyon", type="warehouse", is_warehouse=True)
    session = _session([], [lone])

    await seed_module._seed_main_warehouse(session)

    assert lone.is_main_warehouse is True
    session.add.assert_called_once_with(lone)
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_several_warehouses_leave_the_choice_to_the_admin() -> None:
    a = Place(name="A", type="warehouse", is_warehouse=True)
    b = Place(name="B", type="warehouse", is_warehouse=True)
    session = _session([], [a, b])

    await seed_module._seed_main_warehouse(session)

    assert not a.is_main_warehouse and not b.is_main_warehouse
    session.add.assert_not_called()


@pytest.mark.anyio
async def test_no_warehouse_creates_one_under_the_shop_country() -> None:
    code = settings.territory_profile.country_code
    country = Place(name="Pays", type="country", code=code, country=code)
    session = _session([], [], [country])

    await seed_module._seed_main_warehouse(session)

    created = session.add.call_args.args[0]
    assert isinstance(created, Place)
    assert created.type == "warehouse"
    assert created.is_warehouse is True
    assert created.is_main_warehouse is True
    assert created.parent_id == country.id
    assert created.country == code
    session.commit.assert_awaited_once()
