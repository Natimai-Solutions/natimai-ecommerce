import uuid
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PriceGroupBase(Base):
    """Represents price group base."""

    code: str = Field(
        max_length=50, index=True, description="Unique pricing group code"
    )
    label: str = Field(max_length=100, description="Display label for pricing group")
    margin_rate_pct: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        decimal_places=2,
        description="Margin percentage applied for this group",
    )
    discount_pct: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        lt=100,
        max_digits=5,
        decimal_places=2,
        description=(
            "Remise du groupe en % du prix de référence (tous les articles, "
            "prix calculés comme prix fixés) ; un prix saisi pour le groupe sur "
            "l'article passe avant"
        ),
    )
    default: bool = Field(
        default=False,
        index=True,
        description="Whether this group is the default fallback",
    )
    requires_validation: bool = Field(
        default=False,
        description="Whether assignment to this group requires admin validation",
    )
    # Deposit policy (« acompte à la commande ») for the customers of the
    # group: a share of the total paid at checkout, the balance once the goods
    # are received. Null percentage = the option is not offered.
    deposit_pct: Decimal | None = Field(
        default=None,
        ge=1,
        le=99,
        max_digits=5,
        decimal_places=2,
        description="Part du total versée à la commande (%) ; null = pas d'acompte",
    )
    deposit_fee_pct: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=5,
        decimal_places=2,
        description="Frais liés à l'option acompte, en % du total",
    )
    deposit_fee_fixed: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Frais fixes liés à l'option acompte (devise de référence)",
    )
    deposit_required: bool = Field(
        default=False,
        description="L'acompte est imposé (sinon au choix du client)",
    )


class PriceGroupCreate(PriceGroupBase, BaseCreate):
    """Represents price group create."""

    pass


class PriceGroupUpdate(BaseUpdate):
    """Represents price group update."""

    code: str | None = None
    label: str | None = None
    margin_rate_pct: Decimal | None = None
    discount_pct: Decimal | None = Field(default=None, ge=0, lt=100)
    default: bool | None = None
    requires_validation: bool | None = None
    deposit_pct: Decimal | None = None
    deposit_fee_pct: Decimal | None = None
    deposit_fee_fixed: Decimal | None = None
    deposit_required: bool | None = None


class PriceGroup(PriceGroupBase, table=True):
    """Represents price group."""

    __tablename__ = "price_groups"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class PriceGroupPublic(PriceGroupBase, BasePublic):
    """Represents price group public."""

    id: uuid.UUID


class PriceGroupsPublic(SQLModel):
    """Represents price groups public."""

    data: list[PriceGroupPublic] = Field(default_factory=list)
    count: int = Field(default=0)
