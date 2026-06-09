"""Join table: which price groups are allowed to use a payment method."""

import uuid

from sqlmodel import Field, SQLModel


class PaymentMethodEligibility(SQLModel, table=True):
    """Restricts a payment method to specific price groups.

    If no rows exist for a method, it is available to all groups (open default).
    When at least one row exists, only the listed groups may use that method.
    """

    __tablename__ = "payment_method_eligibility"

    payment_method_id: uuid.UUID = Field(
        foreign_key="payment_methods.id",
        primary_key=True,
    )
    price_group_id: uuid.UUID = Field(
        foreign_key="price_groups.id",
        primary_key=True,
    )
