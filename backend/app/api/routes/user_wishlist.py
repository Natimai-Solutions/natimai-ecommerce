import uuid

from fastapi import Query, status

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep
from app.core.errors import AppError
from app.features.product.models.product import Product
from app.features.user.crud.wishlist import (
    WishlistCrud,
    crud_wishlist,
    crud_wishlist_item,
)
from app.features.user.models.wishlist import (
    Wishlist,
    WishlistAnonymousPublic,
    WishlistCreate,
    WishlistDetailPublic,
    WishlistItem,
    WishlistItemAddRequest,
    WishlistItemDetail,
    WishlistPublic,
    WishlistsAnonymousPublic,
    WishlistsPublic,
    WishlistUpdate,
)


def _check_permission(
    current_user_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False
) -> bool:
    """Check if current user can access resource for given user_id."""
    return current_user_id == user_id or is_admin


class WishlistRouter(
    BaseRouter[
        Wishlist,
        WishlistCreate,
        WishlistUpdate,
        WishlistPublic,
        WishlistsPublic,
        WishlistCrud,
    ]
):
    """Represents wishlist router."""

    pass


class Auth:
    """Represents auth."""

    read = False  # No auth required for public endpoints
    create = True
    update = True
    delete = True


router = WishlistRouter(
    name="wishlist",
    tags=["wishlist"],
    crud=crud_wishlist,
    schema_public=WishlistPublic,
    schema_publics=WishlistsPublic,
    schema_create=WishlistCreate,
    schema_update=WishlistUpdate,
    auth=Auth(),
    auto=False,
)


def _build_wishlist_detail(
    wishlist: Wishlist,
    items: list[WishlistItem],
) -> WishlistDetailPublic:
    """Build wishlist detail."""
    return WishlistDetailPublic(
        id=wishlist.id,
        user_id=wishlist.user_id,
        name=wishlist.name,
        description=wishlist.description,
        is_public=wishlist.is_public,
        items=[
            WishlistItemDetail(
                id=item.id,
                product_id=item.product_id,
                notes=item.notes,
                created_at=item.created_at,
            )
            for item in items
        ],
    )


async def _get_active_product_or_404(
    session: SessionDep, *, product_id: uuid.UUID
) -> Product:
    """Get active product or 404."""
    product = await session.get(Product, product_id)
    if product is None or not product.is_active or not product.is_admin_active:
        raise AppError(
            code="wishlist.product.not_found",
            status_code=404,
            message=f"Product '{product_id}' not found",
            details={"product_id": str(product_id)},
        )
    return product


@router.get("/me", response_model=WishlistDetailPublic)
async def get_my_wishlist(
    session: SessionDep,
    current_user: CurrentUser,
) -> WishlistDetailPublic:
    """Get the authenticated user's default wishlist with its items."""
    wishlist = await crud_wishlist.get_or_create_default_for_user(
        session=session, user_id=current_user.id
    )
    items = await crud_wishlist_item.get_by_wishlist_id(
        session=session, wishlist_id=wishlist.id
    )
    return _build_wishlist_detail(wishlist, items)


@router.post(
    "/me/items",
    response_model=WishlistDetailPublic,
    status_code=status.HTTP_201_CREATED,
)
async def add_product_to_my_wishlist(
    session: SessionDep,
    current_user: CurrentUser,
    payload: WishlistItemAddRequest,
) -> WishlistDetailPublic:
    """Add a product to the authenticated user's default wishlist (idempotent)."""
    await _get_active_product_or_404(session, product_id=payload.product_id)

    wishlist = await crud_wishlist.get_or_create_default_for_user(
        session=session, user_id=current_user.id
    )
    await crud_wishlist_item.add_product(
        session=session,
        wishlist_id=wishlist.id,
        product_id=payload.product_id,
        notes=payload.notes,
    )

    items = await crud_wishlist_item.get_by_wishlist_id(
        session=session, wishlist_id=wishlist.id
    )
    return _build_wishlist_detail(wishlist, items)


@router.delete("/me/items/{product_id}", response_model=WishlistDetailPublic)
async def remove_product_from_my_wishlist(
    session: SessionDep,
    current_user: CurrentUser,
    product_id: uuid.UUID,
) -> WishlistDetailPublic:
    """Remove a product from the authenticated user's default wishlist."""
    wishlist = await crud_wishlist.get_or_create_default_for_user(
        session=session, user_id=current_user.id
    )
    removed = await crud_wishlist_item.deactivate_by_wishlist_and_product(
        session=session,
        wishlist_id=wishlist.id,
        product_id=product_id,
    )
    if not removed:
        raise AppError(
            code="wishlist.product.not_in_wishlist",
            status_code=404,
            message=f"Product '{product_id}' not found in wishlist",
            details={
                "product_id": str(product_id),
                "wishlist_id": str(wishlist.id),
            },
        )

    items = await crud_wishlist_item.get_by_wishlist_id(
        session=session, wishlist_id=wishlist.id
    )
    return _build_wishlist_detail(wishlist, items)


# User-specific wishlist routes (méthode simple)
@router.get("/users/{user_id}/wishlists", response_model=WishlistsPublic)
async def get_user_wishlists(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    skip: int = Query(default=0, ge=0, description="Number of wishlists to skip"),
    limit: int = Query(
        default=100, le=100, ge=1, description="Number of wishlists to return"
    ),
) -> WishlistsPublic:
    """Get all wishlists for a specific user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise AppError(
            code="wishlist.not_found",
            status_code=404,
            message="Liste introuvable",
            details={"user_id": str(user_id)},
        )

    wishlists = await crud_wishlist.get_by_user_id(
        session=session, user_id=user_id, skip=skip, limit=limit
    )
    count = await crud_wishlist.count_by_user(session=session, user_id=user_id)
    return WishlistsPublic(
        data=[WishlistPublic.model_validate(w) for w in wishlists], count=count
    )


@router.post(
    "/users/{user_id}/wishlists",
    response_model=WishlistPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_wishlist(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    wishlist_in: WishlistCreate,
) -> WishlistPublic:
    """Create a new wishlist for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise AppError(
            code="wishlist.not_found",
            status_code=404,
            message="Liste introuvable",
            details={"user_id": str(user_id)},
        )

    wishlist = await crud_wishlist.create_for_user(
        session=session,
        data=wishlist_in,
        user_id=user_id,
        current_user=current_user.id,
    )
    return WishlistPublic.model_validate(wishlist)


@router.get("/users/{user_id}/wishlists/{wishlist_id}", response_model=WishlistPublic)
async def get_user_wishlist(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    wishlist_id: uuid.UUID,
) -> WishlistPublic:
    """Get a specific wishlist for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise AppError(
            code="wishlist.not_found",
            status_code=404,
            message="Liste introuvable",
            details={"user_id": str(user_id)},
        )

    wishlist = await crud_wishlist.get_user_wishlist_by_id(
        session=session, wishlist_id=wishlist_id, user_id=user_id
    )
    if not wishlist:
        raise AppError(
            code="wishlist.not_found",
            status_code=404,
            message=f"Wishlist '{wishlist_id}' not found",
            details={"wishlist_id": str(wishlist_id)},
        )

    return WishlistPublic.model_validate(wishlist)


@router.get("/public", response_model=WishlistsAnonymousPublic)
async def get_public_wishlists(
    session: SessionDep,
    skip: int = Query(default=0, ge=0, description="Number of wishlists to skip"),
    limit: int = Query(
        default=100, le=100, ge=1, description="Number of wishlists to return"
    ),
) -> WishlistsAnonymousPublic:
    """Get all public wishlists (no owner ids)."""
    wishlists = await crud_wishlist.get_public_wishlists(
        session=session, skip=skip, limit=limit
    )
    count = len(wishlists)
    return WishlistsAnonymousPublic(
        data=[WishlistAnonymousPublic.model_validate(w) for w in wishlists],
        count=count,
    )


router.generate_endpoints()
