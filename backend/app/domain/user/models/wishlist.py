import uuid

from sqlmodel import Field, SQLModel

from app.api.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class WishlistBase(SQLModel):
	user_id: uuid.UUID = Field(foreign_key="users.id")
	product_id: uuid.UUID = Field(foreign_key="products.id")


class WishlistCreate(WishlistBase, BaseCreate):
	pass


class WishlistUpdate(BaseUpdate):
	pass


class Wishlist(WishlistBase, Base, table=True):
	__tablename__ = "wishlists"
	id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class WishlistPublic(WishlistBase, BasePublic):
	id: uuid.UUID


class WishlistsPublic(SQLModel):
	data: list[WishlistPublic] = Field(default_factory=list)
	count: int = Field(default=0)
