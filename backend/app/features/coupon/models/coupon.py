import datetime
import uuid
from enum import Enum

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class DiscountType(str, Enum):
    """Type de réduction"""

    COUPON = "coupon"  # Code à saisir
    PROMOTION = "promotion"  # Automatique


class DiscountTarget(str, Enum):
    """Cible de la réduction"""

    PRODUCT = "product"  # Produit spécifique
    CATEGORY = "category"  # Catégorie de produits
    ORDER = "order"  # Commande entière


class DiscountBase(Base):
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
    percentage: float = Field(
        gt=0,
        le=100,
        description="Pourcentage de réduction (1-100)",
    )
    target: DiscountTarget = Field(
        description="Cible de la réduction",
    )
    product_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="products.id",
        description="ID du produit ciblé (si target=PRODUCT)",
    )
    category_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="categories.id",
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


class DiscountCreate(DiscountBase, BaseCreate):
    pass


class DiscountUpdate(BaseUpdate):
    name: str | None = None
    description: str | None = None
    discount_type: DiscountType | None = None
    code: str | None = None
    percentage: float | None = None
    target: DiscountTarget | None = None
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    start_date: datetime.datetime | None = None
    end_date: datetime.datetime | None = None
    max_uses: int | None = None
    current_uses: int | None = None


class Discount(DiscountBase, Base, table=True):
    __tablename__ = "discounts"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Identifiant unique de la réduction",
    )


class DiscountPublic(DiscountBase, BasePublic):
    id: uuid.UUID


class DiscountsPublic(SQLModel):
    data: list[DiscountPublic] = Field(
        default_factory=list,
        description="Liste des réductions",
    )
    count: int = Field(
        default=0,
        description="Nombre total de réductions",
    )
