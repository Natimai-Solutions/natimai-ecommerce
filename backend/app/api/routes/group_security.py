import uuid
from typing import Any

from app.api.base_router import BaseRouter, Routes
from app.api.deps import CurrentUser, SessionDep
from app.core.errors import AppError
from app.features.user.crud.group_security import crud_group_security
from app.features.user.models.group_security import (
    GroupSecuritiesPublic,
    GroupSecurity,
    GroupSecurityCreate,
    GroupSecurityPublic,
    GroupSecurityUpdate,
)


class GroupSecurityRouter(
    BaseRouter[
        GroupSecurity,
        GroupSecurityCreate,
        GroupSecurityUpdate,
        GroupSecurityPublic,
        GroupSecuritiesPublic,
        Any,
    ]
):
    """Router for GroupSecurity endpoints"""

    pass


# Custom endpoints for GroupSecurity
async def get_group_permissions(
    session: SessionDep,
    group_id: uuid.UUID,
    current_user: CurrentUser,
) -> GroupSecuritiesPublic:
    """Get all security rules for a specific group"""
    if not current_user.is_superuser:
        raise AppError(
            code="group_security.admin_required",
            status_code=403,
            message="Admin access required",
            details={"resource": "group_security.group_permissions"},
        )

    rules = await crud_group_security.get_group_permissions(
        session,
        group_id=group_id,
    )
    return GroupSecuritiesPublic(data=rules, count=len(rules))


async def get_table_permissions(
    session: SessionDep,
    table_name: str,
    current_user: CurrentUser,
) -> GroupSecuritiesPublic:
    """Get all security rules for a specific table"""
    if not current_user.is_superuser:
        raise AppError(
            code="group_security.admin_required",
            status_code=403,
            message="Admin access required",
            details={"resource": "group_security.table_permissions"},
        )

    rules = await crud_group_security.get_table_permissions(
        session,
        table_name=table_name,
    )
    return GroupSecuritiesPublic(data=rules, count=len(rules))


async def check_permission(
    session: SessionDep,
    group_id: uuid.UUID,
    table_name: str,
    permission: str,
    current_user: CurrentUser,
) -> dict[str, str | bool]:
    """Check if a group has a specific permission on a table"""
    if not current_user.is_superuser:
        raise AppError(
            code="group_security.admin_required",
            status_code=403,
            message="Admin access required",
            details={"resource": "group_security.permission_check"},
        )

    has_permission = await crud_group_security.check_permission(
        session,
        group_id=group_id,
        table_name=table_name,
        permission=permission,
    )

    return {
        "group_id": str(group_id),
        "table_name": table_name,
        "permission": permission,
        "has_permission": has_permission,
    }


# Custom routes
routes_after_security = [
    Routes(
        path="/group/{group_id}/permissions",
        endpoint=get_group_permissions,
        methods=["GET"],
        tags=["group-security"],
        response_model=GroupSecuritiesPublic,
    ),
    Routes(
        path="/table/{table_name}/permissions",
        endpoint=get_table_permissions,
        methods=["GET"],
        tags=["group-security"],
        response_model=GroupSecuritiesPublic,
    ),
    Routes(
        path="/check/{group_id}/{table_name}/{permission}",
        endpoint=check_permission,
        methods=["GET"],
        tags=["group-security"],
    ),
]


# Authentication configuration - Admin only
class Auth:
    """Represents auth."""

    read = True
    create = True
    update = True
    delete = True


# Instantiate router
router = GroupSecurityRouter(
    name="group_security",
    tags=["group-security"],
    crud=crud_group_security,
    schema_public=GroupSecurityPublic,
    schema_publics=GroupSecuritiesPublic,
    schema_create=GroupSecurityCreate,
    schema_update=GroupSecurityUpdate,
    auth=Auth(),
    routes_after=routes_after_security,
    auto=True,
)
