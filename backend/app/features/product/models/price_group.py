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
    default: bool = Field(
        default=False,
        index=True,
        description="Whether this group is the default fallback",
    )
    requires_validation: bool = Field(
        default=False,
        description="Whether assignment to this group requires admin validation",
    )


class PriceGroupCreate(PriceGroupBase, BaseCreate):
    """Represents price group create."""

    pass


class PriceGroupUpdate(BaseUpdate):
    """Represents price group update."""

    code: str | None = None
    label: str | None = None
    margin_rate_pct: Decimal | None = None
    default: bool | None = None
    requires_validation: bool | None = None


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
