"""The CRUD routes ``BaseRouter`` generates are closed by default: a
superuser only, unless a router opens a permission explicitly. The opened
ones are listed here — opening a new one is a decision this test makes
visible (a generated route answers with the whole table)."""

from __future__ import annotations

import importlib
import pkgutil
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

import app.api.routes as routes_package
from app.api.base_router import BaseRouter
from app.api.routes.partner import router as partner_router
from app.api.routes.user_wishlist import router as wishlist_router
from app.core.errors import AppError
from app.features.user.models.user import User

PERMISSIONS = ("read", "create", "update", "delete")

#: (resource, permission) a non-superuser may call on a generated route.
OPEN_TO_CUSTOMERS = {
    ("brand", "read"),
    ("category", "read"),
    ("group", "read"),
    ("order", "read"),  # scoped to the caller by OrderRouter
    ("order-status", "read"),
    ("payment_method", "read"),
    ("place", "read"),
    ("product", "read"),
    ("review", "read"),
}


def _routers() -> list[BaseRouter[Any, Any, Any, Any, Any, Any]]:
    found: dict[int, BaseRouter[Any, Any, Any, Any, Any, Any]] = {}
    for info in pkgutil.walk_packages(
        routes_package.__path__, routes_package.__name__ + "."
    ):
        module = importlib.import_module(info.name)
        for value in vars(module).values():
            if isinstance(value, BaseRouter):
                found[id(value)] = value
    return list(found.values())


def test_generated_routes_are_superuser_only_unless_listed() -> None:
    opened = {
        (router.resource_name, permission)
        for router in _routers()
        for permission in PERMISSIONS
        if not getattr(router.auth, f"{permission}_superuser")
    }
    assert opened == OPEN_TO_CUSTOMERS


def test_an_auth_that_says_nothing_is_closed() -> None:
    class Silent:
        """Asks for a login, says nothing about superusers."""

        read = True
        create = True
        update = True
        delete = True

    router: BaseRouter[Any, Any, Any, Any, Any, Any] = BaseRouter(
        name="silent", crud=cast(Any, SimpleNamespace()), auth=Silent()
    )
    assert all(getattr(router.auth, f"{p}_superuser") for p in PERMISSIONS)


@pytest.mark.asyncio
@pytest.mark.parametrize("router", [wishlist_router, partner_router])
@pytest.mark.parametrize("permission", PERMISSIONS)
async def test_a_customer_cannot_use_the_generic_routes(
    router: BaseRouter[Any, Any, Any, Any, Any, Any], permission: str
) -> None:
    customer = cast(User, SimpleNamespace(id=None, is_superuser=False))
    with pytest.raises(AppError) as refused:
        await router._check_auth(cast(Any, AsyncMock()), permission, customer)
    assert refused.value.status_code == 403
