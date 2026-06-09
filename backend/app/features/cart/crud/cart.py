# mypy: disable-error-code="arg-type,assignment"

import uuid
from decimal import Decimal

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.base.crud import CrudBase, RecordNotFoundError
from app.features.cart.models.cart import (
    Cart,
    CartCreate,
    CartItem,
    CartItemCreate,
    CartItemUpdate,
    CartUpdate,
)
from app.features.product.models.product import Product
from app.features.product.services.pricing import (
    CurrencyRateMissing,
    convert_to_reference_currency,
)
from app.utils.money import quantize_amount


class CartCrud(CrudBase[Cart, CartCreate, CartUpdate]):
    """Represents cart crud."""

    async def get_active_cart_by_user(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> Cart | None:
        """Get active cart by user."""
        statement = (
            select(self.model)
            .where(
                self.model.user_id == user_id,
                col(self.model.is_checked_out).is_(False),
                col(self.model.is_active).is_(True),
                col(self.model.is_admin_active).is_(True),
            )
            .order_by(col(self.model.created_at).desc())
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def get_or_create_active_cart(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        currency: str = "XPF",
    ) -> Cart:
        """Get or create active cart."""
        cart = await self.get_active_cart_by_user(session, user_id=user_id)
        if cart is not None:
            return cart

        cart = self.model(
            user_id=user_id,
            currency=currency,
            total_amount=Decimal("0.00"),
            is_checked_out=False,
        )
        session.add(cart)
        await session.commit()
        await session.refresh(cart)
        return cart

    async def sync_total(
        self,
        session: AsyncSession,
        *,
        cart_id: uuid.UUID,
    ) -> Decimal:
        """Synchronize total."""
        cart = await session.get(self.model, cart_id)
        if (
            cart is None
            or not cart.is_active
            or not cart.is_admin_active
            or cart.is_checked_out
        ):
            raise RecordNotFoundError("Active cart not found")

        statement = select(CartItem).where(
            CartItem.cart_id == cart_id,
            col(CartItem.is_active).is_(True),
            col(CartItem.is_admin_active).is_(True),
        )
        exec_result = await session.exec(statement)
        items = list(exec_result.all())

        total = sum(
            (item.unit_price * item.quantity for item in items),
            Decimal("0.00"),
        )
        cart.total_amount = quantize_amount(total, cart.currency)

        session.add(cart)
        await session.commit()
        await session.refresh(cart)

        return cart.total_amount


class CartItemCrud(CrudBase[CartItem, CartItemCreate, CartItemUpdate]):
    """Represents cart item crud."""

    async def get_by_cart_id(
        self,
        session: AsyncSession,
        *,
        cart_id: uuid.UUID,
    ) -> list[CartItem]:
        """Get by cart id."""
        statement = (
            select(self.model)
            .where(
                self.model.cart_id == cart_id,
                col(self.model.is_active).is_(True),
                col(self.model.is_admin_active).is_(True),
            )
            .order_by(col(self.model.created_at).desc())
        )
        exec_result = await session.exec(statement)
        return list(exec_result.all())

    async def get_by_cart_and_product(
        self,
        session: AsyncSession,
        *,
        cart_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> CartItem | None:
        """Get by cart and product."""
        statement = select(self.model).where(
            self.model.cart_id == cart_id,
            self.model.product_id == product_id,
            col(self.model.is_active).is_(True),
            col(self.model.is_admin_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def get_active_item_for_user(
        self,
        session: AsyncSession,
        *,
        item_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> CartItem | None:
        """Get active item for user."""
        statement = (
            select(self.model)
            .join(Cart, Cart.id == self.model.cart_id)
            .where(
                self.model.id == item_id,
                Cart.user_id == user_id,
                col(Cart.is_checked_out).is_(False),
                col(Cart.is_active).is_(True),
                col(Cart.is_admin_active).is_(True),
                col(self.model.is_active).is_(True),
                col(self.model.is_admin_active).is_(True),
            )
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def add_or_increment(
        self,
        session: AsyncSession,
        *,
        cart_id: uuid.UUID,
        product: Product,
        quantity: int,
    ) -> CartItem:
        """Execute add or increment."""
        cost_currency = (
            getattr(product, "cost_currency", None) or settings.REFERENCE_CURRENCY
        )
        fx_rate_used: Decimal | None = None
        fx_source_currency: str | None = None
        try:
            _, rate = await convert_to_reference_currency(
                session, Decimal("1"), cost_currency
            )
            if cost_currency != settings.REFERENCE_CURRENCY:
                fx_rate_used = rate
                fx_source_currency = cost_currency
        except CurrencyRateMissing:
            pass  # FX snapshot left null; does not block adding to cart

        existing_item = await self.get_by_cart_and_product(
            session=session,
            cart_id=cart_id,
            product_id=product.id,
        )

        if existing_item is not None:
            existing_item.quantity += quantity
            existing_item.unit_price = product.base_price
            existing_item.fx_rate_used = fx_rate_used
            existing_item.fx_source_currency = fx_source_currency
            session.add(existing_item)
            await session.commit()
            await session.refresh(existing_item)
            return existing_item

        item = self.model(
            cart_id=cart_id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.base_price,
            fx_rate_used=fx_rate_used,
            fx_source_currency=fx_source_currency,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item

    async def update_quantity(
        self,
        session: AsyncSession,
        *,
        item: CartItem,
        quantity: int,
    ) -> CartItem:
        """Update quantity."""
        item.quantity = quantity
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item

    async def deactivate_item(
        self,
        session: AsyncSession,
        *,
        item: CartItem,
    ) -> None:
        """Execute deactivate item."""
        item.is_active = False
        session.add(item)
        await session.commit()

    async def clear_cart(
        self,
        session: AsyncSession,
        *,
        cart_id: uuid.UUID,
    ) -> int:
        """Execute clear cart."""
        items = await self.get_by_cart_id(session=session, cart_id=cart_id)
        for item in items:
            item.is_active = False
            session.add(item)

        await session.commit()
        return len(items)


crud_cart = CartCrud(
    model=Cart,
    schema_create=CartCreate,
    schema_update=CartUpdate,
    order_by=col(Cart.created_at).desc(),
)

crud_cart_item = CartItemCrud(
    model=CartItem,
    schema_create=CartItemCreate,
    schema_update=CartItemUpdate,
    order_by=col(CartItem.created_at).desc(),
)
