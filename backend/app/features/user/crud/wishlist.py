import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.user.models.wishlist import (
    Wishlist,
    WishlistCreate,
    WishlistItem,
    WishlistItemCreate,
    WishlistItemUpdate,
    WishlistUpdate,
)


class WishlistCrud(CrudBase[Wishlist, WishlistCreate, WishlistUpdate]):
    async def get_by_user_id(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Wishlist]:
        statement = (
            select(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.is_admin_active.is_(True),
                self.model.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        exec_result = await session.exec(statement)
        return exec_result.all()

    async def get_public_wishlists(
        self, session: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> list[Wishlist]:
        statement = (
            select(self.model)
            .where(
                self.model.is_public.is_(True),
                self.model.is_admin_active.is_(True),
                self.model.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        exec_result = await session.exec(statement)
        return exec_result.all()

    async def get_user_wishlist_by_id(
        self, session: AsyncSession, *, wishlist_id: uuid.UUID, user_id: uuid.UUID
    ) -> Wishlist | None:
        statement = select(self.model).where(
            self.model.id == wishlist_id,
            self.model.user_id == user_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def create_for_user(
        self,
        session: AsyncSession,
        *,
        obj_in: WishlistCreate,
        user_id: uuid.UUID,
        current_user: uuid.UUID | None = None,
    ) -> Wishlist:
        obj_data = obj_in.model_dump()
        obj_data["user_id"] = user_id
        db_obj = self.model(**obj_data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    async def count_by_user(self, session: AsyncSession, *, user_id: uuid.UUID) -> int:
        statement = select(self.model).where(
            self.model.user_id == user_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return len(exec_result.all())


class WishlistItemCrud(CrudBase[WishlistItem, WishlistItemCreate, WishlistItemUpdate]):
    async def get_by_wishlist_id(
        self,
        session: AsyncSession,
        *,
        wishlist_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WishlistItem]:
        statement = (
            select(self.model)
            .where(
                self.model.wishlist_id == wishlist_id,
                self.model.is_admin_active.is_(True),
                self.model.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        exec_result = await session.exec(statement)
        return exec_result.all()

    async def get_by_wishlist_and_product(
        self, session: AsyncSession, *, wishlist_id: uuid.UUID, product_id: uuid.UUID
    ) -> WishlistItem | None:
        statement = select(self.model).where(
            self.model.wishlist_id == wishlist_id,
            self.model.product_id == product_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def create_for_wishlist(
        self,
        session: AsyncSession,
        *,
        obj_in: WishlistItemCreate,
        wishlist_id: uuid.UUID,
        current_user: uuid.UUID | None = None,
    ) -> WishlistItem:
        obj_data = obj_in.model_dump()
        obj_data["wishlist_id"] = wishlist_id
        db_obj = self.model(**obj_data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj

    async def count_by_wishlist(
        self, session: AsyncSession, *, wishlist_id: uuid.UUID
    ) -> int:
        statement = select(self.model).where(
            self.model.wishlist_id == wishlist_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return len(exec_result.all())


crud_wishlist = WishlistCrud(
    model=Wishlist,
    schema_create=WishlistCreate,
    schema_update=WishlistUpdate,
    order_by=Wishlist.created_at,
)

crud_wishlist_item = WishlistItemCrud(
    model=WishlistItem,
    schema_create=WishlistItemCreate,
    schema_update=WishlistItemUpdate,
    order_by=WishlistItem.created_at,
)
