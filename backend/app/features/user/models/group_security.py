import uuid
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

if TYPE_CHECKING:
    from app.features.user.models.group import Group


class GroupSecurityBase(Base):
    """Base model for GroupSecurity with common fields"""

    group_id: uuid.UUID = Field(
        foreign_key="groups.id",
        index=True,
        description="Group ID this security rule applies to",
    )
    table_name: str = Field(
        max_length=100,
        index=True,
        description="Name of the database table this rule applies to",
    )
    can_read: bool = Field(
        default=True,
        description="Permission to read/view records",
    )
    can_create: bool = Field(
        default=False,
        description="Permission to create new records",
    )
    can_update: bool = Field(
        default=False,
        description="Permission to update existing records",
    )
    can_delete: bool = Field(
        default=False,
        description="Permission to delete records",
    )


class GroupSecurityCreate(GroupSecurityBase, BaseCreate):
    """Schema for creating a new group security rule"""

    pass


class GroupSecurityUpdate(BaseUpdate):
    """Schema for updating a group security rule - all fields optional"""

    group_id: uuid.UUID | None = None
    table_name: str | None = Field(default=None, max_length=100)
    can_read: bool | None = None
    can_create: bool | None = None
    can_update: bool | None = None
    can_delete: bool | None = None


class GroupSecurity(GroupSecurityBase, table=True):
    """GroupSecurity table model for managing table-level permissions"""

    __tablename__ = "group_security"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the security rule",
    )

    # Relationship
    group: "Group" = Relationship(
        back_populates="security_rules",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


class GroupSecurityPublic(GroupSecurityBase, BasePublic):
    """Public schema for group security rule exposure via API"""

    id: uuid.UUID


class GroupSecuritiesPublic(SQLModel):
    """Paginated list of group security rules"""

    data: list[GroupSecurityPublic] = Field(
        default_factory=list,
        description="List of group security rules",
    )
    count: int = Field(
        default=0,
        description="Total number of group security rules",
    )
