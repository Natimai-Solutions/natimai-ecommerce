"""Back-office des demandes de devis (A11).

Le modèle de lancement retenu est « vitrine + devis » : ces demandes sont donc
le principal flux entrant. Elles ne vivaient jusqu'ici que sous forme d'email
vers le support — une boîte de réception n'est ni une file de travail ni une
trace, et un email perdu emportait la demande avec lui.

Ces endpoints donnent la liste, le détail (avec le panier figé au moment de la
demande) et le suivi : qui l'a prise en charge, où elle en est, pourquoi elle a
été perdue.
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import col, or_, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.cart.models.quote_request import (
    CLOSED_QUOTE_STATUSES,
    QuoteRequest,
    QuoteRequestStatus,
)

router = APIRouter(prefix="/admin/quote-requests", tags=["admin-quote-requests"])


class AdminQuoteRequestListItem(BaseModel):
    """Une ligne de la liste des demandes de devis."""

    quote_request_id: uuid.UUID
    created_at: datetime.datetime | None = None
    email: str
    full_name: str | None = None
    phone: str | None = None
    status: str
    #: Faux pour un visiteur non connecté — utile pour prioriser le rappel.
    is_registered_customer: bool
    item_count: int
    currency: str | None = None
    subtotal_amount: str | None = None
    handled_at: datetime.datetime | None = None


class AdminQuoteRequestDetail(AdminQuoteRequestListItem):
    """Le détail, avec le panier figé au moment de la demande."""

    shipping_address: str | None = None
    notes: str | None = None
    admin_comment: str | None = None
    items: list[dict[str, str | None]] = Field(default_factory=list)


class QuoteRequestUpdateBody(BaseModel):
    """Mise à jour du suivi. Les deux champs sont indépendants."""

    status: QuoteRequestStatus | None = None
    admin_comment: str | None = Field(default=None, max_length=2000)


def _snapshot(quote: QuoteRequest) -> dict[str, object]:
    return quote.items_snapshot or {}


def _to_list_item(quote: QuoteRequest) -> AdminQuoteRequestListItem:
    snapshot = _snapshot(quote)
    items = snapshot.get("items")
    return AdminQuoteRequestListItem(
        quote_request_id=quote.id,
        created_at=quote.created_at,
        email=quote.email,
        full_name=quote.full_name,
        phone=quote.phone,
        status=quote.status,
        is_registered_customer=quote.user_id is not None,
        item_count=len(items) if isinstance(items, list) else 0,
        currency=str(snapshot.get("currency")) if snapshot.get("currency") else None,
        subtotal_amount=(
            str(snapshot.get("subtotal_amount"))
            if snapshot.get("subtotal_amount")
            else None
        ),
        handled_at=quote.handled_at,
    )


def _to_detail(quote: QuoteRequest) -> AdminQuoteRequestDetail:
    snapshot = _snapshot(quote)
    raw_items = snapshot.get("items")
    return AdminQuoteRequestDetail(
        **_to_list_item(quote).model_dump(),
        shipping_address=quote.shipping_address,
        notes=quote.notes,
        admin_comment=quote.admin_comment,
        items=list(raw_items) if isinstance(raw_items, list) else [],
    )


async def _read_quote(session: SessionDep, quote_id: uuid.UUID) -> QuoteRequest:
    quote = await session.get(QuoteRequest, quote_id)
    if quote is None:
        raise AppError(
            code="quote_request.not_found",
            status_code=404,
            message=f"Quote request '{quote_id}' not found",
            details={"quote_request_id": str(quote_id)},
        )
    return quote


@router.get("", response_model=list[AdminQuoteRequestListItem])
async def list_quote_requests(
    session: SessionDep,
    _admin: CurrentSuperUser,
    skip: int = 0,
    limit: int = 100,
    status: QuoteRequestStatus | None = None,
    search: str | None = None,
    open_only: bool = False,
) -> list[AdminQuoteRequestListItem]:
    """Lister les demandes, les plus récentes d'abord.

    ``open_only`` masque les demandes closes : c'est la vue de travail
    quotidienne, où une demande traitée n'a plus à encombrer la file.
    ``search`` cherche dans l'email et le nom, en insensible à la casse.
    """
    statement = select(QuoteRequest)
    if status is not None:
        statement = statement.where(col(QuoteRequest.status) == status.value)
    if open_only:
        statement = statement.where(
            col(QuoteRequest.status).notin_([s.value for s in CLOSED_QUOTE_STATUSES])
        )
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                col(QuoteRequest.email).ilike(pattern),
                col(QuoteRequest.full_name).ilike(pattern),
            )
        )
    statement = (
        statement.order_by(col(QuoteRequest.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    result = await session.exec(statement)
    return [_to_list_item(quote) for quote in result.all()]


@router.get("/{quote_id}", response_model=AdminQuoteRequestDetail)
async def get_quote_request(
    quote_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> AdminQuoteRequestDetail:
    """Le détail d'une demande, panier figé compris."""
    return _to_detail(await _read_quote(session, quote_id))


@router.patch("/{quote_id}", response_model=AdminQuoteRequestDetail)
async def update_quote_request(
    quote_id: uuid.UUID,
    body: QuoteRequestUpdateBody,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> AdminQuoteRequestDetail:
    """Faire avancer le suivi d'une demande.

    Le contenu de la demande (contact, panier figé, message du client) n'est
    jamais modifiable : c'est ce que le client a effectivement envoyé.
    """
    quote = await _read_quote(session, quote_id)

    if body.status is not None:
        quote.status = body.status.value
        # `handled_at` marque la clôture, pas la dernière modification : une
        # demande rouverte doit repartir sans date de traitement.
        if body.status in CLOSED_QUOTE_STATUSES:
            quote.handled_at = datetime.datetime.now()
            quote.handled_by_id = admin.id
        else:
            quote.handled_at = None
            quote.handled_by_id = None

    if body.admin_comment is not None:
        quote.admin_comment = body.admin_comment.strip() or None

    session.add(quote)
    await session.commit()
    await session.refresh(quote)
    return _to_detail(quote)
