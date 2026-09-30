import uuid
from datetime import date
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.core.config import settings
from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class TaxRateBase(Base):
    """Represents tax rate base."""

    code: str = Field(
        max_length=50, index=True, description="Tax code (ex: TVA_NORMALE)"
    )
    label: str = Field(max_length=120, description="Tax label")
    rate_pct: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        decimal_places=2,
        description="Tax percentage",
    )
    territory_code: str = Field(
        default_factory=lambda: settings.TAX_TERRITORY_CODE,
        max_length=8,
        index=True,
        description="Territory code where this tax applies",
    )
    valid_from: date = Field(description="Start date of validity")
    valid_until: date | None = Field(default=None, description="Optional end date")


class TaxRateCreate(TaxRateBase, BaseCreate):
    """Represents tax rate create."""

    pass


class TaxRateUpdate(BaseUpdate):
    """Represents tax rate update."""

    label: str | None = None
    valid_until: date | None = None


class TaxRate(TaxRateBase, table=True):
    """Represents tax rate."""

    __tablename__ = "tax_rates"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class TaxRatePublic(TaxRateBase, BasePublic):
    """Represents tax rate public."""

    id: uuid.UUID


class TaxRatesPublic(SQLModel):
    """Represents tax rates public."""

    data: list[TaxRatePublic] = Field(default_factory=list)
    count: int = Field(default=0)
