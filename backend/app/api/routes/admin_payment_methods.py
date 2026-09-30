"""Admin: the payment methods offered to the customers.

The admin creates methods on the types implemented in the code (see
``payment_method_types``), edits their name, description, fee, cap, order,
deposit rule and instructions, switches them on and off, and deletes a method
no payment ever used (a used one is switched off instead, its history stays).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlmodel import col, func, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.models.payment_method_eligibility import (
    PaymentMethodEligibility,
)
from app.features.payment.services.payment_method_types import (
    PaymentMethodType,
    clean_text,
    method_type,
    method_types,
)
from app.features.system.payment_instructions import load_payment_instructions

router = APIRouter(prefix="/admin/payment-methods", tags=["admin-payment"])


class PaymentMethodTypePublic(BaseModel):
    code: str
    label: str
    #: card | wallet | manual | document
    family: str
    supports_instructions: bool
    #: What the customer receives when the method has no instructions of its
    #: own: the type's text (Paramètres système), else the provider's default.
    fallback_instructions: str | None


class AdminPaymentMethod(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    provider_code: str
    type_label: str
    family: str
    supports_instructions: bool
    fee: Decimal
    max_amount: Decimal | None
    sort_order: int
    is_admin_active: bool
    deposit_allowed: bool
    instructions: str | None
    #: Payments made with this method: a used method cannot be deleted.
    payments_count: int


class AdminPaymentMethodWrite(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    fee: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    max_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    sort_order: int | None = Field(default=None, ge=0, le=100_000)
    is_admin_active: bool | None = None
    deposit_allowed: bool | None = None
    instructions: str | None = Field(default=None, max_length=2000)


class AdminPaymentMethodCreate(AdminPaymentMethodWrite):
    provider_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)


def _not_found(payment_method_id: uuid.UUID) -> AppError:
    return AppError(
        code="payment.method.not_found",
        status_code=404,
        message="Moyen de paiement introuvable",
        details={"payment_method_id": str(payment_method_id)},
    )


def _type_of(method: PaymentMethod) -> PaymentMethodType | None:
    return method_type(method.provider_code or "")


async def _payments_count(
    session: SessionDep, method_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not method_ids:
        return {}
    rows = await session.exec(
        select(Payment.payment_method_id, func.count())
        .where(col(Payment.payment_method_id).in_(method_ids))
        .group_by(col(Payment.payment_method_id))
    )
    return {method_id: count for method_id, count in rows.all() if method_id}


def _public(method: PaymentMethod, payments_count: int) -> AdminPaymentMethod:
    kind = _type_of(method)
    return AdminPaymentMethod(
        id=method.id,
        name=method.name,
        description=method.description,
        provider_code=method.provider_code,
        type_label=kind.label if kind else method.provider_code,
        family=kind.family if kind else "unknown",
        supports_instructions=bool(kind and kind.supports_instructions),
        fee=method.fee,
        max_amount=method.max_amount,
        sort_order=method.sort_order,
        is_admin_active=method.is_admin_active,
        deposit_allowed=method.deposit_allowed,
        instructions=method.instructions,
        payments_count=payments_count,
    )


async def _ensure_unique_name(
    session: SessionDep, name: str, *, exclude: uuid.UUID | None = None
) -> None:
    statement = select(PaymentMethod.id).where(
        func.lower(func.trim(col(PaymentMethod.name))) == name.strip().lower()
    )
    if exclude is not None:
        statement = statement.where(col(PaymentMethod.id) != exclude)
    if (await session.exec(statement)).first() is not None:
        raise AppError(
            code="payment.method.name_taken",
            status_code=409,
            message=f"Un moyen de paiement s'appelle déjà « {name.strip()} »",
            details={"name": name.strip()},
        )


def _check_instructions(kind: PaymentMethodType | None, text: str | None) -> None:
    if text and not (kind and kind.supports_instructions):
        raise AppError(
            code="payment.method.instructions_unsupported",
            status_code=400,
            message=(
                "Ce type de paiement n'envoie pas d'instructions au client "
                "(le paiement se fait chez le prestataire)"
            ),
        )


def _apply(method: PaymentMethod, payload: AdminPaymentMethodWrite) -> None:
    fields = payload.model_fields_set
    if "name" in fields and payload.name is not None:
        method.name = payload.name.strip()
    if "description" in fields:
        method.description = clean_text(payload.description)
    if "fee" in fields:
        method.fee = payload.fee or Decimal("0")
    if "max_amount" in fields:
        method.max_amount = payload.max_amount
    if "sort_order" in fields and payload.sort_order is not None:
        method.sort_order = payload.sort_order
    if "is_admin_active" in fields and payload.is_admin_active is not None:
        method.is_admin_active = payload.is_admin_active
    if "deposit_allowed" in fields and payload.deposit_allowed is not None:
        method.deposit_allowed = payload.deposit_allowed
    if "instructions" in fields:
        method.instructions = clean_text(payload.instructions)


@router.get("/types", response_model=list[PaymentMethodTypePublic])
async def list_payment_method_types(
    session: SessionDep, _current_user: CurrentSuperUser
) -> list[PaymentMethodTypePublic]:
    """The types a method can be created on."""
    result = []
    for kind in method_types():
        fallback = None
        if kind.supports_instructions:
            fallback = (
                await load_payment_instructions(session, kind.code)
                or kind.default_instructions
            )
        result.append(
            PaymentMethodTypePublic(
                code=kind.code,
                label=kind.label,
                family=kind.family,
                supports_instructions=kind.supports_instructions,
                fallback_instructions=fallback,
            )
        )
    return result


@router.get("", response_model=list[AdminPaymentMethod])
async def list_admin_payment_methods(
    session: SessionDep, _current_user: CurrentSuperUser
) -> list[AdminPaymentMethod]:
    """Every method, switched on or off, in checkout order."""
    methods = list(
        (
            await session.exec(
                select(PaymentMethod)
                .where(col(PaymentMethod.is_active).is_(True))
                .order_by(col(PaymentMethod.sort_order), col(PaymentMethod.name))
            )
        ).all()
    )
    counts = await _payments_count(session, [m.id for m in methods])
    return [_public(m, counts.get(m.id, 0)) for m in methods]


@router.post("", response_model=AdminPaymentMethod, status_code=201)
async def create_payment_method(
    payload: AdminPaymentMethodCreate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> AdminPaymentMethod:
    """A new method on an existing type (« Virement Banque de Tahiti »)."""
    kind = method_type(payload.provider_code)
    if kind is None:
        raise AppError(
            code="payment.method.type_unknown",
            status_code=400,
            message=f"Type de paiement inconnu : {payload.provider_code}",
            details={"provider_code": payload.provider_code},
        )
    _check_instructions(kind, clean_text(payload.instructions))
    await _ensure_unique_name(session, payload.name)

    sort_order = payload.sort_order
    if sort_order is None:
        last = (await session.exec(select(func.max(PaymentMethod.sort_order)))).first()
        sort_order = int(last or 0) + 10
    method = PaymentMethod(
        name=payload.name.strip(),
        provider_code=kind.code,
        requires_admin_validation=kind.requires_admin_validation,
        requires_document_upload=kind.requires_document_upload,
        sort_order=sort_order,
        created_by_id=current_user.id,
    )
    _apply(method, payload)
    method.sort_order = sort_order
    session.add(method)
    await session.commit()
    await session.refresh(method)
    return _public(method, 0)


@router.patch("/{payment_method_id}", response_model=AdminPaymentMethod)
async def update_payment_method(
    payment_method_id: uuid.UUID,
    payload: AdminPaymentMethodWrite,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> AdminPaymentMethod:
    """Edit a method (its type stays: create another method to change it)."""
    method = await session.get(PaymentMethod, payment_method_id)
    if method is None or not method.is_active:
        raise _not_found(payment_method_id)
    if "name" in payload.model_fields_set:
        if payload.name is None:
            raise AppError(
                code="payment.method.name_required",
                status_code=400,
                message="Le nom du moyen de paiement est obligatoire",
            )
        await _ensure_unique_name(session, payload.name, exclude=method.id)
    if "instructions" in payload.model_fields_set:
        _check_instructions(_type_of(method), clean_text(payload.instructions))
    _apply(method, payload)
    session.add(method)
    await session.commit()
    await session.refresh(method)
    counts = await _payments_count(session, [method.id])
    return _public(method, counts.get(method.id, 0))


@router.delete("/{payment_method_id}", status_code=204)
async def delete_payment_method(
    payment_method_id: uuid.UUID,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> Response:
    """Delete a method no payment used; a used one is switched off instead."""
    method = await session.get(PaymentMethod, payment_method_id)
    if method is None or not method.is_active:
        raise _not_found(payment_method_id)
    used = (await _payments_count(session, [method.id])).get(method.id, 0)
    if used:
        raise AppError(
            code="payment.method.in_use",
            status_code=409,
            message=(
                f"« {method.name} » a servi à {used} paiement(s) : "
                "désactivez-le plutôt que de le supprimer"
            ),
            details={"payments_count": used},
        )
    rules = await session.exec(
        select(PaymentMethodEligibility).where(
            col(PaymentMethodEligibility.payment_method_id) == method.id
        )
    )
    for rule in rules.all():
        await session.delete(rule)
    await session.delete(method)
    await session.commit()
    return Response(status_code=204)
