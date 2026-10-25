import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Query

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep, get_current_user_optional
from app.core.content_i18n import CATEGORY_FIELDS, localize_all
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.media.service import alts_for_urls
from app.features.product.crud.category import CategoryCrud, crud_category
from app.features.product.models.category import (
    CategoriesPublic,
    Category,
    CategoryCreate,
    CategoryPublic,
    CategoryUpdate,
)


async def _fill_image_alts(session: SessionDep, publics: list[CategoryPublic]) -> None:
    """The alt text of each tile image taken from the media library."""
    alts = await alts_for_urls(session, (p.image_url for p in publics))
    for public in publics:
        if public.image_url:
            public.image_alt = alts.get(public.image_url)


class CategoryRouter(
    BaseRouter[
        Category,
        CategoryCreate,
        CategoryUpdate,
        CategoryPublic,
        CategoriesPublic,
        CategoryCrud,
    ]
):
    """Represents category router."""

    def generate_read_multi_endpoint(self) -> Callable[..., Any]:
        """Override: a visitor reads the categories in their language (R9 / T3)."""

        async def read_multi(
            session: SessionDep,
            skip: Annotated[int, Query(ge=0)] = 0,
            limit: Annotated[int, Query(ge=1, le=500)] = 100,
            order_by: str | None = None,
            include_archived: bool = False,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> CategoriesPublic:
            await self._check_auth(session, "read", current_user)
            result = await self.crud.read_multi(
                session,
                skip=skip,
                limit=limit,
                filter=None,
                order_by=order_by,
                include_archived=include_archived,
                user=current_user,
            )
            publics = [CategoryPublic.model_validate(c) for c in result["data"]]
            if current_user is None or not current_user.is_superuser:
                localize_all(publics, CATEGORY_FIELDS)
            await _fill_image_alts(session, publics)
            return CategoriesPublic(data=publics, count=result["count"])

        read_multi.__name__ = "get_multiple_categorys"
        return read_multi

    def generate_read_endpoint(self) -> Callable[..., Any]:
        """Override: a visitor reads a category in their language (R9 / T3)."""

        async def read(
            session: SessionDep,
            id: uuid.UUID,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> CategoryPublic:
            await self._check_auth(session, "read", current_user)
            try:
                record = await self.crud.read(session, id=id, user=current_user)
            except RecordNotFoundError:
                raise AppError(
                    code="resource.not_found",
                    status_code=404,
                    message="category not found",
                    details={"resource": self.resource_name, "id": str(id)},
                )
            public = CategoryPublic.model_validate(record)
            if current_user is None or not current_user.is_superuser:
                localize_all([public], CATEGORY_FIELDS)
            await _fill_image_alts(session, [public])
            return public

        read.__name__ = "get_one_category"
        return read


class Auth:
    """Represents auth."""

    read = False  # Lecture publique des catégories
    create = True  # Création réservée aux admins
    update = True  # Modification réservée aux admins
    delete = True  # Suppression réservée aux admins
    read_superuser = False  # public catalogue
    create_superuser = True
    update_superuser = True
    delete_superuser = True


router = CategoryRouter(
    name="category",
    tags=["category"],
    crud=crud_category,
    schema_public=CategoryPublic,
    schema_publics=CategoriesPublic,
    schema_create=CategoryCreate,
    schema_update=CategoryUpdate,
    auth=Auth(),
    auto=True,
)
