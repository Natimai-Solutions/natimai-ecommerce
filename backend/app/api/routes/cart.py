import uuid

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
)
from app.features.product.models.product import Product
from app.utils.money import quantize_amount

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
