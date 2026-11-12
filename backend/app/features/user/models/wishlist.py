# mypy: disable-error-code="assignment,misc,override"

import datetime
import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

_DEFAULT_WISHLIST_NAME = "Favorites"


class WishlistBase(Base):
    """Represents wishlist base."""

    name: str = Field(description="Name of the wishlist", max_length=100)
    description: str | None = Field(
        default=None, description="Description of the wishlist", max_length=500
    )
    is_public: bool = Field(default=False, description="Whether the wishlist is public")


class WishlistCreate(WishlistBase, BaseCreate):
    """Represents wishlist create."""

    pass


class WishlistUpdate(WishlistBase, BaseUpdate):
    """Represents wishlist update."""

    name: str | None = None
    description: str | None = None
    is_public: bool | None = None


class Wishlist(WishlistBase, table=True):
    """Represents wishlist."""

    __tablename__ = "wishlists"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        nullable=False,
        index=True,
        description="ID of the user who owns the wishlist",
    )


class WishlistPublic(WishlistBase, BasePublic):
    """Represents wishlist public."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(description="ID of the user who owns the wishlist")


class WishlistAnonymousPublic(SQLModel):
    """A public wishlist as anyone may read it: no owner id (audit 2026-11)."""

    id: uuid.UUID
    name: str
    description: str | None = None
    is_public: bool = True
    created_at: datetime.datetime | None = None


class WishlistsAnonymousPublic(SQLModel):
    data: list[WishlistAnonymousPublic] = Field(default_factory=list)
    count: int = 0


class WishlistsPublic(SQLModel):
    """Represents wishlists public."""

    data: list[WishlistPublic] = Field(
        default_factory=list, description="List of wishlists"
    )
    count: int = Field(default=0, description="Total number of wishlists")


# Wishlist Item models for the many-to-many relationship between wishlists and products
class WishlistItemBase(Base):
    """Represents wishlist item base."""

    quantity: int = Field(
        default=1, ge=1, description="Quantity of the product in wishlist"
    )
    notes: str | None = Field(
        default=None, description="Personal notes about the product", max_length=500
    )


class WishlistItemCreate(WishlistItemBase, BaseCreate):
    """Represents wishlist item create."""

    product_id: uuid.UUID = Field(description="ID of the product to add to wishlist")


class WishlistItemUpdate(WishlistItemBase, BaseUpdate):
    """Represents wishlist item update."""

    quantity: int | None = None
    notes: str | None = None


class WishlistItem(WishlistItemBase, Base, table=True):
    """Represents wishlist item."""

    __tablename__ = "wishlist_items"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    wishlist_id: uuid.UUID = Field(
        foreign_key="wishlists.id",
        nullable=False,
        index=True,
        description="ID of the wishlist",
    )
    product_id: uuid.UUID = Field(
        foreign_key="products.id",
        nullable=False,
        index=True,
        description="ID of the product",
    )


class WishlistItemPublic(WishlistItemBase, BasePublic):
    """Represents wishlist item public."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    wishlist_id: uuid.UUID = Field(description="ID of the wishlist")
    product_id: uuid.UUID = Field(description="ID of the product")


class WishlistItemsPublic(SQLModel):
    """Represents wishlist items public."""

    data: list[WishlistItemPublic] = Field(
        default_factory=list, description="List of wishlist items"
    )
    count: int = Field(default=0, description="Total number of wishlist items")


class WishlistItemAddRequest(SQLModel):
    """Represents wishlist item add request."""

    product_id: uuid.UUID = Field(
        description="ID of the product to add to the wishlist"
    )
    notes: str | None = Field(
        default=None, max_length=500, description="Optional personal notes"
    )


class WishlistItemDetail(SQLModel):
    """Represents wishlist item detail."""

    id: uuid.UUID
    product_id: uuid.UUID
    notes: str | None = None
    created_at: datetime.datetime | None = None


class WishlistDetailPublic(SQLModel):
    """Represents wishlist detail public."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None = None
    is_public: bool
    items: list[WishlistItemDetail] = Field(default_factory=list)
