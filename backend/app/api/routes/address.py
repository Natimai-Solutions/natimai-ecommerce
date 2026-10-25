import uuid

from fastapi import Query, status
from pydantic import field_validator
from sqlmodel import SQLModel, col, select

from app.api.base_router import BaseRouter
from app.api.deps import CurrentSuperUser, CurrentUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.place.crud import crud_place
from app.features.user.crud.address import AddressCrud, crud_address
from app.features.user.models.address import (
    Address,
    AddressCreate,
    AddressesPublic,
    AddressPublic,
    AddressUpdate,
    AdminAddressesPublic,
    AdminAddressPublic,
    validate_address_type,
)
from app.features.user.models.user import User


class AddressMeCreate(SQLModel):
    """Self-service create payload (user_id is derived from current user)."""

    street: str
    city: str
    state: str | None = None
    postal_code: str
    country: str
    type: str
    place_id: uuid.UUID | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        return validate_address_type(v)


class AddressMeUpdate(SQLModel):
    """Self-service update payload (ownership and validation are server-managed)."""

    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    type: str | None = None
    place_id: uuid.UUID | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_address_type(v)
        return v


async def _resolve_address_place_id(
    session: SessionDep,
    *,
    place_id: uuid.UUID | None,
    country: str | None,
    postal_code: str | None,
) -> uuid.UUID | None:
    """Geographic zone of an address: explicit choice or postal-code lookup.

    An explicitly provided ``place_id`` is validated and kept; otherwise the
    zone is deduced from country + postal code (e.g. PF: 98728 → Moorea).
    Unknown postal codes simply leave the address without a zone — checkout
    then only offers destination-independent delivery modes.
    """
    if place_id is not None:
        try:
            await crud_place.read(session, id=place_id)
        except RecordNotFoundError as exc:
            raise AppError(
                code="address.place.unknown",
                status_code=400,
                message=f"Unknown place '{place_id}'",
                details={"place_id": str(place_id)},
            ) from exc
        return place_id

    if country and postal_code:
        place = await crud_place.resolve_by_postal_code(
            session, country=country, postal_code=postal_code
        )
        if place is not None:
            return place.id
    return None


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
    """Superuser-only: the generic CRUD has no ownership check (IDOR on PII).
    Customers use the /users/me/addresses endpoints below, admins the
    /admin/addresses ones — both carry their own explicit guards."""

    read = True
    create = True
    update = True
    delete = True
    read_superuser = True
    create_superuser = True
    update_superuser = True
    delete_superuser = True


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


# ---------------------------------------------------------------------------
# /users/me/addresses — self-service endpoints
#
# IMPORTANT: these MUST be declared before the /users/{user_id}/... routes
# below. Starlette matches routes in registration order; if the parametrized
# {user_id} routes came first, a request to /users/me/addresses would bind
# user_id="me", failing UUID validation with a 422 and making the self-service
# endpoints unreachable.
# ---------------------------------------------------------------------------


@router.get("/users/me/addresses", response_model=AddressesPublic)
async def get_my_addresses(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=100, ge=1),
) -> AddressesPublic:
    """List all addresses belonging to the authenticated user."""
    addresses = await crud_address.get_by_user_id(
        session=session, user_id=current_user.id, skip=skip, limit=limit
    )
    count = await crud_address.count_by_user(session=session, user_id=current_user.id)
    return AddressesPublic(
        data=[AddressPublic.model_validate(a) for a in addresses], count=count
    )


@router.post(
    "/users/me/addresses",
    response_model=AddressPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_address(
    session: SessionDep,
    current_user: CurrentUser,
    address_in: AddressMeCreate,
) -> AddressPublic:
    """Create a new address for the authenticated user."""
    resolved_place_id = await _resolve_address_place_id(
        session,
        place_id=address_in.place_id,
        country=address_in.country,
        postal_code=address_in.postal_code,
    )
    payload = AddressCreate(
        **address_in.model_dump(exclude={"place_id"}),
        place_id=resolved_place_id,
        user_id=current_user.id,
    )
    address = await crud_address.create_for_user(
        session=session,
        data=payload,
        user_id=current_user.id,
        current_user=current_user.id,
    )
    return AddressPublic.model_validate(address)


@router.get("/users/me/addresses/{address_id}", response_model=AddressPublic)
async def get_my_address(
    session: SessionDep,
    current_user: CurrentUser,
    address_id: uuid.UUID,
) -> AddressPublic:
    """Get a specific address belonging to the authenticated user."""
    try:
        address = await crud_address.read(session=session, id=address_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        ) from exc

    if address.user_id != current_user.id:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        )
    return AddressPublic.model_validate(address)


@router.patch("/users/me/addresses/{address_id}", response_model=AddressPublic)
async def update_my_address(
    session: SessionDep,
    current_user: CurrentUser,
    address_id: uuid.UUID,
    address_in: AddressMeUpdate,
) -> AddressPublic:
    """Update a specific address belonging to the authenticated user.

    is_validated cannot be modified here — use the admin validate endpoint.
    """
    try:
        address = await crud_address.read(session=session, id=address_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        ) from exc

    if address.user_id != current_user.id:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        )

    update_dict = address_in.model_dump(exclude_unset=True)
    # Re-resolve the zone when the location changed without an explicit choice
    # (otherwise a stale island would survive a postal-code edit).
    if "place_id" in update_dict:
        update_dict["place_id"] = await _resolve_address_place_id(
            session,
            place_id=update_dict["place_id"],
            country=update_dict.get("country", address.country),
            postal_code=update_dict.get("postal_code", address.postal_code),
        )
    elif "postal_code" in update_dict or "country" in update_dict:
        update_dict["place_id"] = await _resolve_address_place_id(
            session,
            place_id=None,
            country=update_dict.get("country", address.country),
            postal_code=update_dict.get("postal_code", address.postal_code),
        )
    update_payload = AddressUpdate(**update_dict)
    address = await crud_address.update(
        session=session,
        id=address_id,
        record=address,
        data=update_payload,
        user=current_user,
    )
    return AddressPublic.model_validate(address)


@router.delete(
    "/users/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_my_address(
    session: SessionDep,
    current_user: CurrentUser,
    address_id: uuid.UUID,
) -> None:
    """Delete a specific address belonging to the authenticated user."""
    try:
        address = await crud_address.read(session=session, id=address_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        ) from exc

    if address.user_id != current_user.id:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        )
    await crud_address.delete(session=session, id=address_id, record=address)


# ---------------------------------------------------------------------------
# Admin / user-scoped address routes (/users/{user_id}/...)
# ---------------------------------------------------------------------------


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
        raise AppError(
            code="address.not_found",
            status_code=404,
            message="Adresse introuvable",
            details={"user_id": str(user_id)},
        )

    addresses = await crud_address.get_by_user_id(
        session=session, user_id=user_id, skip=skip, limit=limit
    )
    count = await crud_address.count_by_user(session=session, user_id=user_id)

    return AddressesPublic(
        data=[AddressPublic.model_validate(a) for a in addresses], count=count
    )


@router.get("/users/{user_id}/addresses/{address_id}", response_model=AddressPublic)
async def get_user_address(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    address_id: uuid.UUID,
) -> AddressPublic:
    """Get a specific address for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise AppError(
            code="address.not_found",
            status_code=404,
            message="Adresse introuvable",
            details={"user_id": str(user_id)},
        )

    try:
        address = await crud_address.read(session=session, id=address_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        ) from exc

    if address.user_id != user_id:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        )

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
        raise AppError(
            code="address.not_found",
            status_code=404,
            message="Adresse introuvable",
            details={"user_id": str(user_id)},
        )

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
        raise AppError(
            code="address.not_found",
            status_code=404,
            message="Adresse introuvable",
            details={"user_id": str(user_id)},
        )

    try:
        address = await crud_address.read(session=session, id=address_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        ) from exc

    if address.user_id != user_id:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        )

    update_dict = address_in.model_dump(exclude_unset=True)
    update_dict.pop("user_id", None)
    address = await crud_address.update(
        session=session,
        id=address_id,
        record=address,
        data=AddressUpdate(**update_dict),
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
        raise AppError(
            code="address.not_found",
            status_code=404,
            message="Adresse introuvable",
            details={"user_id": str(user_id)},
        )

    try:
        address = await crud_address.read(session=session, id=address_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        ) from exc

    if address.user_id != user_id:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        )

    await crud_address.delete(session=session, id=address_id, record=address)


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/admin/addresses/{address_id}/validate",
    response_model=AddressPublic,
)
async def admin_validate_address(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    address_id: uuid.UUID,
) -> AddressPublic:
    """Mark an address as validated (admin only).

    Once validated, the address can be selected at checkout.
    Re-validating an already-validated address is idempotent.
    """
    try:
        address = await crud_address.read(session=session, id=address_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="address.not_found",
            status_code=404,
            message=f"Address '{address_id}' not found",
            details={"address_id": str(address_id)},
        ) from exc

    if address.is_validated:
        return AddressPublic.model_validate(address)

    address = await crud_address.validate_address(session=session, address=address)
    return AddressPublic.model_validate(address)


@router.get("/admin/addresses", response_model=AdminAddressesPublic)
async def admin_list_addresses(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    validated: bool | None = Query(
        default=None,
        description="Filter on the admin-validation flag (omit for all addresses)",
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> AdminAddressesPublic:
    """List addresses across all users for the admin validation screen."""
    addresses = await crud_address.list_all(
        session=session, validated=validated, skip=skip, limit=limit
    )
    total = await crud_address.count_all(session=session, validated=validated)

    emails: dict[uuid.UUID, str] = {}
    user_ids = {address.user_id for address in addresses}
    if user_ids:
        rows = await session.exec(
            select(User.id, User.email).where(col(User.id).in_(user_ids))
        )
        emails = {row[0]: row[1] for row in rows}

    data: list[AdminAddressPublic] = []
    for address in addresses:
        public = AdminAddressPublic.model_validate(address)
        public.user_email = emails.get(address.user_id)
        data.append(public)

    return AdminAddressesPublic(data=data, count=total)


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
        raise AppError(
            code="address.not_found",
            status_code=404,
            message="Adresse introuvable",
            details={"user_id": str(user_id)},
        )

    allowed_types = {"billing", "shipping", "other"}
    if address_type not in allowed_types:
        ordered_allowed = sorted(allowed_types)
        raise AppError(
            code="address.type.invalid",
            status_code=400,
            message=(
                "Invalid address type. Must be one of: " + ", ".join(ordered_allowed)
            ),
            details={
                "address_type": address_type,
                "allowed": ordered_allowed,
            },
        )

    addresses = await crud_address.get_by_user_and_type(
        session=session, user_id=user_id, address_type=address_type
    )
    return [AddressPublic.model_validate(address) for address in addresses]
