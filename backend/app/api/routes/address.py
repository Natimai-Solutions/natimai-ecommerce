import uuid

from fastapi import HTTPException, Query, status

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep
from app.features.base.crud import RecordNotFoundError
from app.features.user.crud.address import AddressCrud, crud_address
from app.features.user.models.address import (
    Address,
    AddressCreate,
    AddressesPublic,
    AddressPublic,
    AddressUpdate,
)


def _check_permission(
    current_user_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False
) -> bool:
    """Check if current user can access resource for given user_id."""
    return current_user_id == user_id or is_admin


class AddressRouter(
    BaseRouter[
        Address,
        AddressCreate,
        AddressUpdate,
        AddressPublic,
        AddressesPublic,
        AddressCrud,
    ]
):
    """Represents address router."""

    pass


class Auth:
    """Represents auth."""

    read = True
    create = True
    update = True
    delete = True


router = AddressRouter(
    name="address",
    tags=["address"],
    crud=crud_address,
    schema_public=AddressPublic,
    schema_publics=AddressesPublic,
    schema_create=AddressCreate,
    schema_update=AddressUpdate,
    auth=Auth(),
    auto=True,
)


# User-specific address routes
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

    try:
        address = await crud_address.read(session=session, id=address_id)
    except RecordNotFoundError:
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
        session=session, data=address_in, user_id=user_id
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

    try:
        address = await crud_address.read(session=session, id=address_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Address not found")

    if address.user_id != user_id:
        raise HTTPException(status_code=404, detail="Address not found")

    address = await crud_address.update(
        session=session, id=address_id, record=address, data=address_in
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

    try:
        address = await crud_address.read(session=session, id=address_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Address not found")

    if address.user_id != user_id:
        raise HTTPException(status_code=404, detail="Address not found")

    await crud_address.delete(session=session, id=address_id, record=address)


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
