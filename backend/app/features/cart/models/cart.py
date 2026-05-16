# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class CartBase(Base):
    """Represents cart base."""

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
    """Represents cart create."""

    pass


class CartUpdate(BaseUpdate):
    """Represents cart update."""

    user_id: uuid.UUID | None = None
    currency: str | None = None
    total_amount: Decimal | None = None
    is_checked_out: bool | None = None


class Cart(CartBase, table=True):
    """Represents cart."""

    __tablename__ = "carts"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier of the cart",
    )


class CartPublic(CartBase, BasePublic):
    """Represents cart public."""

    id: uuid.UUID


class CartsPublic(SQLModel):
    """Represents carts public."""

    data: list[CartPublic] = Field(
        default_factory=list,
        description="List of carts",
    )
    count: int = Field(default=0, description="Total number of carts")


class CartItemBase(Base):
    """Represents cart item base."""

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
    """Represents cart item create."""

    pass


class CartItemUpdate(BaseUpdate):
    """Represents cart item update."""

    cart_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    quantity: int | None = None
    unit_price: Decimal | None = None


class CartItem(CartItemBase, table=True):
    """Represents cart item."""

    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "product_id"),)
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier of the cart item",
    )


class CartItemPublic(CartItemBase, BasePublic):
    """Represents cart item public."""

    id: uuid.UUID


class CartItemsPublic(SQLModel):
    """Represents cart items public."""

    data: list[CartItemPublic] = Field(
        default_factory=list,
        description="List of cart items",
    )
    count: int = Field(default=0, description="Total number of cart items")


class CartItemAddRequest(SQLModel):
    """Represents cart item add request."""

    product_id: uuid.UUID = Field(description="ID of the product to add")
    quantity: int = Field(default=1, ge=1, description="Quantity to add")


class CartItemQuantityUpdateRequest(SQLModel):
    """Represents cart item quantity update request."""

    quantity: int = Field(ge=1, description="New quantity")


class CartItemDetail(SQLModel):
    """Represents cart item detail."""

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class CartDetailPublic(SQLModel):
    """Represents cart detail public."""

    id: uuid.UUID
    user_id: uuid.UUID
    currency: str
    total_amount: Decimal
    is_checked_out: bool
    items: list[CartItemDetail] = Field(default_factory=list)


class CheckoutShippingPreference(str, Enum):
    """Represents checkout shipping preference."""

    FASTEST = "fastest"
    ECO_FRIENDLY = "eco_friendly"
    CHEAPEST = "cheapest"


class CheckoutRequest(SQLModel):
    """Represents checkout request."""

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
    shipping_fee_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description=(
            "Deprecated manual shipping fee override. "
            "Used only if no shipping routes are selected"
        ),
    )
    payment_fee_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Payment fees snapshot applied at checkout",
    )
    shipping_route_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description=("Ordered list of selected shipping routes for this checkout path"),
    )
    shipping_preference: CheckoutShippingPreference | None = Field(
        default=None,
        description=("Automatic selection preference when shipping_route_ids is empty"),
    )


class CheckoutResponse(SQLModel):
    """Represents checkout response."""

    order_id: uuid.UUID
    payment_id: uuid.UUID
    cart_id: uuid.UUID
    subtotal_amount: Decimal
    shipping_fee_amount: Decimal
    payment_fee_amount: Decimal
    total_fees_amount: Decimal
    total_amount: Decimal
    currency: str
    item_count: int
    applied_shipping_route_ids: list[uuid.UUID] = Field(default_factory=list)
    shipping_eta_days: int | None = None
    shipping_carbon_footprint_kg_co2e: float | None = None
    shipping_cost_breakdown: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Snapshot detaille des couts de livraison par troncon "
            "(meme contenu que sur la commande)"
        ),
    )
    message: str = Field(default="Checkout completed")
