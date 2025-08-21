import uuid

from sqlmodel import Field, SQLModel

from app.api.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class GroupBase(SQLModel):
	name: str = Field(description="Group name", max_length=100)
	description: str | None = Field(default=None, max_length=255)


class GroupCreate(GroupBase, BaseCreate):
	pass


class GroupUpdate(BaseUpdate):
	name: str | None = None
	description: str | None = None


class Group(GroupBase, Base, table=True):
	__tablename__ = "groups"
	id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class GroupPublic(GroupBase, BasePublic):
	id: uuid.UUID


class GroupsPublic(SQLModel):
	data: list[GroupPublic] = Field(default_factory=list)
	count: int = Field(default=0)
