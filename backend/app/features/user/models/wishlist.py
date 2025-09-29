import uuid
from datetime import datetime

from pydantic import Field as PydanticField, field_validator
from sqlmodel import Field, Relationship, SQLModel
from app.features.base.models import Base, BaseCreate, BaseUpdate, BasePublic


class WishlistBase(Base):
    name: str = Field(description="Name of the wishlist", max_length=100)
    description: str | None = Field(default=None, description="Description of the wishlist", max_length=500)
    is_public: bool = Field(default=False, description="Whether the wishlist is public")


class WishlistCreate(WishlistBase, BaseCreate):
    pass


class WishlistUpdate(WishlistBase, BaseUpdate):
    name: str | None = None
    description: str | None = None
    is_public: bool | None = None


class Wishlist(WishlistBase, Base, table=True):
    __tablename__ = "wishlists"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, index=True, description="ID of the user who owns the wishlist"
    )


class WishlistPublic(WishlistBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(description="ID of the user who owns the wishlist")


class WishlistsPublic(SQLModel):
    data: list[WishlistPublic] = Field(
        default_factory=list, description="List of wishlists"
    )
    count: int = Field(default=0, description="Total number of wishlists")


# Wishlist Item models for the many-to-many relationship between wishlists and products
class WishlistItemBase(Base):
    quantity: int = Field(default=1, ge=1, description="Quantity of the product in wishlist")
    notes: str | None = Field(default=None, description="Personal notes about the product", max_length=500)


class WishlistItemCreate(WishlistItemBase, BaseCreate):
    product_id: uuid.UUID = Field(description="ID of the product to add to wishlist")


class WishlistItemUpdate(WishlistItemBase, BaseUpdate):
    quantity: int | None = None
    notes: str | None = None


class WishlistItem(WishlistItemBase, Base, table=True):
    __tablename__ = "wishlist_items"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    wishlist_id: uuid.UUID = Field(
        foreign_key="wishlists.id", nullable=False, index=True, description="ID of the wishlist"
    )
    product_id: uuid.UUID = Field(
        foreign_key="products.id", nullable=False, index=True, description="ID of the product"
    )


class WishlistItemPublic(WishlistItemBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    wishlist_id: uuid.UUID = Field(description="ID of the wishlist")
    product_id: uuid.UUID = Field(description="ID of the product")


class WishlistItemsPublic(SQLModel):
    data: list[WishlistItemPublic] = Field(
        default_factory=list, description="List of wishlist items"
    )
    count: int = Field(default=0, description="Total number of wishlist items")
