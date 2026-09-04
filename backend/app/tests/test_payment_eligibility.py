"""Unit tests for payment-method eligibility (audit item Q3).

Ce module décide quels moyens de paiement un client voit, et le même code
autorise l'initiation côté serveur : une erreur ici expose un moyen de paiement
à un groupe qui n'y a pas droit, ou dépasse silencieusement le plafond d'un
paiement à la commande.

Trois règles s'y croisent :
- aucune ligne d'éligibilité = ouvert à tous (défaut ouvert) ;
- au moins une ligne = réservé aux groupes listés, et à eux seuls ;
- `max_amount`, s'il est posé, retire le moyen au-delà du total du panier.

La base est simulée : seule la logique est testée.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.payment.services.eligibility import (
    check_payment_method_eligible,
    get_default_price_group_id,
    get_eligible_payment_methods,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _method(
    *,
    sort_order: int = 0,
    max_amount: Decimal | None = None,
) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        is_active=True,
        is_admin_active=True,
        max_amount=max_amount,
        sort_order=sort_order,
    )


class _Result:
    """Le résultat d'un `session.exec`, servi depuis une liste préparée."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return self._rows


class _Session:
    """Sert les résultats dans l'ordre où le service pose ses requêtes.

    Ordre attendu : (groupe par défaut, si aucun groupe n'est passé) → moyens
    actifs → moyens restreints → moyens autorisés pour le groupe.
    """

    def __init__(self, *results: list[Any]) -> None:
        self._queue = list(results)
        self.exec_count = 0

    async def exec(self, _statement: Any) -> _Result:
        self.exec_count += 1
        return _Result(self._queue.pop(0) if self._queue else [])


def _session(*results: list[Any]) -> Any:
    """`_Session` vue comme une AsyncSession par les signatures du service."""
    return cast(AsyncSession, _Session(*results))


# ---------------------------------------------------------------------------
# get_default_price_group_id
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_default_price_group_id_is_none_when_no_group_is_flagged() -> None:
    assert await get_default_price_group_id(_session([])) is None


@pytest.mark.anyio
async def test_default_price_group_id_returns_the_flagged_group() -> None:
    group = SimpleNamespace(id=uuid.uuid4())

    assert await get_default_price_group_id(_session([group])) == group.id


# ---------------------------------------------------------------------------
# Défaut ouvert vs restriction
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_method_without_eligibility_rows_is_open_to_everyone() -> None:
    open_method = _method()
    session = _session([open_method], [], [])

    eligible = await get_eligible_payment_methods(session, price_group_id=uuid.uuid4())

    assert [m.id for m in eligible] == [open_method.id]


@pytest.mark.anyio
async def test_restricted_method_is_hidden_from_a_group_that_is_not_listed() -> None:
    restricted = _method()
    # Restreint (il a des lignes) mais aucune ne vise ce groupe.
    session = _session([restricted], [restricted.id], [])

    eligible = await get_eligible_payment_methods(session, price_group_id=uuid.uuid4())

    assert eligible == []


@pytest.mark.anyio
async def test_restricted_method_is_visible_to_a_listed_group() -> None:
    restricted = _method()
    session = _session([restricted], [restricted.id], [restricted.id])

    eligible = await get_eligible_payment_methods(session, price_group_id=uuid.uuid4())

    assert [m.id for m in eligible] == [restricted.id]


@pytest.mark.anyio
async def test_without_group_and_without_default_only_open_methods_remain() -> None:
    """Sans groupe résolu, la requête des autorisations n'est même pas posée."""
    open_method = _method()
    restricted = _method()
    session = _session([], [open_method, restricted], [restricted.id])

    eligible = await get_eligible_payment_methods(session, price_group_id=None)

    assert [m.id for m in eligible] == [open_method.id]
    # groupe par défaut + moyens actifs + moyens restreints, pas d'autorisations
    assert session.exec_count == 3


@pytest.mark.anyio
async def test_default_group_is_used_when_none_is_given() -> None:
    default_group = SimpleNamespace(id=uuid.uuid4())
    restricted = _method()
    session = _session([default_group], [restricted], [restricted.id], [restricted.id])

    eligible = await get_eligible_payment_methods(session, price_group_id=None)

    assert [m.id for m in eligible] == [restricted.id]


@pytest.mark.anyio
async def test_no_active_method_short_circuits_the_remaining_queries() -> None:
    session = _session([])

    assert (
        await get_eligible_payment_methods(session, price_group_id=uuid.uuid4()) == []
    )
    assert session.exec_count == 1


# ---------------------------------------------------------------------------
# Plafond max_amount
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_method_is_hidden_when_the_cart_exceeds_its_ceiling() -> None:
    capped = _method(max_amount=Decimal("50000"))
    session = _session([capped], [], [])

    eligible = await get_eligible_payment_methods(
        session, price_group_id=uuid.uuid4(), cart_total=Decimal("50001")
    )

    assert eligible == []


@pytest.mark.anyio
async def test_a_cart_exactly_at_the_ceiling_still_passes() -> None:
    """Le plafond est inclusif : `max_amount >= cart_total`."""
    capped = _method(max_amount=Decimal("50000"))
    session = _session([capped], [], [])

    eligible = await get_eligible_payment_methods(
        session, price_group_id=uuid.uuid4(), cart_total=Decimal("50000")
    )

    assert [m.id for m in eligible] == [capped.id]


@pytest.mark.anyio
async def test_ceiling_is_ignored_when_no_cart_total_is_given() -> None:
    """Le listing sans panier (écran admin) ne doit rien masquer."""
    capped = _method(max_amount=Decimal("1"))
    session = _session([capped], [], [])

    eligible = await get_eligible_payment_methods(session, price_group_id=uuid.uuid4())

    assert [m.id for m in eligible] == [capped.id]


@pytest.mark.anyio
async def test_methods_without_ceiling_survive_any_cart_total() -> None:
    uncapped = _method()
    session = _session([uncapped], [], [])

    eligible = await get_eligible_payment_methods(
        session, price_group_id=uuid.uuid4(), cart_total=Decimal("999999999")
    )

    assert [m.id for m in eligible] == [uncapped.id]


@pytest.mark.anyio
async def test_result_is_ordered_by_sort_order() -> None:
    last = _method(sort_order=30)
    first = _method(sort_order=10)
    middle = _method(sort_order=20)
    session = _session([last, first, middle], [], [])

    eligible = await get_eligible_payment_methods(session, price_group_id=uuid.uuid4())

    assert [m.id for m in eligible] == [first.id, middle.id, last.id]


# ---------------------------------------------------------------------------
# check_payment_method_eligible — la garde côté initiation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_accepts_an_eligible_method() -> None:
    method = _method()
    session = _session([method], [], [])

    assert await check_payment_method_eligible(
        session,
        payment_method_id=method.id,
        price_group_id=uuid.uuid4(),
        amount=Decimal("1000"),
    )


@pytest.mark.anyio
async def test_check_refuses_a_method_over_its_ceiling() -> None:
    """Même moyen, même groupe : seul le montant le rend inéligible."""
    method = _method(max_amount=Decimal("1000"))
    session = _session([method], [], [])

    assert not await check_payment_method_eligible(
        session,
        payment_method_id=method.id,
        price_group_id=uuid.uuid4(),
        amount=Decimal("1001"),
    )


@pytest.mark.anyio
async def test_check_refuses_a_method_restricted_to_another_group() -> None:
    method = _method()
    session = _session([method], [method.id], [])

    assert not await check_payment_method_eligible(
        session,
        payment_method_id=method.id,
        price_group_id=uuid.uuid4(),
        amount=Decimal("1000"),
    )
