import uuid

from fastapi import HTTPException, Query, status

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep
from app.features.user.crud.wishlist import (
    WishlistCrud,
    crud_wishlist,
)
from app.features.user.models.wishlist import (
    Wishlist,
    WishlistCreate,
    WishlistPublic,
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
    pass


class Auth:
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
    auto=True,
)


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
        raise HTTPException(status_code=403, detail="Not authorized")

    wishlists = await crud_wishlist.get_by_user_id(
        session=session, user_id=user_id, skip=skip, limit=limit
    )
    count = await crud_wishlist.count_by_user(session=session, user_id=user_id)
    return WishlistsPublic(data=wishlists, count=count)


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
        raise HTTPException(status_code=403, detail="Not authorized")

    wishlist = await crud_wishlist.create_for_user(
        session=session,
        obj_in=wishlist_in,
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
        raise HTTPException(status_code=403, detail="Not authorized")

    wishlist = await crud_wishlist.get_user_wishlist_by_id(
        session=session, wishlist_id=wishlist_id, user_id=user_id
    )
    if not wishlist:
        raise HTTPException(status_code=404, detail="Wishlist not found")

    return WishlistPublic.model_validate(wishlist)


@router.get("/public", response_model=WishlistsPublic)
async def get_public_wishlists(
    session: SessionDep,
    skip: int = Query(default=0, ge=0, description="Number of wishlists to skip"),
    limit: int = Query(
        default=100, le=100, ge=1, description="Number of wishlists to return"
    ),
) -> WishlistsPublic:
    """Get all public wishlists."""
    wishlists = await crud_wishlist.get_public_wishlists(
        session=session, skip=skip, limit=limit
    )
    count = await crud_wishlist.count_public_wishlists(session=session)
    return WishlistsPublic(data=wishlists, count=count)
