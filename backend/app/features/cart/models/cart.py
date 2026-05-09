# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class CartBase(Base):
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True,
        description="ID of the user owning the cart",
    )
    currency: str = Field(
        default="XPF",
        max_length=3,
        description="Currency used for cart amounts",
    )
    total_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Current cart total",
    )
    is_checked_out: bool = Field(
        default=False,
        description="Whether the cart has already been converted to an order",
    )


class CartCreate(CartBase, BaseCreate):
    pass


class CartUpdate(BaseUpdate):
    user_id: uuid.UUID | None = None
    currency: str | None = None
    total_amount: Decimal | None = None
    is_checked_out: bool | None = None


class Cart(CartBase, table=True):
    __tablename__ = "carts"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier of the cart",
    )


class CartPublic(CartBase, BasePublic):
    id: uuid.UUID


class CartsPublic(SQLModel):
    data: list[CartPublic] = Field(
        default_factory=list,
        description="List of carts",
    )
    count: int = Field(default=0, description="Total number of carts")


class CartItemBase(Base):
    cart_id: uuid.UUID = Field(
        foreign_key="carts.id",
        index=True,
        description="ID of the cart",
    )
    product_id: uuid.UUID = Field(
        foreign_key="products.id",
        index=True,
        description="ID of the product",
    )
    quantity: int = Field(
        ge=1,
        description="Quantity of this product in the cart",
    )
    unit_price: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Unit price snapshot in cart currency",
    )


class CartItemCreate(CartItemBase, BaseCreate):
    pass


class CartItemUpdate(BaseUpdate):
    cart_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    quantity: int | None = None
    unit_price: Decimal | None = None


class CartItem(CartItemBase, table=True):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "product_id"),)
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier of the cart item",
    )


class CartItemPublic(CartItemBase, BasePublic):
    id: uuid.UUID


class CartItemsPublic(SQLModel):
    data: list[CartItemPublic] = Field(
        default_factory=list,
        description="List of cart items",
    )
    count: int = Field(default=0, description="Total number of cart items")


class CartItemAddRequest(SQLModel):
    product_id: uuid.UUID = Field(description="ID of the product to add")
    quantity: int = Field(default=1, ge=1, description="Quantity to add")


class CartItemQuantityUpdateRequest(SQLModel):
    quantity: int = Field(ge=1, description="New quantity")


class CartItemDetail(SQLModel):
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class CartDetailPublic(SQLModel):
    id: uuid.UUID
    user_id: uuid.UUID
    currency: str
    total_amount: Decimal
    is_checked_out: bool
    items: list[CartItemDetail] = Field(default_factory=list)


class CheckoutRequest(SQLModel):
    shipping_address: str | None = Field(
        default=None,
        max_length=500,
        description="Shipping address snapshot for order creation",
    )
    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional checkout notes",
    )


class CheckoutResponse(SQLModel):
    order_id: uuid.UUID
    payment_id: uuid.UUID
    cart_id: uuid.UUID
    total_amount: Decimal
    currency: str
    item_count: int
    message: str = Field(default="Checkout completed")
