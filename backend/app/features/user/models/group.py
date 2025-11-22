import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import NUMERIC
from sqlmodel import Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.user.models.user_group import UserGroup
    from app.features.user.models.group_security import GroupSecurity


class GroupBase(Base):
    """Base model for Group with common fields"""

    name: str = Field(
        max_length=100,
        unique=True,
        index=True,
        description="Unique name of the group",
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description of the group purpose",
    )
    group_type: str = Field(
        max_length=50,
        index=True,
        description="Type of group: 'security', 'pricing', 'discount', 'general'",
    )
    discount_percentage: Decimal | None = Field(
        default=None,
        sa_column=Column(NUMERIC(5, 2)),
        description="Default discount percentage for pricing groups (0.00-100.00)",
    )
    priority: int = Field(
        default=0,
        ge=0,
        description="Priority level for group evaluation (higher = more priority)",
    )


class GroupCreate(GroupBase, BaseCreate):
    """Schema for creating a new group"""

    pass


class GroupUpdate(BaseUpdate):
    """Schema for updating a group - all fields optional"""

    name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    group_type: str | None = Field(default=None, max_length=50)
    discount_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    priority: int | None = Field(default=None, ge=0)


class Group(GroupBase, table=True):
    """Group table model"""

    __tablename__ = "groups"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the group",
    )

    # Relationships
    user_groups: list["UserGroup"] = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    security_rules: list["GroupSecurity"] = Relationship(
        back_populates="group",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


class GroupPublic(GroupBase, BasePublic):
    """Public schema for group exposure via API"""

    id: uuid.UUID


class GroupsPublic(SQLModel):
    """Paginated list of groups"""

    data: list[GroupPublic] = Field(
        default_factory=list,
        description="List of groups",
    )
    count: int = Field(
        default=0,
        description="Total number of groups",
    )