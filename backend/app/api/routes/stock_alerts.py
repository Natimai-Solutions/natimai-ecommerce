"""« Me prévenir » : subscribe from the product page (signed in or not),
list and cancel one's alerts from the account."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlmodel import col, select

from app.api.deps import CurrentUser, CurrentUserOptional, SessionDep
from app.core.errors import AppError
from app.features.product.models.product import Product
from app.features.product.models.stock_alert import (
    StockAlert,
    StockAlertPublic,
    StockAlertSubscribe,
)
from app.features.product.services.stock_alert import subscribe

router = APIRouter(prefix="/stock-alerts", tags=["stock-alerts"])


@router.post("", response_model=StockAlertPublic, status_code=status.HTTP_201_CREATED)
async def subscribe_stock_alert(
    body: StockAlertSubscribe, session: SessionDep, current_user: CurrentUserOptional
) -> StockAlertPublic:
    """Ask to be told when the product is orderable again (idempotent)."""
    product = await session.get(Product, body.product_id)
    if product is None or not product.is_active or not product.is_admin_active:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message="Produit introuvable",
            details={"product_id": str(body.product_id)},
        )
    email = body.email or (current_user.email if current_user else None)
    if not email:
        raise AppError(
            code="stock_alert.email_required",
            status_code=400,
            message="Indiquez l'adresse e-mail à prévenir",
            details={},
        )
    alert = await subscribe(
        session,
        product=product,
        email=str(email),
        user_id=current_user.id if current_user else None,
    )
    product_name = product.name
    await session.commit()
    await session.refresh(alert)
    item = StockAlertPublic.model_validate(alert)
    item.product_name = product_name
    return item


@router.get("/me", response_model=list[StockAlertPublic])
async def list_my_stock_alerts(
    session: SessionDep, current_user: CurrentUser
) -> list[StockAlertPublic]:
    """The customer's alerts (by account, or by the account's e-mail)."""
    rows = (
        await session.exec(
            select(StockAlert, Product.name)
            .join(Product, col(Product.id) == col(StockAlert.product_id))
            .where(
                col(StockAlert.is_active).is_(True),
                col(StockAlert.status) != "cancelled",
                (col(StockAlert.user_id) == current_user.id)
                | (col(StockAlert.email) == str(current_user.email).lower()),
            )
            .order_by(col(StockAlert.created_at).desc())
        )
    ).all()
    items = []
    for alert, name in rows:
        item = StockAlertPublic.model_validate(alert)
        item.product_name = name
        items.append(item)
    return items


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_my_stock_alert(
    alert_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> None:
    """Cancel one of the customer's pending alerts."""
    alert = await session.get(StockAlert, alert_id)
    owned = alert is not None and (
        alert.user_id == current_user.id
        or alert.email == str(current_user.email).lower()
    )
    if alert is None or not owned:
        raise AppError(
            code="stock_alert.not_found",
            status_code=404,
            message="Alerte introuvable",
            details={"alert_id": str(alert_id)},
        )
    alert.status = "cancelled"
    session.add(alert)
    await session.commit()
