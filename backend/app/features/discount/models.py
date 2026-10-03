import datetime
import uuid
from decimal import Decimal
from enum import StrEnum

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class DiscountType(StrEnum):
    """Represents discount type."""

    COUPON = "coupon"  # Code à saisir
    PROMOTION = "promotion"  # Automatique


class DiscountTarget(StrEnum):
    """Represents discount target."""

    PRODUCT = "product"  # Produit spécifique
    CATEGORY = "category"  # Catégorie de produits
    ORDER = "order"  # Commande entière


class DiscountBase(Base):
    """Represents discount base."""

    name: str = Field(
        description="Nom de la réduction",
        max_length=100,
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description de la réduction",
    )
    discount_type: DiscountType = Field(
        description="Type de réduction (coupon ou promotion)",
    )
    code: str | None = Field(
        default=None,
        max_length=50,
        index=True,
        description="Code du coupon (uniquement pour les coupons)",
    )
    percentage: Decimal | None = Field(
        default=None,
        gt=0,
        le=100,
        max_digits=5,
        decimal_places=2,
        description="Pourcentage de réduction (0.01-100.00) — ou `amount`",
    )
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="Remise en montant fixe (devise de référence) — ou `percentage`",
    )
    min_order_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Montant minimum des articles éligibles pour appliquer la remise",
    )
    max_uses_per_customer: int | None = Field(
        default=None,
        ge=1,
        description="Utilisations maximum par client (None = illimité)",
    )
    target: DiscountTarget = Field(
        description="Cible de la réduction",
    )
    product_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="products.id",
        index=True,
        description="ID du produit ciblé (si target=PRODUCT)",
    )
    category_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="categories.id",
        index=True,
        description="ID de la catégorie ciblée (si target=CATEGORY)",
    )
    start_date: datetime.datetime | None = Field(
        default=None,
        description="Date de début de validité",
    )
    end_date: datetime.datetime | None = Field(
        default=None,
        description="Date de fin de validité",
    )
    max_uses: int | None = Field(
        default=None,
        ge=0,
        description="Nombre maximum d'utilisations (None = illimité)",
    )
    current_uses: int = Field(
        default=0,
        ge=0,
        description="Nombre d'utilisations actuelles",
    )
    applies_to_promoted: bool = Field(
        default=True,
        description=(
            "Code promo : s'applique aussi aux articles concernés par une "
            "promotion en cours (faux = ces articles sont exclus du code)"
        ),
    )


class DiscountCreate(DiscountBase, BaseCreate):
    """Represents discount create."""

    pass


class DiscountUpdate(BaseUpdate):
    """Represents discount update."""

    name: str | None = None
    description: str | None = None
    discount_type: DiscountType | None = None
    code: str | None = None
    percentage: Decimal | None = None
    amount: Decimal | None = None
    min_order_amount: Decimal | None = None
    max_uses_per_customer: int | None = None
    target: DiscountTarget | None = None
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    start_date: datetime.datetime | None = None
    end_date: datetime.datetime | None = None
    max_uses: int | None = None
    current_uses: int | None = None
    applies_to_promoted: bool | None = None


class Discount(DiscountBase, table=True):
    """Represents discount."""

    __tablename__ = "discounts"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Identifiant unique de la réduction",
    )


class DiscountPublic(DiscountBase, BasePublic):
    """Represents discount public."""

    id: uuid.UUID


class DiscountsPublic(SQLModel):
    """Represents discounts public."""

    data: list[DiscountPublic] = Field(
        default_factory=list,
        description="Liste des réductions",
    )
    count: int = Field(
        default=0,
        description="Nombre total de réductions",
    )
