"""Back-office des demandes de devis (A11).

Le modèle de lancement est « vitrine + devis » : ces demandes sont le principal
flux entrant, et elles ne vivaient que sous forme d'email vers le support.
"""

from __future__ import annotations

import datetime
import uuid
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes.admin_quote_requests import (
    QuoteRequestUpdateBody,
    get_quote_request,
    update_quote_request,
)
from app.core.errors import AppError
from app.features.cart.models.quote_request import (
    CLOSED_QUOTE_STATUSES,
    QuoteRequestStatus,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _quote(**overrides: Any) -> Any:
    quote = SimpleNamespace(
        id=uuid.uuid4(),
        created_at=datetime.datetime(2026, 8, 27, 10, 0, tzinfo=datetime.timezone.utc),
        email="client@example.pf",
        full_name="Alice Tama",
        phone="+689 40 00 00 00",
        status=QuoteRequestStatus.REQUESTED.value,
        user_id=None,
        shipping_address="BP 42, Papeete",
        notes="Livraison avant fin septembre si possible",
        admin_comment=None,
        handled_at=None,
        handled_by_id=None,
        items_snapshot={
            "currency": "XPF",
            "subtotal_amount": "125000.00",
            "items": [
                {"product_name": "Station de travail", "quantity": "1"},
                {"product_name": 'Écran 27"', "quantity": "2"},
            ],
        },
    )
    for key, value in overrides.items():
        setattr(quote, key, value)
    return quote


def _session(quote: Any) -> MagicMock:
    session = MagicMock()
    session.get = AsyncMock(return_value=quote)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _admin() -> Any:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=True)


@pytest.mark.anyio
async def test_the_detail_exposes_the_frozen_cart() -> None:
    """Le panier figé est tout l'intérêt de l'écran : sans lui, l'admin doit
    retourner chercher l'email."""
    quote = _quote()

    detail = await get_quote_request(quote.id, _session(quote), cast(Any, _admin()))

    assert detail.item_count == 2
    assert [item["product_name"] for item in detail.items] == [
        "Station de travail",
        'Écran 27"',
    ]
    assert detail.currency == "XPF"
    assert detail.subtotal_amount == "125000.00"
    assert detail.notes == "Livraison avant fin septembre si possible"


@pytest.mark.anyio
async def test_a_guest_request_is_flagged_as_such() -> None:
    """Un visiteur non connecté n'a pas de compte à rappeler : le distinguer
    change la façon de le recontacter."""
    guest = await get_quote_request(
        uuid.uuid4(), _session(_quote(user_id=None)), cast(Any, _admin())
    )
    known = await get_quote_request(
        uuid.uuid4(), _session(_quote(user_id=uuid.uuid4())), cast(Any, _admin())
    )

    assert guest.is_registered_customer is False
    assert known.is_registered_customer is True


@pytest.mark.anyio
async def test_an_unknown_request_is_a_404() -> None:
    with pytest.raises(AppError) as exc:
        await get_quote_request(uuid.uuid4(), _session(None), cast(Any, _admin()))

    assert exc.value.status_code == 404
    assert exc.value.code == "quote_request.not_found"


@pytest.mark.anyio
async def test_closing_a_request_records_who_and_when() -> None:
    quote = _quote()
    admin = _admin()

    await update_quote_request(
        quote.id,
        QuoteRequestUpdateBody(status=QuoteRequestStatus.WON, admin_comment="Signé"),
        _session(quote),
        cast(Any, admin),
    )

    assert quote.status == "won"
    assert quote.handled_at is not None
    assert quote.handled_by_id == admin.id
    assert quote.admin_comment == "Signé"


@pytest.mark.anyio
async def test_reopening_a_request_clears_the_handling_marks() -> None:
    """`handled_at` marque la clôture, pas la dernière modification : une
    demande rouverte ne doit pas rester comptée comme traitée."""
    quote = _quote(
        status=QuoteRequestStatus.LOST.value,
        handled_at=datetime.datetime(2026, 8, 20, tzinfo=datetime.timezone.utc),
        handled_by_id=uuid.uuid4(),
    )

    await update_quote_request(
        quote.id,
        QuoteRequestUpdateBody(status=QuoteRequestStatus.IN_PROGRESS),
        _session(quote),
        cast(Any, _admin()),
    )

    assert quote.status == "in_progress"
    assert quote.handled_at is None
    assert quote.handled_by_id is None


@pytest.mark.anyio
async def test_a_comment_alone_does_not_move_the_status() -> None:
    """Les deux champs sont indépendants : annoter une demande en cours ne doit
    pas la faire changer d'état."""
    quote = _quote(status=QuoteRequestStatus.IN_PROGRESS.value)

    await update_quote_request(
        quote.id,
        QuoteRequestUpdateBody(admin_comment="Relancé par téléphone"),
        _session(quote),
        cast(Any, _admin()),
    )

    assert quote.status == "in_progress"
    assert quote.admin_comment == "Relancé par téléphone"
    assert quote.handled_at is None


@pytest.mark.anyio
async def test_a_blank_comment_clears_it() -> None:
    quote = _quote(admin_comment="ancien commentaire")

    await update_quote_request(
        quote.id,
        QuoteRequestUpdateBody(admin_comment="   "),
        _session(quote),
        cast(Any, _admin()),
    )

    assert quote.admin_comment is None


def test_closed_statuses_are_the_terminal_ones() -> None:
    assert CLOSED_QUOTE_STATUSES == {
        QuoteRequestStatus.WON,
        QuoteRequestStatus.LOST,
        QuoteRequestStatus.CANCELLED,
    }
    # `email_failed` n'est PAS terminal : c'est justement la demande qu'il faut
    # rattraper à la main, elle doit rester dans la file de travail.
    assert QuoteRequestStatus.EMAIL_FAILED not in CLOSED_QUOTE_STATUSES
