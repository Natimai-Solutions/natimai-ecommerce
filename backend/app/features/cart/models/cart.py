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
    fx_source_currency: str | None = Field(
        default=None,
        max_length=8,
        description="Original supplier cost currency before XPF conversion",
    )
    fx_rate_used: Decimal | None = Field(
        default=None,
        decimal_places=6,
        max_digits=16,
        description="FX rate applied (1 fx_source_currency = fx_rate_used XPF). Null when cost was already in XPF.",
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


class CartReplaceRequest(SQLModel):
    """Full replacement of the cart content, applied atomically."""

    items: list[CartItemAddRequest] = Field(
        default_factory=list,
        max_length=200,
        description=(
            "The cart content to install. Every product is resolved and "
            "validated before anything is written, so the call either applies "
            "in full or changes nothing. Repeated product ids are merged by "
            "summing their quantities."
        ),
    )


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
    shipping_address_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Id of the customer's saved shipping address. When provided, the "
            "tracking is linked to this exact address (no text rematching, no "
            "duplicate creation). `shipping_address` stays as the order snapshot."
        ),
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
    payment_fee_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description=(
            "Ignored. The fee is read server-side from the selected "
            "PaymentMethod: it is a property of the method, not something the "
            "caller gets to decide. Kept optional so existing clients that "
            "still send it are not rejected."
        ),
    )
    cgv_accepted: bool = Field(
        default=False,
        description=(
            "Explicit acceptance of the terms of sale. Required: the checkbox "
            "in the SPA is not proof — the acceptance is recorded on the order "
            "(cgv_accepted_at / cgv_version) so it is opposable, and an API "
            "call that bypasses the UI is refused."
        ),
    )
    shipping_route_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description=("Ordered list of selected shipping routes for this checkout path"),
    )
    shipping_preference: CheckoutShippingPreference | None = Field(
        default=None,
        description=("Automatic selection preference when shipping_route_ids is empty"),
    )
    delivery_type: str | None = Field(
        default=None,
        max_length=50,
        description=(
            "Last-leg delivery mode tagged on a route by the admin (free-form, "
            "e.g. home_delivery / air_freight / sea_freight)"
        ),
    )
    payment_method_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Payment method to initiate in the same transaction (single-payment "
            "flow). When omitted, a pending placeholder payment is created instead."
        ),
    )
    return_url: str | None = Field(
        default=None,
        description="Return URL for provider redirect/SmartForm (CB).",
    )
    payment_plan: str | None = Field(
        default=None,
        max_length=20,
        description=(
            "« deposit » to pay a deposit now and the balance at reception, "
            "« full » (default) to pay everything now. Subject to the deposit "
            "policy of the customer's price group."
        ),
    )


class DepositTerms(SQLModel):
    """Deposit part of a quote / order (all zero on a full-payment order)."""

    payment_plan: str = Field(default="full", description="full | deposit")
    deposit_available: bool = Field(
        default=False, description="The customer's group offers a deposit"
    )
    deposit_required: bool = Field(
        default=False, description="The deposit is imposed by the group"
    )
    deposit_pct: Decimal | None = Field(default=None, description="Share paid now (%)")
    deposit_fee_amount: Decimal = Field(
        default=Decimal("0.00"), description="Fee of the deposit option (in total)"
    )
    deposit_amount: Decimal = Field(
        default=Decimal("0.00"), description="Charged now on a deposit order"
    )
    balance_amount: Decimal = Field(
        default=Decimal("0.00"), description="Asked for at reception"
    )


class CheckoutResponse(DepositTerms):
    """Represents checkout response."""

    order_id: uuid.UUID
    # Référence lisible affichée sur l'écran de confirmation. Elle est déjà
    # allouée au checkout (allocate_order_number) ; ne pas la renvoyer obligeait
    # le front à refaire un appel pour afficher le numéro de la commande.
    order_number: str | None = None
    # Départ groupé de rattachement (None hors départ) : la confirmation
    # affiche la date de clôture / livraison estimée sans second appel.
    grouped_departure_id: uuid.UUID | None = None
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
    # Provider initiation result (single-payment flow). Populated when
    # payment_method_id is supplied: CB → form_token/server_url/public_key;
    # manual/document → instructions.
    provider_code: str | None = None
    provider_reference: str | None = None
    form_token: str | None = None
    server_url: str | None = None
    public_key: str | None = None
    redirect_url: str | None = None
    instructions: str | None = None
    message: str = Field(default="Checkout completed")


class LastLegOption(SQLModel):
    """Priced last-leg (zone C) delivery option for the current cart."""

    delivery_type: str
    label: str | None = None
    amount: Decimal
    currency: str
    eta_days: int | None = None
    route_name: str | None = None


class CheckoutQuoteResponse(DepositTerms):
    """What ``POST /cart/checkout`` will bill for the current cart and choices.

    Served by ``GET /cart/me/checkout-quote`` from the very same computation
    as the checkout, so the recap the customer reads is the amount debited.
    """

    currency: str
    subtotal_amount: Decimal = Field(description="Articles, taxes incluses")
    shipping_fee_amount: Decimal = Field(
        description="Livraison (tronçon choisi) + frais de dédouanement"
    )
    customs_declaration_fee: Decimal = Field(
        default=Decimal("0.00"),
        description="Part de shipping_fee_amount due au dédouanement (0 = aucun)",
    )
    payment_fee_amount: Decimal = Field(description="Frais du moyen de paiement")
    total_fees_amount: Decimal
    total_amount: Decimal = Field(description="Montant qui sera débité")
    delivery_type: str | None = None
    shipping_eta_days: int | None = None
    free_shipping_applied: bool = Field(
        default=False, description="Le franco a mis la livraison à 0"
    )
    shipping_cost_breakdown: dict[str, Any] | None = None


class LastLegOptionsResponse(SQLModel):
    """Last-leg delivery options with their price, for the checkout selector."""

    currency: str
    options: list[LastLegOption] = Field(default_factory=list)
    customs_declaration_fee: Decimal = Field(
        default=Decimal("0.00"),
        description=(
            "Frais de dédouanement facturés une fois par expédition, quel que "
            "soit le nombre d'articles (0 = aucun frais paramétré). Ils "
            "s'ajoutent au total au checkout, en plus du mode de livraison."
        ),
    )
