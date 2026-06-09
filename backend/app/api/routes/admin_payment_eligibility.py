"""Admin endpoints: manage payment method ↔ price group eligibility."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Response
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.payment.crud.payment_method import crud_payment_method
from app.features.payment.models.payment_method_eligibility import (
    PaymentMethodEligibility,
)
from app.features.product.models.price_group import PriceGroup

router = APIRouter(prefix="/admin/payment-methods", tags=["admin-payment"])


@router.get("/{payment_method_id}/groups")
async def list_eligible_groups(
    payment_method_id: uuid.UUID,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> list[dict[str, Any]]:
    """List price groups that are explicitly allowed to use a payment method.

    An empty list means the method is open to all groups (no restriction).
    """
    try:
        await crud_payment_method.read(session, id=payment_method_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="payment.method.not_found",
            status_code=404,
            message=f"Payment method {payment_method_id} not found",
            details={"payment_method_id": str(payment_method_id)},
        ) from exc

    rows_stmt = select(PaymentMethodEligibility).where(
        PaymentMethodEligibility.payment_method_id == payment_method_id
    )
    rows_result = await session.exec(rows_stmt)
    rows = rows_result.all()

    group_ids = [r.price_group_id for r in rows]
    if not group_ids:
        return []

    groups_stmt = select(PriceGroup).where(col(PriceGroup.id).in_(group_ids))
    groups_result = await session.exec(groups_stmt)
    groups = groups_result.all()

    return [{"id": str(g.id), "code": g.code, "label": g.label} for g in groups]


@router.post("/{payment_method_id}/groups/{price_group_id}", status_code=201)
async def add_eligible_group(
    payment_method_id: uuid.UUID,
    price_group_id: uuid.UUID,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> dict[str, Any]:
    """Allow a price group to use a payment method. Idempotent."""
    try:
        await crud_payment_method.read(session, id=payment_method_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="payment.method.not_found",
            status_code=404,
            message=f"Payment method {payment_method_id} not found",
            details={"payment_method_id": str(payment_method_id)},
        ) from exc

    price_group = await session.get(PriceGroup, price_group_id)
    if price_group is None:
        raise AppError(
            code="price_group.not_found",
            status_code=404,
            message=f"Price group {price_group_id} not found",
            details={"price_group_id": str(price_group_id)},
        )

    existing = await session.get(
        PaymentMethodEligibility,
        {"payment_method_id": payment_method_id, "price_group_id": price_group_id},
    )
    if existing is None:
        session.add(
            PaymentMethodEligibility(
                payment_method_id=payment_method_id,
                price_group_id=price_group_id,
            )
        )
        await session.commit()

    return {
        "payment_method_id": str(payment_method_id),
        "price_group_id": str(price_group_id),
    }


@router.delete("/{payment_method_id}/groups/{price_group_id}", status_code=204)
async def remove_eligible_group(
    payment_method_id: uuid.UUID,
    price_group_id: uuid.UUID,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> Response:
    """Remove a price group restriction from a payment method. Idempotent."""
    row = await session.get(
        PaymentMethodEligibility,
        {"payment_method_id": payment_method_id, "price_group_id": price_group_id},
    )
    if row is not None:
        await session.delete(row)
        await session.commit()
    return Response(status_code=204)
