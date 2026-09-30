# mypy: disable-error-code="assignment,misc,override"
"""Price of an article for one customer group, typed by the admin.

It replaces, for that group only, the reference price less the group's
discount (see product/services/group_pricing.py): a negotiated price for the
administrations, a reseller price on one article…
"""

import uuid
from decimal import Decimal

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class ProductGroupPrice(SQLModel, table=True):
    __tablename__ = "product_group_prices"
    __table_args__ = (
        UniqueConstraint("product_id", "price_group_id", name="uq_product_group_price"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    product_id: uuid.UUID = Field(
        foreign_key="products.id", index=True, ondelete="CASCADE"
    )
    price_group_id: uuid.UUID = Field(
        foreign_key="price_groups.id", index=True, ondelete="CASCADE"
    )
    #: Tax-inclusive unit price for the group, in the reference currency.
    price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
