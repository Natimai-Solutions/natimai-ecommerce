import uuid
from typing import Any

from fastapi import Depends

from app.api.base_router import BaseRouter, Routes
from app.api.deps import CurrentUser, SessionDep, get_current_user_optional
from app.core.errors import AppError
from app.features.user.crud.group import crud_group
from app.features.user.crud.user_group import crud_user_group
from app.features.user.models.group import (
    Group,
    GroupCreate,
    GroupPublic,
    GroupsPublic,
    GroupUpdate,
)
from app.features.user.models.user_group import (
    UserGroupCreate,
    UserGroupPublic,
    UserGroupsPublic,
)


class GroupRouter(
    BaseRouter[
        Group,
        GroupCreate,
        GroupUpdate,
        GroupPublic,
        GroupsPublic,
        Any,
    ]
):
    """Router for Group endpoints"""

    pass


# Custom endpoints for Group
async def get_groups_by_type(
    session: SessionDep,
    group_type: str,
    skip: int = 0,
    limit: int = 100,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> GroupsPublic:
    """Get all groups of a specific type"""
    if current_user is None:
        raise AppError(
            code="group.authentication_required",
            status_code=403,
            message="Authentication required",
            details={"resource": "group.by_type"},
        )

    groups = await crud_group.get_by_type(
        session,
        group_type=group_type,
        skip=skip,
        limit=limit,
    )
    return GroupsPublic(data=groups, count=len(groups))


async def get_pricing_groups(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> GroupsPublic:
    """Get all pricing/discount groups"""
    if current_user is None:
        raise AppError(
            code="group.authentication_required",
            status_code=403,
            message="Authentication required",
            details={"resource": "group.pricing"},
        )

    groups = await crud_group.get_pricing_groups(
        session,
        skip=skip,
        limit=limit,
    )
    return GroupsPublic(data=groups, count=len(groups))


async def add_user_to_group(
    session: SessionDep,
    group_id: uuid.UUID,
    user_group: UserGroupCreate,
    current_user: CurrentUser,
) -> UserGroupPublic:
    """Add a user to a group"""
    if not current_user.is_superuser:
        raise AppError(
            code="group.admin_required",
            status_code=403,
            message="Admin access required",
            details={"resource": "group.users.add"},
        )

    try:
        result = await crud_user_group.add_user_to_group(
            session,
            user_id=user_group.user_id,
            group_id=group_id,
        )
        return UserGroupPublic.model_validate(result)
    except ValueError as e:
        raise AppError(
            code="group.user_membership.invalid",
            status_code=400,
            message=str(e),
            details={
                "group_id": str(group_id),
                "user_id": str(user_group.user_id),
                "reason": str(e),
            },
        ) from e


async def remove_user_from_group(
    session: SessionDep,
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Remove a user from a group"""
    if not current_user.is_superuser:
        raise AppError(
            code="group.admin_required",
            status_code=403,
            message="Admin access required",
            details={"resource": "group.users.remove"},
        )

    removed = await crud_user_group.remove_user_from_group(
        session,
        user_id=user_id,
        group_id=group_id,
    )

    if not removed:
        raise AppError(
            code="group.user_not_in_group",
            status_code=404,
            message=f"User {user_id} not found in group {group_id}",
            details={
                "group_id": str(group_id),
                "user_id": str(user_id),
            },
        )

    return {"message": "User removed from group successfully"}


async def get_group_users(
    session: SessionDep,
    group_id: uuid.UUID,
    _current_user: CurrentUser,
) -> UserGroupsPublic:
    """Get all users in a specific group"""
    user_groups = await crud_user_group.get_group_users(
        session,
        group_id=group_id,
    )
    return UserGroupsPublic(data=user_groups, count=len(user_groups))


async def get_user_groups(
    session: SessionDep,
    user_id: uuid.UUID,
    current_user: CurrentUser,
) -> UserGroupsPublic:
    """Get all groups a user belongs to"""
    # Only allow users to see their own groups unless admin
    if not current_user.is_superuser and current_user.id != user_id:
        raise AppError(
            code="group.not_owned",
            status_code=403,
            message="You cannot access another user's groups",
            details={"user_id": str(user_id)},
        )

    user_groups = await crud_user_group.get_user_groups(
        session,
        user_id=user_id,
    )
    return UserGroupsPublic(data=user_groups, count=len(user_groups))


# Literal single-segment routes MUST be registered BEFORE the auto-generated
# /{id} route: FastAPI path params are `str` convertors in Starlette, so /{id}
# would otherwise greedily capture "/pricing" and 422 on the UUID parse.
routes_before_group = [
    Routes(
        path="/pricing",
        endpoint=get_pricing_groups,
        methods=["GET"],
        tags=["group"],
        response_model=GroupsPublic,
    ),
]

# Routes for Group with custom endpoints
routes_after_group = [
    Routes(
        path="/by-type/{group_type}",
        endpoint=get_groups_by_type,
        methods=["GET"],
        tags=["group"],
        response_model=GroupsPublic,
    ),
    Routes(
        path="/{group_id}/users",
        endpoint=get_group_users,
        methods=["GET"],
        tags=["group"],
        response_model=UserGroupsPublic,
    ),
    Routes(
        path="/{group_id}/users",
        endpoint=add_user_to_group,
        methods=["POST"],
        tags=["group"],
        response_model=UserGroupPublic,
    ),
    Routes(
        path="/{group_id}/users/{user_id}",
        endpoint=remove_user_from_group,
        methods=["DELETE"],
        tags=["group"],
    ),
]

# Routes for user groups
routes_user_groups = [
    Routes(
        path="/users/{user_id}/groups",
        endpoint=get_user_groups,
        methods=["GET"],
        tags=["group"],
        response_model=UserGroupsPublic,
    ),
]


# Authentication configuration
class Auth:
    """Represents auth."""

    read = True  # Authentication required for read
    create = True  # Authentication required for create
    update = True  # Authentication required for update
    delete = True  # Authentication required for delete


# Instantiate router with auto-generated CRUD endpoints
router = GroupRouter(
    name="group",
    tags=["group"],
    crud=crud_group,
    schema_public=GroupPublic,
    schema_publics=GroupsPublic,
    schema_create=GroupCreate,
    schema_update=GroupUpdate,
    auth=Auth(),
    routes_before=routes_before_group,
    routes_after=routes_after_group + routes_user_groups,
    auto=True,  # Generate standard CRUD endpoints
)
