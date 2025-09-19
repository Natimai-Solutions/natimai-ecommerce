import uuid

from sqlmodel import Field, Relationship, SQLModel
from app.features.base.models import Base, BaseCreate, BaseUpdate, BasePublic

from app.features.product.models.product import Product
from .user import User

class ReviewBase(Base):
    rating: int = Field(..., ge=1, le=5, description="Rating between 1 and 5")
    comment: str | None = Field(default=None, max_length=1000, description="Review comment")

class ReviewCreate(ReviewBase, BaseCreate):
    product_id: uuid.UUID = Field(..., description="ID of the product being reviewed")
    user_id: uuid.UUID = Field(..., description="ID of the user who created the review")

class ReviewUpdate(BaseUpdate):
    rating: int | None = Field(default=None, ge=1, le=5, description="Rating between 1 and 5")
    comment: str | None = Field(default=None, max_length=1000, description="Review comment")

class Review(ReviewBase, Base, table=True):
    __tablename__ = "reviews"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    product_id: uuid.UUID = Field(foreign_key="products.id", nullable=False)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    product: Product = Relationship(back_populates="reviews")
    user: User = Relationship(back_populates="reviews")

class ReviewPublic(ReviewBase, BasePublic):
    id: uuid.UUID
    product_id: uuid.UUID
    user_id: uuid.UUID

class ReviewsPublic(SQLModel):
    data: list[ReviewPublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Total number of reviews")