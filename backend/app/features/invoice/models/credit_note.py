"""Credit note model (Z2) — the accounting counterpart of a refund.

A refund used to change a payment status and nothing else. Money went back to
the customer while the invoice stayed in the books, unchanged, claiming a sale
that no longer held. An issued invoice cannot be edited or cancelled — that is
the whole point of a gap-free sequence — so the correction is a *separate*
document that references the original.

Like :class:`~app.features.invoice.models.invoice.Invoice`, this is
deliberately not built on ``Base``: no soft delete, no admin toggle, no
generic CRUD router. Issued, then read-only.

Amounts are stored **positive**. The document type carries the sign, which is
how an accountant reads it and how the total ties back to the refund amount
without a sign convention to remember.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class CreditNote(SQLModel, table=True):
    """An issued credit note, correcting an invoice after a refund."""

    __tablename__ = "credit_notes"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Identifiant unique de l'avoir",
    )
    credit_note_number: str = Field(
        max_length=32,
        unique=True,
        index=True,
        description="Numéro d'avoir légal (AV-AAAA-NNNNN), séquence continue",
    )
    fiscal_year: int = Field(
        index=True,
        description="Exercice comptable de rattachement (année d'émission)",
    )
    sequence_number: int = Field(
        description="Rang dans la séquence de l'exercice (1, 2, 3… sans trou)",
    )
    invoice_id: uuid.UUID = Field(
        foreign_key="invoices.id",
        index=True,
        description=(
            "Facture corrigée. Pas unique : un remboursement partiel peut être "
            "suivi d'un autre, chacun donnant lieu à son propre avoir."
        ),
    )
    refund_id: uuid.UUID = Field(
        foreign_key="refunds.id",
        unique=True,
        index=True,
        description=(
            "Remboursement à l'origine de l'avoir. Unique : c'est la clé "
            "d'idempotence, l'outbox garantissant une livraison au moins une fois."
        ),
    )
    order_id: uuid.UUID = Field(
        foreign_key="orders.id",
        index=True,
        description="Commande concernée",
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
        description="Client crédité",
    )
    issued_at: datetime = Field(
        index=True,
        description="Date d'émission (fait foi pour l'exercice comptable)",
    )
    currency: str = Field(
        max_length=8,
        description="Devise de l'avoir (celle de la facture d'origine)",
    )
    total_excl_tax: Decimal = Field(
        max_digits=12,
        decimal_places=2,
        description="Total hors taxes crédité (positif)",
    )
    total_tax: Decimal = Field(
        max_digits=12,
        decimal_places=2,
        description="Total des taxes créditées (positif)",
    )
    total_incl_tax: Decimal = Field(
        max_digits=12,
        decimal_places=2,
        description="Total TTC crédité (positif) — égal au montant remboursé",
    )
    reason: str | None = Field(
        default=None,
        max_length=1024,
        description="Motif du remboursement, repris du Refund",
    )
    snapshot: dict[str, Any] = Field(
        sa_column=Column(JSON, nullable=False),
        description=(
            "Copie figée de l'avoir à l'émission (vendeur, client, facture "
            "d'origine, ventilation de taxes) — source de vérité du rendu PDF"
        ),
    )
    emailed_at: datetime | None = Field(
        default=None,
        description="Date d'envoi de l'avoir au client (idempotence de l'email)",
    )


class CreditNoteCounter(SQLModel, table=True):
    """Gap-free per-year credit-note counter.

    A separate table from ``invoice_counters`` on purpose: the two sequences
    are legally distinct and must never share numbers. Same locking discipline
    (``SELECT … FOR UPDATE`` inside the issuing transaction).
    """

    __tablename__ = "credit_note_counters"

    fiscal_year: int = Field(
        primary_key=True,
        description="Exercice comptable",
    )
    last_value: int = Field(
        default=0,
        description="Dernier numéro attribué pour cet exercice",
    )


class CreditNotePublic(SQLModel):
    """Credit note metadata exposed by the API (the PDF has its own endpoint)."""

    id: uuid.UUID
    credit_note_number: str
    fiscal_year: int
    invoice_id: uuid.UUID
    order_id: uuid.UUID
    issued_at: datetime
    currency: str
    total_excl_tax: Decimal
    total_tax: Decimal
    total_incl_tax: Decimal
    reason: str | None
    #: Human-readable references read from the frozen snapshot, so a screen
    #: can label the row without a second lookup (None on legacy documents).
    order_number: str | None = None
    invoice_number: str | None = None
