import uuid
from datetime import date
from decimal import Decimal
from enum import Enum

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class CurrencyRateSource(str, Enum):
    manual = "manual"
    auto = "auto"


class CurrencyRateBase(Base):
    """Represents currency rate base."""

    currency_code: str = Field(
        max_length=8,
        index=True,
        description="ISO currency code (ex: USD, EUR)",
    )
    rate_to_reference: Decimal = Field(
        gt=0,
        decimal_places=6,
        max_digits=16,
        description=(
            "Conversion rate: 1 unit of currency_code = rate_to_reference "
            "units of the reference currency"
        ),
    )
    valid_from: date = Field(description="Start date of validity")
    valid_until: date | None = Field(default=None, description="Optional end date")
    source: CurrencyRateSource = Field(
        default=CurrencyRateSource.manual,
        description="Origin of the rate (manual entry or automatic update)",
    )
    updated_by_user_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        description="Admin who last updated this rate",
    )


class CurrencyRateCreate(CurrencyRateBase, BaseCreate):
    """Represents currency rate create."""

    pass


class CurrencyRateUpdate(BaseUpdate):
    """Represents currency rate update."""

    valid_until: date | None = None


class CurrencyRate(CurrencyRateBase, table=True):
    """Represents currency rate."""

    __tablename__ = "currency_rates"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class CurrencyRatePublic(CurrencyRateBase, BasePublic):
    """Represents currency rate public."""

    id: uuid.UUID


class CurrencyRatesPublic(SQLModel):
    """Represents currency rates public."""

    data: list[CurrencyRatePublic] = Field(default_factory=list)
    count: int = Field(default=0)


class CurrencyRateUpsertRequest(SQLModel):
    """Request body for admin PUT /admin/currency-rates/{code}."""

    rate_to_reference: Decimal = Field(
        gt=0,
        decimal_places=6,
        max_digits=16,
        description="New conversion rate",
    )
    valid_from: date = Field(description="Start date for the new rate")
