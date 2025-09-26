import uuid

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BaseUpdate, BasePublic


def validate_rating(v: int, field_name: str = "Rating") -> int:
    """Validate rating field."""
    if v < 1 or v > 5:
        raise ValueError(f"{field_name} must be between 1 and 5")
    return v


class ReviewBase(Base):
    rating: int = Field(ge=1, le=5, description="Rating between 1 and 5")
    comment: str | None = Field(default=None, max_length=1000, description="Review comment")

    @field_validator('rating')
    @classmethod
    def validate_rating_field(cls, v: int) -> int:
        return validate_rating(v)


class ReviewCreate(ReviewBase, BaseCreate):
    product_id: uuid.UUID = Field(description="ID of the product being reviewed")
    user_id: uuid.UUID = Field(description="ID of the user who created the review")

      
class ReviewUpdate(ReviewBase, BaseUpdate):
    rating: int | None = Field(default=None, ge=1, le=5, description="Rating between 1 and 5")
    comment: str | None = Field(default=None, max_length=1000, description="Review comment")
    product_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None

    @field_validator('rating')
    @classmethod
    def validate_rating_field(cls, v: int | None) -> int | None:
        if v is not None:
            return validate_rating(v)
        return v

class Review(ReviewBase, Base, table=True):
    __tablename__ = "reviews"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    product_id: uuid.UUID = Field(
        foreign_key="products.id", nullable=False, index=True, description="ID of the product being reviewed"
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id", nullable=False, index=True, description="ID of the user who created the review"
    )



class ReviewPublic(ReviewBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    product_id: uuid.UUID = Field(description="ID of the product being reviewed")
    user_id: uuid.UUID = Field(description="ID of the user who created the review")



class ReviewsPublic(SQLModel):
    data: list[ReviewPublic] = Field(
        default_factory=list, description="List of reviews"
    )
    count: int = Field(default=0, description="Total number of reviews")
