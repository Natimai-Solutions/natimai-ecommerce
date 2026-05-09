import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import (
    Cart,
    CartDetailPublic,
    CartItem,
    CartItemAddRequest,
    CartItemDetail,
    CartItemQuantityUpdateRequest,
    CheckoutRequest,
    CheckoutResponse,
)
from app.features.inventory.crud import crud_inventory, crud_stock_movement
from app.features.inventory.models.stock_movement import (
    InventoryStockMovementCreate,
    MovementStatus,
    MovementType,
    ReferenceType,
)
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.order.models.order import OrderCreate
from app.features.order.models.order_line import OrderLineCreate
from app.features.order.models.order_status import OrderStatus, OrderStatusCreate
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import PaymentCreate
from app.features.payment.models.payment_status import (
    PaymentStatus,
    PaymentStatusCreate,
)
from app.features.product.models.product import Product
from app.features.user.models.user import User
from app.utils.money import quantize_amount

_PENDING_ORDER_STATUS = "Pending"
_PENDING_PAYMENT_STATUS = "Pending"


def _snapshot_checkout_amounts(
    *,
    items: list[CartItem],
    currency: str,
    shipping_fee_amount: Decimal,
    payment_fee_amount: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    subtotal_amount = sum(
        (item.unit_price * item.quantity for item in items),
        Decimal("0.00"),
    )
    subtotal_amount = quantize_amount(subtotal_amount, currency)

    shipping_fee = quantize_amount(shipping_fee_amount, currency)
    payment_fee = quantize_amount(payment_fee_amount, currency)
    total_fees_amount = quantize_amount(shipping_fee + payment_fee, currency)
    total_amount = quantize_amount(subtotal_amount + total_fees_amount, currency)

    return (
        subtotal_amount,
        shipping_fee,
        payment_fee,
        total_fees_amount,
        total_amount,
    )


async def _get_or_create_order_pending_status(session: SessionDep) -> OrderStatus:
    status_record = await crud_order_status.get_by_name(
        session,
        name=_PENDING_ORDER_STATUS,
    )
    if status_record is not None:
        return status_record

    return await crud_order_status.create_draft(
        session=session,
        data=OrderStatusCreate(name=_PENDING_ORDER_STATUS),
        user=None,
    )


async def _get_or_create_payment_pending_status(
    session: SessionDep,
) -> PaymentStatus:
    status_record = await crud_payment_status.get_by_name(
        session,
        name=_PENDING_PAYMENT_STATUS,
    )
    if status_record is not None:
        return status_record

    return await crud_payment_status.create_draft(
        session=session,
        data=PaymentStatusCreate(
            name=_PENDING_PAYMENT_STATUS,
            description="Payment created at checkout and awaiting processing",
        ),
        user=None,
    )


async def _reserve_stock_for_checkout(
    session: SessionDep,
    *,
    order_id: uuid.UUID,
    product: Product,
    quantity: int,
    current_user: User,
) -> None:
    quantity_decimal = Decimal(quantity)
    inventory = await crud_inventory.get_by_product_and_place(
        session=session,
        product_id=product.id,
        place_id=None,
    )

    if inventory is not None:
        if inventory.quantity < quantity_decimal:
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient stock for product {product.id}",
            )

        inventory.quantity -= quantity_decimal
        session.add(inventory)

        await crud_stock_movement.create_draft(
            session=session,
            data=InventoryStockMovementCreate(
                movement_type=MovementType.OUTGOING.value,
                reference_type=ReferenceType.ORDER.value,
                reference_id=order_id,
                from_place_id=inventory.place_id,
                to_place_id=None,
                product_id=product.id,
                quantity=quantity_decimal,
                unit_cost=product.base_price,
                reason="Stock reserved during checkout",
                status=MovementStatus.PENDING.value,
            ),
            user=current_user,
        )
        return

    if product.is_supplier_managed:
        if product.supplier_quantity < quantity_decimal:
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient supplier stock for product {product.id}",
            )

        product.supplier_quantity -= quantity_decimal
        session.add(product)

        await crud_stock_movement.create_draft(
            session=session,
            data=InventoryStockMovementCreate(
                movement_type=MovementType.OUTGOING.value,
                reference_type=ReferenceType.ORDER.value,
                reference_id=order_id,
                from_place_id=None,
                to_place_id=None,
                product_id=product.id,
                quantity=quantity_decimal,
                unit_cost=product.base_price,
                reason="Supplier stock reserved during checkout",
                status=MovementStatus.PENDING.value,
            ),
            user=current_user,
        )
        return

    raise HTTPException(
        status_code=409,
        detail=f"No reservable stock found for product {product.id}",
    )

router = APIRouter(prefix="/cart", tags=["cart"])


def _build_cart_detail(cart: Cart, items: list[CartItem]) -> CartDetailPublic:
    item_details = [
        CartItemDetail(
            id=item.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_total=quantize_amount(item.unit_price * item.quantity, cart.currency),
        )
        for item in items
    ]

    return CartDetailPublic(
        id=cart.id,
        user_id=cart.user_id,
        currency=cart.currency,
        total_amount=cart.total_amount,
        is_checked_out=cart.is_checked_out,
        items=item_details,
    )


async def _get_active_product_or_404(
    session: SessionDep,
    *,
    product_id: uuid.UUID,
) -> Product:
    product = await session.get(Product, product_id)
    if product is None or not product.is_active or not product.is_admin_active:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/me", response_model=CartDetailPublic)
async def get_my_cart(
    session: SessionDep,
    current_user: CurrentUser,
) -> CartDetailPublic:
    cart = await crud_cart.get_or_create_active_cart(
        session=session,
        user_id=current_user.id,
    )
    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    return _build_cart_detail(cart, items)


@router.post(
    "/items",
    response_model=CartDetailPublic,
    status_code=status.HTTP_201_CREATED,
)
async def add_cart_item(
    session: SessionDep,
    current_user: CurrentUser,
    payload: CartItemAddRequest,
) -> CartDetailPublic:
    cart = await crud_cart.get_or_create_active_cart(
        session=session,
        user_id=current_user.id,
    )
    product = await _get_active_product_or_404(session, product_id=payload.product_id)

    await crud_cart_item.add_or_increment(
        session=session,
        cart_id=cart.id,
        product=product,
        quantity=payload.quantity,
    )
    await crud_cart.sync_total(session=session, cart_id=cart.id)
    await session.refresh(cart)

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    return _build_cart_detail(cart, items)


@router.patch("/items/{item_id}", response_model=CartDetailPublic)
async def update_cart_item_quantity(
    session: SessionDep,
    current_user: CurrentUser,
    item_id: uuid.UUID,
    payload: CartItemQuantityUpdateRequest,
) -> CartDetailPublic:
    item = await crud_cart_item.get_active_item_for_user(
        session=session,
        item_id=item_id,
        user_id=current_user.id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found")

    await crud_cart_item.update_quantity(
        session=session,
        item=item,
        quantity=payload.quantity,
    )
    await crud_cart.sync_total(session=session, cart_id=item.cart_id)

    cart = await session.get(Cart, item.cart_id)
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found")

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    return _build_cart_detail(cart, items)


@router.delete("/items/{item_id}", response_model=CartDetailPublic)
async def remove_cart_item(
    session: SessionDep,
    current_user: CurrentUser,
    item_id: uuid.UUID,
) -> CartDetailPublic:
    item = await crud_cart_item.get_active_item_for_user(
        session=session,
        item_id=item_id,
        user_id=current_user.id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found")

    await crud_cart_item.deactivate_item(session=session, item=item)
    await crud_cart.sync_total(session=session, cart_id=item.cart_id)

    cart = await session.get(Cart, item.cart_id)
    if cart is None:
        raise HTTPException(status_code=404, detail="Cart not found")

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    return _build_cart_detail(cart, items)


@router.delete("/items", response_model=CartDetailPublic)
async def clear_my_cart(
    session: SessionDep,
    current_user: CurrentUser,
) -> CartDetailPublic:
    cart = await crud_cart.get_or_create_active_cart(
        session=session,
        user_id=current_user.id,
    )

    await crud_cart_item.clear_cart(session=session, cart_id=cart.id)
    await crud_cart.sync_total(session=session, cart_id=cart.id)
    await session.refresh(cart)

    return _build_cart_detail(cart, [])


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def checkout_my_cart(
    session: SessionDep,
    current_user: CurrentUser,
    payload: CheckoutRequest,
) -> CheckoutResponse:
    cart = await crud_cart.get_active_cart_by_user(
        session=session,
        user_id=current_user.id,
    )
    if cart is None:
        raise HTTPException(status_code=400, detail="No active cart found")

    items = await crud_cart_item.get_by_cart_id(session=session, cart_id=cart.id)
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    (
        subtotal_amount,
        shipping_fee_amount,
        payment_fee_amount,
        total_fees_amount,
        total_amount,
    ) = _snapshot_checkout_amounts(
        items=items,
        currency=cart.currency,
        shipping_fee_amount=payload.shipping_fee_amount,
        payment_fee_amount=payload.payment_fee_amount,
    )
    if total_amount <= 0:
        raise HTTPException(status_code=400, detail="Cart total must be > 0")

    try:
        order_status = await _get_or_create_order_pending_status(session)
        order = await crud_order.create_draft(
            session=session,
            data=OrderCreate(
                user_id=current_user.id,
                order_status_id=order_status.id,
                total_amount=total_amount,
                subtotal_amount=subtotal_amount,
                shipping_fee_amount=shipping_fee_amount,
                payment_fee_amount=payment_fee_amount,
                total_fees_amount=total_fees_amount,
                shipping_address=payload.shipping_address,
                notes=payload.notes,
            ),
            user=current_user,
        )

        for item in items:
            product = await _get_active_product_or_404(
                session,
                product_id=item.product_id,
            )

            await _reserve_stock_for_checkout(
                session=session,
                order_id=order.id,
                product=product,
                quantity=item.quantity,
                current_user=current_user,
            )

            await crud_order_line.create_draft(
                session=session,
                data=OrderLineCreate(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    discount_amount=Decimal("0.00"),
                    notes=None,
                ),
                user=current_user,
            )

        payment_status = await _get_or_create_payment_pending_status(session)
        payment = await crud_payment.create_draft(
            session=session,
            data=PaymentCreate(
                amount=total_amount,
                currency=cart.currency,
                order_id=order.id,
                user_id=current_user.id,
            ),
            user=current_user,
        )
        payment.payment_status_id = payment_status.id
        session.add(payment)

        cart.is_checked_out = True
        cart.total_amount = total_amount
        session.add(cart)

        for item in items:
            item.is_active = False
            session.add(item)

        await session.commit()

        await session.refresh(order)
        await session.refresh(payment)
        await session.refresh(cart)

        return CheckoutResponse(
            order_id=order.id,
            payment_id=payment.id,
            cart_id=cart.id,
            subtotal_amount=subtotal_amount,
            shipping_fee_amount=shipping_fee_amount,
            payment_fee_amount=payment_fee_amount,
            total_fees_amount=total_fees_amount,
            total_amount=total_amount,
            currency=cart.currency,
            item_count=len(items),
            message="Checkout completed",
        )

    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=500, detail="Checkout failed") from exc
