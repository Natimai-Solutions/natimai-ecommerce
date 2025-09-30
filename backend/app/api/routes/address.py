import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.features.user.crud.address import crud_address
from app.features.user.models.address import (
    AddressCreate,
    AddressesPublic,
    AddressPublic,
    AddressUpdate,
)

router = APIRouter()


def _check_permission(
    current_user_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False
) -> bool:
    """Check if current user can access resource for given user_id."""
    return current_user_id == user_id or is_admin


@router.get("/users/{user_id}/addresses", response_model=AddressesPublic)
async def get_user_addresses(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    skip: int = Query(default=0, ge=0, description="Number of addresses to skip"),
    limit: int = Query(
        default=100, le=100, ge=1, description="Number of addresses to return"
    ),
) -> AddressesPublic:
    """Get all addresses for a specific user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    addresses = await crud_address.get_by_user_id(
        session=session, user_id=user_id, skip=skip, limit=limit
    )
    count = await crud_address.count_by_user(session=session, user_id=user_id)

    return AddressesPublic(data=addresses, count=count)


@router.get("/users/{user_id}/addresses/{address_id}", response_model=AddressPublic)
async def get_user_address(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    address_id: uuid.UUID,
) -> AddressPublic:
    """Get a specific address for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    address = await crud_address.get(session=session, id=address_id)
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    if address.user_id != user_id:
        raise HTTPException(status_code=404, detail="Address not found")

    return AddressPublic.model_validate(address)


@router.post(
    "/users/{user_id}/addresses",
    response_model=AddressPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_address(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    address_in: AddressCreate,
) -> AddressPublic:
    """Create a new address for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    address = await crud_address.create_for_user(
        session=session, obj_in=address_in, user_id=user_id
    )
    return AddressPublic.model_validate(address)


@router.patch("/users/{user_id}/addresses/{address_id}", response_model=AddressPublic)
async def update_user_address(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    address_id: uuid.UUID,
    address_in: AddressUpdate,
) -> AddressPublic:
    """Update a specific address for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    address = await crud_address.get(session=session, id=address_id)
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    if address.user_id != user_id:
        raise HTTPException(status_code=404, detail="Address not found")

    address = await crud_address.update(
        session=session, db_obj=address, obj_in=address_in
    )
    return AddressPublic.model_validate(address)


@router.delete(
    "/users/{user_id}/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_user_address(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    address_id: uuid.UUID,
) -> None:
    """Delete a specific address for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    address = await crud_address.get(session=session, id=address_id)
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    if address.user_id != user_id:
        raise HTTPException(status_code=404, detail="Address not found")

    await crud_address.remove(session=session, id=address_id)


@router.get(
    "/users/{user_id}/addresses/by-type/{address_type}",
    response_model=list[AddressPublic],
)
async def get_user_addresses_by_type(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    address_type: str,
) -> list[AddressPublic]:
    """Get addresses for a user filtered by type."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")

    allowed_types = {"billing", "shipping", "other"}
    if address_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid address type. Must be one of: {', '.join(allowed_types)}",
        )

    addresses = await crud_address.get_by_user_and_type(
        session=session, user_id=user_id, address_type=address_type
    )
    return [AddressPublic.model_validate(address) for address in addresses]
