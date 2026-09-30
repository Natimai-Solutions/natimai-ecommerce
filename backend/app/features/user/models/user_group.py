import datetime
import uuid
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.features.user.models.group import Group
    from app.features.user.models.user import User


class UserGroupBase(SQLModel):
    """Base model for UserGroup association"""

    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        primary_key=True,
        index=True,
        description="User ID",
    )
    group_id: uuid.UUID = Field(
        foreign_key="groups.id",
        primary_key=True,
        index=True,
        description="Group ID",
    )
    joined_at: datetime.datetime | None = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc),
        description="Timestamp when user joined the group",
    )


class UserGroupCreate(SQLModel):
    """Schema for adding a user to a group"""

    user_id: uuid.UUID
    group_id: uuid.UUID


class UserGroup(UserGroupBase, table=True):
    """Association table for many-to-many relationship between Users and Groups"""

    __tablename__ = "user_groups"

    # Relationships
    user: "User" = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    group: "Group" = Relationship(
        back_populates="user_groups",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


class UserGroupPublic(UserGroupBase):
    """Public schema for user-group association"""

    pass


class UserGroupsPublic(SQLModel):
    """List of user-group associations"""

    data: list[UserGroupPublic] = Field(
        default_factory=list,
        description="List of user-group associations",
    )
    count: int = Field(
        default=0,
        description="Total number of associations",
    )
