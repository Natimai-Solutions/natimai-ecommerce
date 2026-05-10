import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.user.models.wishlist import (
    _DEFAULT_WISHLIST_NAME,
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
                col(self.model.is_admin_active).is_(True),
                col(self.model.is_active).is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(col(self.model.created_at).desc())
        )
        exec_result = await session.exec(statement)
        return list(exec_result.all())

    async def get_public_wishlists(
        self, session: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> list[Wishlist]:
        statement = (
            select(self.model)
            .where(
                col(self.model.is_public).is_(True),
                col(self.model.is_admin_active).is_(True),
                col(self.model.is_active).is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(col(self.model.created_at).desc())
        )
        exec_result = await session.exec(statement)
        return list(exec_result.all())

    async def get_user_wishlist_by_id(
        self, session: AsyncSession, *, wishlist_id: uuid.UUID, user_id: uuid.UUID
    ) -> Wishlist | None:
        statement = select(self.model).where(
            self.model.id == wishlist_id,
            self.model.user_id == user_id,
            col(self.model.is_admin_active).is_(True),
            col(self.model.is_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def create_for_user(
        self,
        session: AsyncSession,
        *,
        data: WishlistCreate,
        user_id: uuid.UUID,
        current_user: uuid.UUID | None = None,
    ) -> Wishlist:
        obj_data = data.model_dump()
        obj_data["user_id"] = user_id
        record = self.model(**obj_data)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async def count_by_user(self, session: AsyncSession, *, user_id: uuid.UUID) -> int:
        statement = select(self.model).where(
            self.model.user_id == user_id,
            col(self.model.is_admin_active).is_(True),
            col(self.model.is_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return len(exec_result.all())

    async def get_or_create_default_for_user(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> Wishlist:
        existing = await self.get_by_user_id(
            session=session, user_id=user_id, skip=0, limit=1
        )
        if existing:
            return existing[0]

        record = self.model(
            user_id=user_id,
            name=_DEFAULT_WISHLIST_NAME,
            description=None,
            is_public=False,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record


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
                col(self.model.is_admin_active).is_(True),
                col(self.model.is_active).is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(col(self.model.created_at).desc())
        )
        exec_result = await session.exec(statement)
        return list(exec_result.all())

    async def get_by_wishlist_and_product(
        self, session: AsyncSession, *, wishlist_id: uuid.UUID, product_id: uuid.UUID
    ) -> WishlistItem | None:
        statement = select(self.model).where(
            self.model.wishlist_id == wishlist_id,
            self.model.product_id == product_id,
            col(self.model.is_admin_active).is_(True),
            col(self.model.is_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def create_for_wishlist(
        self,
        session: AsyncSession,
        *,
        data: WishlistItemCreate,
        wishlist_id: uuid.UUID,
        current_user: uuid.UUID | None = None,
    ) -> WishlistItem:
        obj_data = data.model_dump()
        obj_data["wishlist_id"] = wishlist_id
        record = self.model(**obj_data)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async def count_by_wishlist(
        self, session: AsyncSession, *, wishlist_id: uuid.UUID
    ) -> int:
        statement = select(self.model).where(
            self.model.wishlist_id == wishlist_id,
            col(self.model.is_admin_active).is_(True),
            col(self.model.is_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return len(exec_result.all())

    async def add_product(
        self,
        session: AsyncSession,
        *,
        wishlist_id: uuid.UUID,
        product_id: uuid.UUID,
        notes: str | None = None,
    ) -> WishlistItem:
        existing = await self.get_by_wishlist_and_product(
            session=session, wishlist_id=wishlist_id, product_id=product_id
        )
        if existing is not None:
            return existing

        record = self.model(
            wishlist_id=wishlist_id,
            product_id=product_id,
            quantity=1,
            notes=notes,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record

    async def deactivate_by_wishlist_and_product(
        self,
        session: AsyncSession,
        *,
        wishlist_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> bool:
        item = await self.get_by_wishlist_and_product(
            session=session, wishlist_id=wishlist_id, product_id=product_id
        )
        if item is None:
            return False

        item.is_active = False
        session.add(item)
        await session.commit()
        return True


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
