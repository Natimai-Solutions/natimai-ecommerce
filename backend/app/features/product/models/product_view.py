"""Daily product view counters (M1 — « produits les plus vus »).

One row per product and day, incremented by the storefront product page.
Coarse on purpose: no visitor identity, no raw event log — enough to rank
products over a window (« les plus consultés ces 30 derniers jours ») at a
size that stays proportional to catalog × days, not to traffic.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlmodel import Field, SQLModel, UniqueConstraint


class ProductViewDaily(SQLModel, table=True):
    """Views of one product on one day."""

    __tablename__ = "product_view_daily"
    __table_args__ = (UniqueConstraint("product_id", "day"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    product_id: uuid.UUID = Field(foreign_key="products.id", index=True)
    day: date = Field(index=True)
    views: int = Field(default=0, ge=0)
