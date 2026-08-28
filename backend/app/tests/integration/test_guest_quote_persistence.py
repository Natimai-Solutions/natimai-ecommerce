"""Une demande de devis invitée survit à l'envoi d'email (A11).

C'était le vrai trou : les demandes des visiteurs non connectés n'étaient pas
persistées du tout. Elles n'existaient que sous forme d'email vers le support,
et un échec d'envoi les perdait définitivement — alors que l'endpoint répondait
201. Le modèle de lancement étant « vitrine + devis », c'est le flux principal.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import cart as cart_routes
from app.core.config import settings
from app.features.cart.models.quote_request import (
    GuestQuoteRequestItem,
    GuestQuoteRequestSubmit,
    QuoteRequest,
    QuoteRequestStatus,
)


def _payload() -> GuestQuoteRequestSubmit:
    return GuestQuoteRequestSubmit(
        customer_email="Visiteur@Example.PF",
        customer_name="Visiteur Anonyme",
        customer_phone="+689 40 00 00 00",
        shipping_address="BP 42, Papeete",
        notes="Devis pour un parc de 10 postes",
        currency="XPF",
        items=[
            GuestQuoteRequestItem(
                product_name="Station de travail",
                quantity=10,
                unit_price=Decimal("125000.00"),
                line_total=Decimal("1250000.00"),
            )
        ],
    )


@pytest.mark.asyncio
async def test_a_guest_request_is_persisted(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "EMAIL_SUPPORT", "support@example.pf")

    async def _delivered(**_: object) -> bool:
        return True

    monkeypatch.setattr(cart_routes, "_send_quote_support_email", _delivered)

    response = await cart_routes.create_guest_quote_request(_payload(), db_session)

    assert response.email_delivered is True

    # Colonnes plutôt qu'entité : l'endpoint a committé, donc les instances de
    # l'identity map sont expirées et les relire déclencherait un rafraîchi
    # synchrone (MissingGreenlet). Deux requêtes courtes plutôt qu'une large :
    # mypy renonce à typer un select() de six colonnes nullables.
    user_id, cart_id, status = (
        await db_session.exec(
            select(
                QuoteRequest.user_id,
                QuoteRequest.cart_id,
                QuoteRequest.status,
            ).where(col(QuoteRequest.email) == "visiteur@example.pf")
        )
    ).one()

    # Ni compte ni panier serveur : c'est précisément ce que le modèle ne
    # savait pas représenter avant.
    assert user_id is None
    assert cart_id is None
    assert status == QuoteRequestStatus.REQUESTED

    full_name, notes, snapshot = (
        await db_session.exec(
            select(
                QuoteRequest.full_name,
                QuoteRequest.notes,
                QuoteRequest.items_snapshot,
            ).where(col(QuoteRequest.email) == "visiteur@example.pf")
        )
    ).one()

    assert full_name == "Visiteur Anonyme"
    assert notes == "Devis pour un parc de 10 postes"
    assert (snapshot or {})["subtotal_amount"] == "1250000.00"
    assert (snapshot or {})["items"][0]["product_name"] == "Station de travail"


@pytest.mark.asyncio
async def test_a_failed_email_leaves_the_request_recoverable(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cas qui justifie l'écran admin : l'email est perdu, pas la demande."""
    monkeypatch.setattr(settings, "EMAIL_SUPPORT", "support@example.pf")

    async def _failed(**_: object) -> bool:
        return False

    monkeypatch.setattr(cart_routes, "_send_quote_support_email", _failed)

    response = await cart_routes.create_guest_quote_request(_payload(), db_session)

    assert response.email_delivered is False

    status = (
        await db_session.exec(
            select(QuoteRequest.status).where(
                col(QuoteRequest.email) == "visiteur@example.pf"
            )
        )
    ).one()
    # Le statut dit exactement ce qui s'est passé, et n'est pas terminal : la
    # demande reste dans la file de travail du back-office.
    assert status == QuoteRequestStatus.EMAIL_FAILED
