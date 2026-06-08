import uuid
from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class UpgradeRequestStatus(str, Enum):
    pending = "PENDING"
    approved = "APPROVED"
    rejected = "REJECTED"


class GroupUpgradeRequest(SQLModel, table=True):
    """Request by a user to be moved to a specific PriceGroup requiring validation."""

    __tablename__ = "group_upgrade_requests"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    price_group_id: uuid.UUID = Field(
        foreign_key="price_groups.id", nullable=False, index=True
    )
    status: UpgradeRequestStatus = Field(
        default=UpgradeRequestStatus.pending, index=True
    )
    business_registration_number: str = Field(
        max_length=100,
        description="Numéro TAHITI or equivalent local registration identifier",
    )
    attestation_notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Free-text supporting information provided by the user",
    )
    admin_comment: str | None = Field(
        default=None,
        max_length=1000,
        description="Comment from the admin who reviewed the request",
    )
    reviewed_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    reviewed_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class GroupUpgradeRequestPublic(SQLModel):
    """API read schema."""

    id: uuid.UUID
    user_id: uuid.UUID
    price_group_id: uuid.UUID
    status: UpgradeRequestStatus
    business_registration_number: str
    attestation_notes: str | None
    admin_comment: str | None
    reviewed_by_id: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class GroupUpgradeRequestCreate(SQLModel):
    """User-facing create schema."""

    price_group_id: uuid.UUID
    business_registration_number: str = Field(max_length=100)
    attestation_notes: str | None = Field(default=None, max_length=2000)


class GroupUpgradeRequestsPublic(SQLModel):
    """Paginated list."""

    data: list[GroupUpgradeRequestPublic] = Field(default_factory=list)
    count: int = Field(default=0)
