"""Grouped departures (« départs groupés », the « vague » of the pre-order spec).

One object carries everything the admin needs for a consolidated shipment:
the order cutoff shown on the storefront, the estimated delivery date, the
orders attached to it and its logistics status. Orders are attached at
checkout to the open, published departure with the nearest cutoff; an admin
can move them by hand. With no open departure the shop behaves as before.
"""

# mypy: disable-error-code="assignment,misc,override"

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import field_validator
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

# Lifecycle, in order. ``open`` is the only status that accepts new orders.
DEPARTURE_STATUSES: tuple[str, ...] = (
    "draft",
    "open",
    "closed",
    "ordered",
    "in_transit",
    "at_customs",
    "received",
    "distributed",
)


def _tz_datetime(*, index: bool = False, nullable: bool = True) -> Column:  # type: ignore[type-arg]
    return Column(DateTime(timezone=True), index=index, nullable=nullable)


def check_status(value: str | None) -> str | None:
    """Reject a status outside the lifecycle (shared by the write schemas)."""
    if value is not None and value not in DEPARTURE_STATUSES:
        raise ValueError(
            f"statut inconnu '{value}', attendu : {', '.join(DEPARTURE_STATUSES)}"
        )
    return value


class GroupedDepartureBase(Base):
    """Fields shared by the table and its schemas."""

    name: str = Field(max_length=200, description="Ex. « Départ d'octobre »")
    order_cutoff_at: datetime = Field(
        sa_column=_tz_datetime(index=True, nullable=False),
        description="Date limite de commande — la date affichée en vitrine",
    )
    estimated_delivery_at: datetime | None = Field(
        default=None,
        sa_column=_tz_datetime(),
        description="Date de remise estimée au client",
    )
    departure_at: datetime | None = Field(
        default=None,
        sa_column=_tz_datetime(),
        description="Départ physique du groupage, si différent de la clôture",
    )
    status: str = Field(
        default="open",
        max_length=30,
        index=True,
        description="draft | open | closed | ordered | in_transit | at_customs | received | distributed",
    )
    is_published: bool = Field(
        default=False,
        index=True,
        description="Visible en vitrine (bandeau, fiche produit, checkout)",
    )
    min_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Seuil de montant en dessous duquel le départ est reporté",
    )
    min_units: int | None = Field(
        default=None,
        ge=0,
        description="Seuil de pièces en dessous duquel le départ est reporté",
    )
    recurrence_days: int | None = Field(
        default=None,
        ge=1,
        description="À la clôture, crée le départ suivant N jours plus tard",
    )
    notes: str | None = Field(default=None, max_length=2000)
    # Real purchase orders placed for this departure (one per supplier):
    # [{supplier_name, order_number, ordered_at, total_amount, currency}].
    supplier_orders: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSON), description="Bons de commande passés"
    )
    consolidation_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="shipping_route_tracking_consolidations.id",
        index=True,
        description="Consolidation logistique portant le transport de ce départ",
    )

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str) -> str:
        return check_status(value) or value


class GroupedDeparture(GroupedDepartureBase, table=True):
    """Represents a grouped departure."""

    __tablename__ = "grouped_departures"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class GroupedDepartureCreate(GroupedDepartureBase, BaseCreate):
    """Represents grouped departure create."""

    pass


class GroupedDepartureUpdate(BaseUpdate):
    """Represents grouped departure update (partial)."""

    name: str | None = None
    order_cutoff_at: datetime | None = None
    estimated_delivery_at: datetime | None = None
    departure_at: datetime | None = None
    status: str | None = None
    is_published: bool | None = None
    min_amount: Decimal | None = None
    min_units: int | None = None
    recurrence_days: int | None = None
    notes: str | None = None
    consolidation_id: uuid.UUID | None = None
    supplier_orders: list[dict[str, Any]] | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        return check_status(value)


class GroupedDeparturePublic(GroupedDepartureBase, BasePublic):
    """Admin view: every field plus the audit columns."""

    id: uuid.UUID
    orders_count: int = 0
    orders_total: Decimal = Decimal("0")
    # Orders moved by the status change of this update (PATCH only).
    orders_updated: int = 0


class GroupedDeparturesPublic(SQLModel):
    """Represents grouped departures public."""

    data: list[GroupedDeparturePublic] = Field(default_factory=list)
    count: int = 0


class GroupedDepartureSummary(SQLModel):
    """Storefront view (no auth): what a customer needs to know, nothing more."""

    id: uuid.UUID
    name: str
    order_cutoff_at: datetime
    estimated_delivery_at: datetime | None = None
    departure_at: datetime | None = None
    status: str


class SupplierOrderEntry(SQLModel):
    """A real purchase order recorded on a departure (typed by the admin)."""

    supplier_name: str = Field(max_length=100)
    order_number: str = Field(max_length=100)
    ordered_at: datetime
    total_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="XPF", max_length=8)
    notes: str | None = Field(default=None, max_length=500)


# --- Social / e-mail reminders before the cutoff --------------------------

REMINDER_CHANNELS: tuple[str, ...] = ("webhook",)
REMINDER_ANCHORS: tuple[str, ...] = ("cutoff", "departure")
REMINDER_STATUSES: tuple[str, ...] = ("scheduled", "sent", "failed", "cancelled")

#: Variables usable in a reminder template.
REMINDER_TEMPLATE_VARIABLES: tuple[str, ...] = (
    "name",
    "cutoff_date",
    "days_left",
    "delivery_date",
    "shop_url",
)

#: Default reminders created with each departure (days before the cutoff).
DEFAULT_REMINDERS: tuple[tuple[int, str], ...] = (
    (
        7,
        "📦 Départ groupé « {name} » : commandez avant le {cutoff_date}, "
        "plus que {days_left} jours ! Livraison estimée le {delivery_date}. {shop_url}",
    ),
    (
        2,
        "⏰ Plus que {days_left} jours pour rejoindre le départ groupé « {name} » "
        "(clôture le {cutoff_date}). {shop_url}",
    ),
    (
        0,
        "🚨 Dernier jour ! Le départ groupé « {name} » se clôture aujourd'hui. "
        "{shop_url}",
    ),
)


class DepartureReminderBase(Base):
    """A social-media / newsletter reminder scheduled before a departure."""

    grouped_departure_id: uuid.UUID = Field(
        foreign_key="grouped_departures.id", index=True
    )
    offset_days: int = Field(
        ge=0, description="Days before the anchor date (0 = the day itself)"
    )
    anchor: str = Field(
        default="cutoff", max_length=20, description="cutoff | departure"
    )
    channel: str = Field(default="webhook", max_length=20)
    message_template: str = Field(
        max_length=2000, description="Text with {name}, {cutoff_date}, {days_left}…"
    )
    image_url: str | None = Field(default=None, max_length=500)
    status: str = Field(default="scheduled", max_length=20, index=True)
    scheduled_at: datetime = Field(
        sa_column=_tz_datetime(index=True, nullable=False),
        description="When it fires (anchor − offset, 09:00 local)",
    )
    sent_at: datetime | None = Field(default=None, sa_column=_tz_datetime())
    error: str | None = Field(default=None, max_length=500)

    @field_validator("anchor")
    @classmethod
    def _known_anchor(cls, value: str) -> str:
        if value not in REMINDER_ANCHORS:
            raise ValueError(f"ancre inconnue '{value}'")
        return value

    @field_validator("channel")
    @classmethod
    def _known_channel(cls, value: str) -> str:
        if value not in REMINDER_CHANNELS:
            raise ValueError(f"canal inconnu '{value}'")
        return value


class DepartureReminder(DepartureReminderBase, table=True):
    """Represents a departure reminder."""

    __tablename__ = "departure_reminders"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class DepartureReminderWrite(SQLModel):
    """Admin create / update payload (the fire time is derived)."""

    offset_days: int = Field(ge=0)
    anchor: str = "cutoff"
    channel: str = "webhook"
    message_template: str = Field(max_length=2000)
    image_url: str | None = None


class DepartureReminderPublic(DepartureReminderBase, BasePublic):
    """Admin view, with the message as it will be posted."""

    id: uuid.UUID
    rendered_text: str = ""
