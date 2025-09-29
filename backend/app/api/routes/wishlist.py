import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import CurrentUser, SessionDep
from app.features.user.crud.wishlist import crud_wishlist, crud_wishlist_item
from app.features.user.models.wishlist import (
    WishlistPublic,
    WishlistsPublic,
    WishlistCreate,
    WishlistUpdate,
    WishlistItemPublic,
    WishlistItemsPublic,
    WishlistItemCreate,
    WishlistItemUpdate,
)

router = APIRouter()


def _check_permission(current_user_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False) -> bool:
    """Check if current user can access resource for given user_id."""
    return current_user_id == user_id or is_admin


@router.get("/users/{user_id}/wishlists", response_model=WishlistsPublic)
async def get_user_wishlists(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> WishlistsPublic:
    """Get all wishlists for a specific user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    wishlists = await crud_wishlist.get_by_user_id(
        session=session, user_id=user_id, skip=skip, limit=limit
    )
    count = await crud_wishlist.count_by_user(session=session, user_id=user_id)
    return WishlistsPublic(data=wishlists, count=count)


@router.post("/users/{user_id}/wishlists", response_model=WishlistPublic, status_code=status.HTTP_201_CREATED)
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
        session=session, obj_in=wishlist_in, user_id=user_id, current_user=current_user.id
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


@router.patch("/users/{user_id}/wishlists/{wishlist_id}", response_model=WishlistPublic)
async def update_user_wishlist(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    wishlist_id: uuid.UUID,
    wishlist_update: WishlistUpdate,
) -> WishlistPublic:
    """Update a specific wishlist."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    wishlist = await crud_wishlist.get_user_wishlist_by_id(
        session=session, wishlist_id=wishlist_id, user_id=user_id
    )
    if not wishlist:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    updated_wishlist = await crud_wishlist.update(
        session=session, db_obj=wishlist, obj_in=wishlist_update
    )
    return WishlistPublic.model_validate(updated_wishlist)


@router.delete("/users/{user_id}/wishlists/{wishlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_wishlist(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    wishlist_id: uuid.UUID,
) -> None:
    """Delete a specific wishlist."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    wishlist = await crud_wishlist.get_user_wishlist_by_id(
        session=session, wishlist_id=wishlist_id, user_id=user_id
    )
    if not wishlist:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    await crud_wishlist.remove(session=session, id=wishlist_id)


# Wishlist Items endpoints
@router.get("/users/{user_id}/wishlists/{wishlist_id}/items", response_model=WishlistItemsPublic)
async def get_wishlist_items(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    wishlist_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
) -> WishlistItemsPublic:
    """Get all items in a specific wishlist."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Verify wishlist belongs to user
    wishlist = await crud_wishlist.get_user_wishlist_by_id(
        session=session, wishlist_id=wishlist_id, user_id=user_id
    )
    if not wishlist:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    items = await crud_wishlist_item.get_by_wishlist_id(
        session=session, wishlist_id=wishlist_id, skip=skip, limit=limit
    )
    count = await crud_wishlist_item.count_by_wishlist(
        session=session, wishlist_id=wishlist_id
    )
    return WishlistItemsPublic(data=items, count=count)


@router.post("/users/{user_id}/wishlists/{wishlist_id}/items", response_model=WishlistItemPublic, status_code=status.HTTP_201_CREATED)
async def add_item_to_wishlist(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    wishlist_id: uuid.UUID,
    item_in: WishlistItemCreate,
) -> WishlistItemPublic:
    """Add an item to a wishlist."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Verify wishlist belongs to user
    wishlist = await crud_wishlist.get_user_wishlist_by_id(
        session=session, wishlist_id=wishlist_id, user_id=user_id
    )
    if not wishlist:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    # Check if item already exists in wishlist
    existing_item = await crud_wishlist_item.get_by_wishlist_and_product(
        session=session, wishlist_id=wishlist_id, product_id=item_in.product_id
    )
    if existing_item:
        raise HTTPException(status_code=400, detail="Product already exists in wishlist")
    
    item = await crud_wishlist_item.create_for_wishlist(
        session=session, obj_in=item_in, wishlist_id=wishlist_id, current_user=current_user.id
    )
    return WishlistItemPublic.model_validate(item)


@router.get("/users/{user_id}/wishlists/{wishlist_id}/items/{item_id}", response_model=WishlistItemPublic)
async def get_wishlist_item(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    wishlist_id: uuid.UUID,
    item_id: uuid.UUID,
) -> WishlistItemPublic:
    """Get a specific item from a wishlist."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Verify wishlist belongs to user
    wishlist = await crud_wishlist.get_user_wishlist_by_id(
        session=session, wishlist_id=wishlist_id, user_id=user_id
    )
    if not wishlist:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    item = await crud_wishlist_item.get(session=session, id=item_id)
    if not item or item.wishlist_id != wishlist_id:
        raise HTTPException(status_code=404, detail="Wishlist item not found")
    
    return WishlistItemPublic.model_validate(item)


@router.patch("/users/{user_id}/wishlists/{wishlist_id}/items/{item_id}", response_model=WishlistItemPublic)
async def update_wishlist_item(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    wishlist_id: uuid.UUID,
    item_id: uuid.UUID,
    item_update: WishlistItemUpdate,
) -> WishlistItemPublic:
    """Update a specific item in a wishlist."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Verify wishlist belongs to user
    wishlist = await crud_wishlist.get_user_wishlist_by_id(
        session=session, wishlist_id=wishlist_id, user_id=user_id
    )
    if not wishlist:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    item = await crud_wishlist_item.get(session=session, id=item_id)
    if not item or item.wishlist_id != wishlist_id:
        raise HTTPException(status_code=404, detail="Wishlist item not found")
    
    updated_item = await crud_wishlist_item.update(
        session=session, db_obj=item, obj_in=item_update
    )
    return WishlistItemPublic.model_validate(updated_item)


@router.delete("/users/{user_id}/wishlists/{wishlist_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item_from_wishlist(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    wishlist_id: uuid.UUID,
    item_id: uuid.UUID,
) -> None:
    """Remove an item from a wishlist."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Verify wishlist belongs to user
    wishlist = await crud_wishlist.get_user_wishlist_by_id(
        session=session, wishlist_id=wishlist_id, user_id=user_id
    )
    if not wishlist:
        raise HTTPException(status_code=404, detail="Wishlist not found")
    
    item = await crud_wishlist_item.get(session=session, id=item_id)
    if not item or item.wishlist_id != wishlist_id:
        raise HTTPException(status_code=404, detail="Wishlist item not found")
    
    await crud_wishlist_item.remove(session=session, id=item_id)


# Public endpoints for browsing public wishlists
@router.get("/wishlists/public", response_model=WishlistsPublic)
async def get_public_wishlists(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
) -> WishlistsPublic:
    """Get all public wishlists."""
    wishlists = await crud_wishlist.get_public_wishlists(
        session=session, skip=skip, limit=limit
    )
    return WishlistsPublic(data=wishlists, count=len(wishlists))