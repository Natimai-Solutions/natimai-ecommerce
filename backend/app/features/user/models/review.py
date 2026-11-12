# mypy: disable-error-code="assignment,misc,override"

import datetime
import uuid
from enum import StrEnum

from pydantic import field_validator
from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class ReviewStatus(StrEnum):
    """Moderation of a review: only an approved one is shown."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def validate_rating(v: int, field_name: str = "Rating") -> int:
    """Validate rating field."""
    if v < 1 or v > 5:
        raise ValueError(f"{field_name} must be between 1 and 5")
    return v


class ReviewBase(Base):
    """Represents review base."""

    rating: int = Field(..., ge=1, le=5, description="Rating between 1 and 5")
    comment: str | None = Field(
        default=None, max_length=1000, description="Review comment"
    )

    @field_validator("rating")
    @classmethod
    def validate_rating_field(cls, v: int) -> int:
        """Validate rating field."""
        return validate_rating(v)


class ReviewCreate(ReviewBase, BaseCreate):
    """Represents review create."""

    product_id: uuid.UUID = Field(description="ID of the product being reviewed")
    user_id: uuid.UUID = Field(description="ID of the user who created the review")


class ReviewUpdate(ReviewBase, BaseUpdate):
    """Represents review update."""

    rating: int | None = Field(
        default=None, ge=1, le=5, description="Rating between 1 and 5"
    )
    comment: str | None = Field(
        default=None, max_length=1000, description="Review comment"
    )
    product_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None

    @field_validator("rating")
    @classmethod
    def validate_rating_field(cls, v: int | None) -> int | None:
        """Validate rating field."""
        if v is not None:
            return validate_rating(v)
        return v


class Review(ReviewBase, table=True):
    """Represents review."""

    __tablename__ = "reviews"
    __table_args__ = (
        # One review per customer and product: the storefront edits it in place.
        Index(
            "ux_reviews_user_product_active",
            "user_id",
            "product_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    product_id: uuid.UUID = Field(
        foreign_key="products.id",
        nullable=False,
        index=True,
        description="ID of the product being reviewed",
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        nullable=False,
        index=True,
        description="ID of the user who created the review",
    )
    #: pending until the shop approves it; edited by its author → pending again.
    status: str = Field(
        default=ReviewStatus.PENDING.value,
        max_length=16,
        index=True,
        sa_column_kwargs={"server_default": ReviewStatus.PENDING.value},
    )
    #: The author bought the product (checked when the review is written).
    verified_purchase: bool = Field(
        default=False, sa_column_kwargs={"server_default": "false"}
    )
    #: How the author is shown (« Hina T. »), frozen when the review is written.
    author_name: str | None = Field(default=None, max_length=60)
    moderated_at: datetime.datetime | None = Field(default=None)
    moderated_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    #: Why a review was rejected (seen by the shop only).
    moderation_note: str | None = Field(default=None, max_length=300)


class ReviewPublic(ReviewBase, BasePublic):
    """Represents review public."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    product_id: uuid.UUID = Field(description="ID of the product being reviewed")
    user_id: uuid.UUID = Field(description="ID of the user who created the review")


class ReviewAnonymousPublic(SQLModel):
    """A review as anyone may read it: no user id (audit 2026-11 — the
    public list linked every review to an account id, the key of the other
    per-user routes)."""

    id: uuid.UUID
    product_id: uuid.UUID
    rating: int
    comment: str | None = None
    created_at: datetime.datetime | None = None


class ReviewsAnonymousPublic(SQLModel):
    data: list[ReviewAnonymousPublic] = Field(default_factory=list)
    count: int = 0


class ReviewsPublic(SQLModel):
    """Represents reviews public."""

    data: list[ReviewPublic] = Field(
        default_factory=list, description="List of reviews"
    )
    count: int = Field(default=0, description="Total number of reviews")
