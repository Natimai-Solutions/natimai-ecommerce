import uuid
from decimal import Decimal
from enum import Enum

from sqlmodel import Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate
from app.features.product.models.category import Category

class BrandProductBase(Base):
    name: str = Field(
        description="Name of the brand",
        max_length=100,
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description of the brand",
    )
    image_url: str | None = Field(
        default=None,
        max_length=500,
        description="URL of the brand image",
    )