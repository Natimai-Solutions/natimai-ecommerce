import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import SessionDep, get_current_active_superuser, CurrentUser
from app.features.user.crud.address import crud_address
from app.features.user.models.address import (
    Address,
    AddressCreate, 
    AddressPublic,
    AddressesPublic,
    AddressUpdate,
)


router = APIRouter()


@router.get(
    "/{user_id}/addresses",
    response_model=AddressesPublic,
)
async def read_user_addresses(
    session: SessionDep,
    user_id: uuid.UUID,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0, description="Number of addresses to skip"),
    limit: int = Query(default=100, le=100, ge=1, description="Number of addresses to return")
) -> Any:
    if current_user.id != user_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    addresses = await crud_address.get_by_user_id(
        session=session, user_id=user_id, skip=skip, limit=limit
    )
    count = await crud_address.count_by_user(session=session, user_id=user_id)
    
    return AddressesPublic(data=addresses, count=count)


@router.get(
    "/{user_id}/addresses/{address_id}",
    response_model=AddressPublic,
)
async def read_user_address(
    session: SessionDep,
    user_id: uuid.UUID,
    address_id: uuid.UUID,
    current_user: CurrentUser,
) -> Any:
    if current_user.id != user_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    address = await crud_address.get(session=session, id=address_id)
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
    
    if address.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
    
    return address


@router.post(
    "/{user_id}/addresses",
    response_model=AddressPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_address(
    session: SessionDep,
    user_id: uuid.UUID,
    address_in: AddressCreate,
    current_user: CurrentUser,
) -> Any:
    if current_user.id != user_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    address = await crud_address.create_for_user(
        session=session, obj_in=address_in, user_id=user_id
    )
    return address


@router.put(
    "/{user_id}/addresses/{address_id}",
    response_model=AddressPublic,
)
async def update_user_address(
    session: SessionDep,
    user_id: uuid.UUID,
    address_id: uuid.UUID,
    address_in: AddressUpdate,
    current_user: CurrentUser,
) -> Any:
    if current_user.id != user_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    address = await crud_address.get(session=session, id=address_id)
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
    
    if address.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
    
    address = await crud_address.update(
        session=session, db_obj=address, obj_in=address_in
    )
    return address


@router.delete(
    "/{user_id}/addresses/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_address(
    session: SessionDep,
    user_id: uuid.UUID,
    address_id: uuid.UUID,
    current_user: CurrentUser,
) -> None:
    if current_user.id != user_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    address = await crud_address.get(session=session, id=address_id)
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
    
    if address.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
    
    await crud_address.remove(session=session, id=address_id)


@router.get(
    "/{user_id}/addresses/by-type/{address_type}",
    response_model=list[AddressPublic],
)
async def read_user_addresses_by_type(
    session: SessionDep,
    user_id: uuid.UUID,
    address_type: str,
    current_user: CurrentUser,
) -> Any:
    if current_user.id != user_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    allowed_types = {"billing", "shipping", "other"}
    if address_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid address type. Must be one of: {', '.join(allowed_types)}"
        )
    
    addresses = await crud_address.get_by_user_and_type(
        session=session, user_id=user_id, address_type=address_type
    )
    return addresses