"""Journal des prix : chaque changement du prix de vente matérialisé
(``Product.sale_price_cached``), avec sa cause.

Écrit là où le prix est écrit — à chaque enregistrement d'un article et à
chaque rafraîchissement en masse — et seulement quand la valeur change, pour
que le balayage nocturne ne remplisse pas la table sans raison.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

#: Cause portée par les écritures unitaires (création / édition / sync).
REASON_PRODUCT_WRITE = "product_write"


class ProductPriceEntry(SQLModel, table=True):
    """Une ligne du journal : ancien prix, nouveau prix, cause, date."""

    __tablename__ = "product_price_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    product_id: uuid.UUID = Field(foreign_key="products.id", index=True)
    old_price: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    new_price: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    #: Ce qui a déclenché le recalcul : ``product_write``, ``nightly``,
    #: ``currency_rate:EUR``, ``tax_rate_created:TVA_NORMALE``, ``category_…``,
    #: ``system_setting:pricing_…``, ``admin_inline``…
    reason: str = Field(max_length=120, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)


class ProductPriceEntryPublic(SQLModel):
    id: uuid.UUID
    product_id: uuid.UUID
    old_price: Decimal | None
    new_price: Decimal | None
    reason: str
    created_at: datetime


def price_change_entry(
    product_id: uuid.UUID,
    old_price: Decimal | None,
    new_price: Decimal | None,
    *,
    reason: str,
) -> ProductPriceEntry | None:
    """The journal line for a price write, or None when nothing changed."""
    if old_price == new_price:
        return None
    return ProductPriceEntry(
        product_id=product_id, old_price=old_price, new_price=new_price, reason=reason
    )


__all__ = [
    "REASON_PRODUCT_WRITE",
    "ProductPriceEntry",
    "ProductPriceEntryPublic",
    "price_change_entry",
]
