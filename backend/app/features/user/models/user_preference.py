import uuid

from sqlmodel import Field, SQLModel

_VALID_SHIPPING_PREFERENCES = {"fastest", "cheapest", "eco_friendly"}
_VALID_SHIPPING_MODES = {"rapide", "economique", "ecologique"}
_VALID_LOCALES = {"fr", "en"}


class UserPreferenceBase(SQLModel):
    """Shared fields for user preferences."""

    notification_email_enabled: bool = Field(
        default=True, description="Receive transactional emails (order, payment)"
    )
    notification_shipping_steps: bool = Field(
        default=True, description="Receive shipping status notifications"
    )
    default_shipping_preference: str | None = Field(
        default=None,
        description="Checkout fallback: fastest | cheapest | eco_friendly",
    )
    locale: str | None = Field(
        default=None, max_length=10, description="UI language: fr | en"
    )
    currency_pref: str | None = Field(
        default=None, max_length=10, description="Display currency: XPF | USD | EUR"
    )
    preferred_shipping_mode: str | None = Field(
        default=None,
        description="Import freight level of service: rapide | economique | ecologique",
    )


class UserPreferenceUpdate(SQLModel):
    """Update schema — all fields optional."""

    notification_email_enabled: bool | None = None
    notification_shipping_steps: bool | None = None
    default_shipping_preference: str | None = None
    locale: str | None = None
    currency_pref: str | None = None
    preferred_shipping_mode: str | None = None


class UserPreference(UserPreferenceBase, table=True):
    """Persisted user preferences — one row per user."""

    __tablename__ = "user_preferences"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        unique=True,
        index=True,
        nullable=False,
    )


class UserPreferencePublic(UserPreferenceBase):
    """API read schema."""

    user_id: uuid.UUID
