# mypy: disable-error-code="assignment,misc,override"

import uuid
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PaymentValidationBase(Base):
    payment_id: uuid.UUID = Field(
        foreign_key="payments.id",
        nullable=False,
        index=True,
        description="ID of the payment this validation entry refers to",
    )
    action: str = Field(
        max_length=50,
        index=True,
        description="Validation action: register_intent | approve | reject | request_info",
    )
    admin_user_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="users.id",
        nullable=True,
        index=True,
        description="Admin user who took the action (None for system-initiated entries)",
    )
    reason: str | None = Field(
        default=None,
        max_length=1024,
        description="Reason or comment associated with the action",
    )
    extra_data: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column("metadata", JSON),
        description="Free-form payload (e.g., bank reference, check number)",
    )


class PaymentValidationCreate(PaymentValidationBase, BaseCreate):
    pass


class PaymentValidationUpdate(PaymentValidationBase, BaseUpdate):
    payment_id: uuid.UUID | None = None
    action: str | None = None
    admin_user_id: uuid.UUID | None = None
    reason: str | None = None
    extra_data: dict[str, Any] | None = None


class PaymentValidation(PaymentValidationBase, table=True):
    __tablename__ = "payment_validations"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
    )


class PaymentValidationPublic(PaymentValidationBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class PaymentValidationsPublic(SQLModel):
    data: list[PaymentValidationPublic] = Field(default_factory=list)
    count: int = Field(default=0)
