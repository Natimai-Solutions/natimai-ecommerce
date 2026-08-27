"""Invoice model (M3) — an issued invoice is immutable.

Deliberately **not** built on ``Base``/``BaseRouter``: invoices carry no
soft-delete or admin-toggle semantics, and exposing a generic CRUD router
would allow editing an issued accounting document. Only creation (via
``invoice_service.issue_invoice_for_order``) and reads exist.

Everything printed on the PDF is frozen in ``snapshot`` at issuance: seller
and buyer identity, lines, and the VAT breakdown. Re-rendering the PDF later
therefore reproduces the original document even if the product catalogue,
tax rates or the customer's address have changed since.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class Invoice(SQLModel, table=True):
    """An issued invoice, tied 1-to-1 to a paid order."""

    __tablename__ = "invoices"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Identifiant unique de la facture",
    )
    invoice_number: str = Field(
        max_length=32,
        unique=True,
        index=True,
        description="Numéro de facture légal (FAC-AAAA-NNNNN), séquence continue",
    )
    fiscal_year: int = Field(
        index=True,
        description="Exercice comptable de rattachement (année d'émission)",
    )
    sequence_number: int = Field(
        description="Rang dans la séquence de l'exercice (1, 2, 3… sans trou)",
    )
    order_id: uuid.UUID = Field(
        foreign_key="orders.id",
        unique=True,
        index=True,
        description="Commande facturée (une facture par commande)",
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
        description="Client facturé",
    )
    issued_at: datetime = Field(
        index=True,
        description="Date d'émission (fait foi pour l'exercice comptable)",
    )
    currency: str = Field(
        max_length=8,
        description="Devise de facturation",
    )
    total_excl_tax: Decimal = Field(
        max_digits=12,
        decimal_places=2,
        description="Total hors taxes",
    )
    total_tax: Decimal = Field(
        max_digits=12,
        decimal_places=2,
        description="Total des taxes (TGC/TVA)",
    )
    total_incl_tax: Decimal = Field(
        max_digits=12,
        decimal_places=2,
        description="Total toutes taxes comprises — égal au total de la commande",
    )
    snapshot: dict[str, Any] = Field(
        sa_column=Column(JSON, nullable=False),
        description=(
            "Copie figée de la facture à l'émission (vendeur, client, lignes, "
            "ventilation de taxes) — source de vérité du rendu PDF"
        ),
    )


class InvoiceCounter(SQLModel, table=True):
    """Gap-free per-year invoice counter.

    Allocation locks the year's row (``SELECT … FOR UPDATE``) inside the
    issuing transaction, so a rollback releases the number instead of burning
    it — unlike a PostgreSQL sequence. A legal invoice sequence must have no
    gaps, which is exactly why the order number (M5) uses a different
    mechanism.
    """

    __tablename__ = "invoice_counters"

    fiscal_year: int = Field(
        primary_key=True,
        description="Exercice comptable",
    )
    last_value: int = Field(
        default=0,
        description="Dernier numéro attribué pour cet exercice",
    )


class InvoicePublic(SQLModel):
    """Invoice metadata exposed by the API (the PDF has its own endpoint)."""

    id: uuid.UUID
    invoice_number: str
    fiscal_year: int
    order_id: uuid.UUID
    issued_at: datetime
    currency: str
    total_excl_tax: Decimal
    total_tax: Decimal
    total_incl_tax: Decimal
    order_number: str | None = None


class InvoicesPublic(SQLModel):
    """Paginated list of invoices."""

    data: list[InvoicePublic] = Field(default_factory=list)
    count: int = Field(default=0)
