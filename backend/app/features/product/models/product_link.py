"""Related products (R9 / T7): manual links and category rules.

``product_links`` ties one product to another as an *accessory* (« complétez
votre équipement ») or an *alternative*; ``category_links`` says which
categories to suggest from a category (« dans PC fixes, proposer Écrans et
Claviers »). The storefront block shows the manual links first, in their
order, then the best sellers of the suggested categories, never an
unavailable product.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

LinkKind = Literal["accessory", "alternative"]
LINK_KINDS: tuple[str, ...] = ("accessory", "alternative")


class ProductLink(SQLModel, table=True):
    """``product_id`` → ``linked_product_id`` as an accessory or an alternative."""

    __tablename__ = "product_links"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "linked_product_id", "kind", name="uq_product_links_pair"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    product_id: uuid.UUID = Field(
        foreign_key="products.id", index=True, ondelete="CASCADE"
    )
    linked_product_id: uuid.UUID = Field(
        foreign_key="products.id", index=True, ondelete="CASCADE"
    )
    kind: str = Field(default="accessory", max_length=16, index=True)
    position: int = Field(default=0)
    created_at: datetime | None = Field(default=None)


class CategoryLink(SQLModel, table=True):
    """From the products of ``category_id``, suggest ``suggested_category_id``."""

    __tablename__ = "category_links"
    __table_args__ = (
        UniqueConstraint(
            "category_id", "suggested_category_id", name="uq_category_links_pair"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    category_id: uuid.UUID = Field(
        foreign_key="categories.id", index=True, ondelete="CASCADE"
    )
    suggested_category_id: uuid.UUID = Field(
        foreign_key="categories.id", index=True, ondelete="CASCADE"
    )
    position: int = Field(default=0)


class ProductLinkWrite(SQLModel):
    """One line of the « Articles liés » section of the product form."""

    linked_product_id: uuid.UUID
    kind: str = Field(default="accessory", max_length=16)
    position: int = 0


class ProductLinkPublic(SQLModel):
    """A link as the back-office lists it: the target's identity for the row."""

    id: uuid.UUID
    linked_product_id: uuid.UUID
    kind: str
    position: int
    name: str
    vendor_part_number: str | None = None
    supplier_sku: str | None = None
    image_url: str | None = None
    is_active: bool = True
