"""Unit tests for the per-declaration customs fees resolver (audit item F3).

Redevances et participations sont dues par déclaration, pas par article : le
résolveur les lit sur le lieu de dédouanement et les rend une fois par
expédition. Un montant non renseigné ne facture rien.

The DB is mocked: only the resolution logic is under test.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.routes.cart import _customs_declaration_fees


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _place(*, name: str, fee: str | None) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        customs_clearance=True,
        customs_declaration_fee=None if fee is None else Decimal(fee),
    )


def _session(places: list[Any]) -> Any:
    async def _exec(_stmt: Any) -> Any:
        result = MagicMock()
        result.all.return_value = places
        return result

    session = MagicMock()
    session.exec = AsyncMock(side_effect=_exec)
    return session


@pytest.mark.anyio
async def test_returns_one_fee_per_customs_place() -> None:
    papeete = _place(name="Papeete", fee="3500")

    fees = await _customs_declaration_fees(_session([papeete]))

    assert len(fees) == 1
    assert fees[0].place_id == papeete.id
    assert fees[0].place_name == "Papeete"
    assert fees[0].amount == Decimal("3500")


@pytest.mark.anyio
async def test_two_borders_mean_two_declarations() -> None:
    """Distinct customs places are distinct declarations — one fee each."""
    fees = await _customs_declaration_fees(
        _session(
            [_place(name="Papeete", fee="3500"), _place(name="Nouméa", fee="2000")]
        )
    )

    assert sorted(fee.amount for fee in fees) == [Decimal("2000"), Decimal("3500")]


@pytest.mark.anyio
async def test_nothing_is_billed_when_no_fee_is_configured() -> None:
    """The amount is a deployment parameter: unset bills nothing (like F1's rates)."""
    assert await _customs_declaration_fees(_session([])) == []
