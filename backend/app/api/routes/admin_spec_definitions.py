"""Admin endpoints: manage spec_definitions (spec catalog for product filtering).

Phase 3: table-backed definitions, editable via admin.
On any modification (PUT/DELETE), triggers re-projection of affected products.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from fastapi import status as http_status
from sqlmodel import select

from app.api.deps import CurrentSuperUser, SessionDep, module_required
from app.core.content_i18n import (
    SPEC_DEFINITION_FIELDS,
    InvalidTranslations,
    clean_translations,
)
from app.core.errors import AppError
from app.features.product.models.spec_definition import (
    SpecDefinition,
    SpecDefinitionCreate,
    SpecDefinitionPublic,
    SpecDefinitionsPublic,
    SpecDefinitionUpdate,
)

router = APIRouter(
    prefix="/admin/spec-definitions",
    tags=["admin-spec"],
    dependencies=[Depends(module_required("specs"))],
)


async def _trigger_reproject(category_id: str | None = None) -> None:
    """Fire-and-forget: enqueue a spec re-projection ARQ job."""
    try:
        from app.tasks.icecat_tasks import enqueue_reproject_product_specs

        await enqueue_reproject_product_specs(category_id=category_id)
    except Exception:
        pass  # Reproject can be triggered manually; don't fail the admin request


@router.get("", response_model=SpecDefinitionsPublic)
async def list_spec_definitions(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    include_inactive: bool = False,
) -> SpecDefinitionsPublic:
    """List all spec definitions."""
    stmt = select(SpecDefinition)
    if not include_inactive:
        stmt = stmt.where(SpecDefinition.is_active == True)  # noqa: E712
    result = await session.exec(stmt)
    specs = result.all()
    return SpecDefinitionsPublic(
        data=[SpecDefinitionPublic.model_validate(s) for s in specs],
        count=len(specs),
    )


@router.get("/{key}", response_model=SpecDefinitionPublic)
async def get_spec_definition(
    key: str,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> SpecDefinitionPublic:
    """Get a single spec definition by key."""
    stmt = select(SpecDefinition).where(SpecDefinition.key == key)
    result = await session.exec(stmt)
    spec = result.first()
    if spec is None:
        raise AppError(
            code="spec_definition.not_found",
            status_code=http_status.HTTP_404_NOT_FOUND,
            message=f"Spec definition '{key}' not found",
            details={"key": key},
        )
    return SpecDefinitionPublic.model_validate(spec)


def _translations(
    data: dict[str, Any], *, previous: dict[str, Any] | None, source: dict[str, Any]
) -> dict[str, Any]:
    """Validated, stamped translations of the label (R9 / T3)."""
    try:
        return clean_translations(
            data.get("translations"),
            previous=previous,
            source_values=source,
            fields=SPEC_DEFINITION_FIELDS,
        )
    except InvalidTranslations as exc:
        raise AppError(
            code="spec_definition.translations.invalid",
            status_code=http_status.HTTP_400_BAD_REQUEST,
            message=f"Traductions invalides : {exc}",
        ) from exc


@router.post("", response_model=SpecDefinitionPublic, status_code=201)
async def create_spec_definition(
    data: SpecDefinitionCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    _current_user: CurrentSuperUser,
) -> SpecDefinitionPublic:
    """Create a new spec definition. Triggers re-projection."""
    existing_stmt = select(SpecDefinition).where(SpecDefinition.key == data.key)
    existing_result = await session.exec(existing_stmt)
    if existing_result.first() is not None:
        raise AppError(
            code="spec_definition.duplicate_key",
            status_code=http_status.HTTP_409_CONFLICT,
            message=f"Spec definition with key '{data.key}' already exists",
            details={"key": data.key},
        )

    fields = data.model_dump()
    fields["translations"] = _translations(fields, previous=None, source=fields)
    spec = SpecDefinition(
        id=uuid.uuid4(),
        **fields,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(spec)
    await session.commit()
    await session.refresh(spec)

    background_tasks.add_task(_trigger_reproject)
    return SpecDefinitionPublic.model_validate(spec)


@router.put("/{key}", response_model=SpecDefinitionPublic)
async def update_spec_definition(
    key: str,
    data: SpecDefinitionUpdate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    _current_user: CurrentSuperUser,
) -> SpecDefinitionPublic:
    """Update a spec definition. Triggers re-projection."""
    stmt = select(SpecDefinition).where(SpecDefinition.key == key)
    result = await session.exec(stmt)
    spec = result.first()
    if spec is None:
        raise AppError(
            code="spec_definition.not_found",
            status_code=http_status.HTTP_404_NOT_FOUND,
            message=f"Spec definition '{key}' not found",
            details={"key": key},
        )

    changed = data.model_dump(exclude_unset=True)
    if "translations" in changed:
        source = {"label_fr": changed.get("label_fr", spec.label_fr)}
        changed["translations"] = _translations(
            changed, previous=spec.translations, source=source
        )
    for field, value in changed.items():
        setattr(spec, field, value)
    spec.updated_at = datetime.now(timezone.utc)

    session.add(spec)
    await session.commit()
    await session.refresh(spec)

    background_tasks.add_task(_trigger_reproject)
    return SpecDefinitionPublic.model_validate(spec)


@router.delete("/{key}", status_code=204)
async def delete_spec_definition(
    key: str,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    _current_user: CurrentSuperUser,
) -> Response:
    """Soft-delete a spec definition (sets is_active=False). Triggers re-projection."""
    stmt = select(SpecDefinition).where(SpecDefinition.key == key)
    result = await session.exec(stmt)
    spec = result.first()
    if spec is None:
        raise AppError(
            code="spec_definition.not_found",
            status_code=http_status.HTTP_404_NOT_FOUND,
            message=f"Spec definition '{key}' not found",
            details={"key": key},
        )

    spec.is_active = False
    spec.updated_at = datetime.now(timezone.utc)
    session.add(spec)
    await session.commit()

    background_tasks.add_task(_trigger_reproject)
    return Response(status_code=204)
