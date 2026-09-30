"""Admin back-office of the ``suppliers`` table.

  GET    /admin/suppliers            — every supplier (inactive included)
  GET    /admin/suppliers/adapters   — implementations available in the code
  POST   /admin/suppliers            — declare a supplier
  GET    /admin/suppliers/{code}
  PATCH  /admin/suppliers/{code}     — partial update (``code`` is immutable)
  DELETE /admin/suppliers/{code}     — deactivate (products keep their link;
                                       ?products=zero_stock|hide withdraws them)
  GET    /admin/suppliers/{code}/sku-allowlist — the references we follow
  PUT    /admin/suppliers/{code}/sku-allowlist — replace that list
  GET    /admin/suppliers/{code}/category-mappings — category rules (S5)
  PUT    /admin/suppliers/{code}/category-mappings — create / replace rules
  DELETE /admin/suppliers/{code}/category-mappings/{id}
  POST   /admin/suppliers/{code}/category-mappings/reapply — move products
  GET    /admin/suppliers/{code}/observed-categories — couples seen in base
  PUT    /admin/suppliers/{code}/credentials — store a feed login (encrypted)
  DELETE /admin/suppliers/{code}/credentials
  POST   /admin/suppliers/{code}/feed/inspect — headers of a file feed

A supplier of kind ``api`` must name a registered ``adapter_key``; a ``file``
supplier's ``column_mapping`` must at least map the two required fields.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.core.secrets_box import encrypt_json
from app.features.integrations.models.supplier import (
    FILE_MAPPING_REQUIRED,
    FILE_MAPPING_TARGETS,
    AdapterDescriptor,
    Supplier,
    SupplierCreate,
    SupplierKind,
    SupplierPublic,
    SuppliersPublic,
    SupplierUpdate,
)
from app.features.integrations.models.supplier_category_mapping import (
    CategoryMappingPublic,
    CategoryMappingWrite,
    ObservedCategory,
)
from app.features.integrations.services.category_mapping import (
    delete_mapping,
    describe_pairs,
    list_mappings,
    observed_pairs,
    reapply_mappings,
    save_mappings,
)
from app.features.integrations.services.sku_allowlist import (
    AllowlistView,
    AllowlistWrite,
    allowlist_view,
    save_allowlist,
)
from app.features.integrations.services.supplier_sync_orchestrator import (
    global_filter_action,
)
from app.features.place.models import Place
from app.features.product.models.product import Product
from app.services.suppliers import (
    ADAPTERS,
    adapter_for_supplier,
    describe_adapters,
    forget_adapter,
    has_adapter,
)
from app.services.suppliers.file_feed import FeedError, FileFeedAdapter
from app.services.suppliers.file_import import validate_mapping
from app.tasks.pricing_tasks import schedule_price_refresh

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/suppliers", tags=["admin-suppliers"])


class ReapplyResult(BaseModel):
    """Products moved to their mapped category / taken off the storefront."""

    moved: int
    deactivated: int


def _public(supplier: Supplier) -> SupplierPublic:
    configured = True
    if supplier.kind == SupplierKind.API:
        configured = (
            has_adapter(supplier.adapter_key)
            and ADAPTERS[str(supplier.adapter_key)].credentials_present()
        )
    if configured and supplier.kind == SupplierKind.API:
        # Instance-level checks (a file feed: its URL, login and mapping).
        try:
            configured = adapter_for_supplier(supplier).is_configured()
        except Exception:  # noqa: BLE001 - a listing never fails on one row
            configured = False
    public = SupplierPublic.model_validate(supplier)
    public.configured = configured
    public.has_credentials = bool(supplier.credentials_encrypted)
    return public


async def _load(session: SessionDep, code: str) -> Supplier:
    result = await session.exec(select(Supplier).where(Supplier.code == code))
    supplier = result.first()
    if supplier is None:
        raise AppError(
            code="supplier.not_found",
            status_code=404,
            message=f"Unknown supplier '{code}'",
            details={"supplier_name": code},
        )
    return supplier


async def _validate(session: SessionDep, supplier: Supplier) -> None:
    """Cross-field checks shared by create and update."""
    if supplier.kind == SupplierKind.API:
        if not has_adapter(supplier.adapter_key):
            raise AppError(
                code="supplier.adapter.unknown",
                status_code=400,
                message=(
                    f"No integration registered under adapter_key "
                    f"{supplier.adapter_key!r}. Available: {', '.join(sorted(ADAPTERS))}"
                ),
                details={
                    "adapter_key": supplier.adapter_key,
                    "available": sorted(ADAPTERS),
                },
            )
        if supplier.auto_purchase_order and not (
            ADAPTERS[str(supplier.adapter_key)].supports_purchase_orders
        ):
            raise AppError(
                code="supplier.purchase_orders.unsupported",
                status_code=400,
                message=(
                    f"L'intégration {supplier.adapter_key} ne sait pas passer de "
                    "commande fournisseur"
                ),
                details={"adapter_key": supplier.adapter_key},
            )
        feed_url = (supplier.settings or {}).get("feed_url")
        if feed_url and not str(feed_url).lower().startswith("https://"):
            raise AppError(
                code="supplier.feed.https_required",
                status_code=400,
                message="L'adresse du fichier doit commencer par https://",
                details={"feed_url": str(feed_url)},
            )
        allowed = set(ADAPTERS[str(supplier.adapter_key)].settings_keys)
        unknown = sorted(set(supplier.settings or {}) - allowed)
        if unknown:
            raise AppError(
                code="supplier.settings.unknown_keys",
                status_code=400,
                message=f"Unknown settings for {supplier.adapter_key}: {', '.join(unknown)}",
                details={"unknown": unknown, "allowed": sorted(allowed)},
            )
    if supplier.kind in (SupplierKind.FILE, SupplierKind.API) and (
        supplier.column_mapping
    ):
        problems = validate_mapping(supplier.column_mapping)
        if problems:
            raise AppError(
                code="supplier.import.mapping_invalid",
                status_code=400,
                message="; ".join(problems),
                details={"problems": problems},
            )
    if supplier.origin_place_id is not None:
        place = await session.get(Place, supplier.origin_place_id)
        if place is None:
            raise AppError(
                code="supplier.origin_place.not_found",
                status_code=400,
                message=f"Place '{supplier.origin_place_id}' does not exist",
                details={"origin_place_id": str(supplier.origin_place_id)},
            )


@router.get("", response_model=SuppliersPublic)
async def list_suppliers(
    session: SessionDep, _current_user: CurrentSuperUser
) -> SuppliersPublic:
    """Every declared supplier, active or not."""
    result = await session.exec(select(Supplier).order_by(col(Supplier.name).asc()))
    rows = list(result.all())
    return SuppliersPublic(data=[_public(s) for s in rows], count=len(rows))


@router.get("/adapters", response_model=list[AdapterDescriptor])
async def list_adapters(_current_user: CurrentSuperUser) -> list[AdapterDescriptor]:
    """Integrations available in the code, for the ``adapter_key`` dropdown."""
    return describe_adapters()


@router.post("", response_model=SupplierPublic, status_code=201)
async def create_supplier(
    payload: SupplierCreate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> SupplierPublic:
    """Declare a supplier."""
    # Read before any commit: the session expires ORM instances on commit and
    # a lazy reload of ``current_user`` would then fail in async mode.
    actor_id = current_user.id
    supplier = Supplier.model_validate(payload)
    await _validate(session, supplier)
    session.add(supplier)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            code="supplier.code.conflict",
            status_code=409,
            message=f"A supplier with code '{payload.code}' already exists",
            details={"code": payload.code},
        ) from exc
    await session.refresh(supplier)
    logger.info("Admin %s created supplier %s", actor_id, supplier.code)
    return _public(supplier)


@router.get("/{code}", response_model=SupplierPublic)
async def get_supplier(
    code: str, session: SessionDep, _current_user: CurrentSuperUser
) -> SupplierPublic:
    """One supplier by code."""
    return _public(await _load(session, code))


@router.patch("/{code}", response_model=SupplierPublic)
async def update_supplier(
    code: str,
    payload: SupplierUpdate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> SupplierPublic:
    """Partial update; the adapter instance is rebuilt on the next use."""
    actor_id = current_user.id
    supplier = await _load(session, code)
    fields = payload.model_dump(exclude_unset=True)
    for name, value in fields.items():
        setattr(supplier, name, value)
    supplier.updated_at = datetime.now(timezone.utc)
    await _validate(session, supplier)
    session.add(supplier)
    await session.commit()
    await session.refresh(supplier)
    forget_adapter(supplier.code)
    logger.info("Admin %s updated supplier %s: %s", actor_id, code, sorted(fields))
    return _public(supplier)


@router.get("/{code}/sku-allowlist", response_model=AllowlistView)
async def get_sku_allowlist(
    code: str, session: SessionDep, _current_user: CurrentSuperUser
) -> AllowlistView:
    """The references the shop follows at this supplier, against its catalogue."""
    return await allowlist_view(session, await _load(session, code))


@router.put("/{code}/sku-allowlist", response_model=AllowlistView)
async def put_sku_allowlist(
    code: str,
    payload: AllowlistWrite,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> AllowlistView:
    """Replace the list (empty clears it: the whole catalogue is followed).

    Managed products outside a non-empty list leave the storefront now; the
    listed ones are created or refreshed by the next syncs.
    """
    actor_id = current_user.id
    supplier = await _load(session, code)
    view = await save_allowlist(session, supplier, payload.skus)
    await session.commit()
    forget_adapter(code)
    logger.info(
        "Admin %s set the SKU allowlist of %s: %d references, %d products hidden",
        actor_id,
        code,
        len(view.entries),
        view.deactivated,
    )
    return view


class SupplierCredentialsWrite(BaseModel):
    """Portal login of a file-feed supplier (write-only)."""

    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=500)


class FeedInspection(BaseModel):
    """First rows of a supplier's feed, to build the column mapping (same
    shape as the inspection of an uploaded file)."""

    filename: str = "flux"
    headers: list[str]
    sample_rows: list[dict[str, str]]
    total_rows: int
    mapping_targets: list[str] = Field(
        default_factory=lambda: list(FILE_MAPPING_TARGETS)
    )
    required_targets: list[str] = Field(
        default_factory=lambda: list(FILE_MAPPING_REQUIRED)
    )
    mapping_problems: list[str] = Field(default_factory=list)


@router.put("/{code}/credentials", response_model=SupplierPublic)
async def put_supplier_credentials(
    code: str,
    payload: SupplierCredentialsWrite,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> SupplierPublic:
    """Store the supplier's portal login, encrypted. Never read back."""
    actor_id = current_user.id
    supplier = await _load(session, code)
    supplier.credentials_encrypted = encrypt_json(
        {"username": payload.username, "password": payload.password}
    )
    supplier.updated_at = datetime.now(timezone.utc)
    session.add(supplier)
    await session.commit()
    await session.refresh(supplier)
    forget_adapter(code)
    logger.info("Admin %s stored credentials for supplier %s", actor_id, code)
    return _public(supplier)


@router.delete("/{code}/credentials", response_model=SupplierPublic)
async def delete_supplier_credentials(
    code: str, session: SessionDep, current_user: CurrentSuperUser
) -> SupplierPublic:
    """Forget the supplier's stored login."""
    actor_id = current_user.id
    supplier = await _load(session, code)
    supplier.credentials_encrypted = None
    supplier.updated_at = datetime.now(timezone.utc)
    session.add(supplier)
    await session.commit()
    await session.refresh(supplier)
    forget_adapter(code)
    logger.info("Admin %s removed the credentials of supplier %s", actor_id, code)
    return _public(supplier)


@router.post("/{code}/feed/inspect", response_model=FeedInspection)
async def inspect_supplier_feed(
    code: str, session: SessionDep, _current_user: CurrentSuperUser
) -> FeedInspection:
    """Download the supplier's feed and return its headers and first rows."""
    supplier = await _load(session, code)
    adapter = (
        adapter_for_supplier(supplier) if has_adapter(supplier.adapter_key) else None
    )
    if not isinstance(adapter, FileFeedAdapter):
        raise AppError(
            code="supplier.feed.not_a_feed",
            status_code=400,
            message=f"{supplier.name} n'est pas un fournisseur par fichier en ligne",
            details={"supplier_name": code},
        )
    try:
        headers, rows, total = await adapter.inspect()
    except FeedError as exc:
        raise AppError(
            code="supplier.feed.unreachable",
            status_code=502,
            message=str(exc),
            details={"supplier_name": code},
        ) from exc
    problems = (
        validate_mapping(supplier.column_mapping, headers)
        if supplier.column_mapping
        else []
    )
    return FeedInspection(
        headers=headers, sample_rows=rows, total_rows=total, mapping_problems=problems
    )


@router.get("/{code}/category-mappings", response_model=list[CategoryMappingPublic])
async def get_category_mappings(
    code: str, session: SessionDep, _current_user: CurrentSuperUser
) -> list[CategoryMappingPublic]:
    """The supplier's category rules (source couple → shop category, action)."""
    return await list_mappings(session, await _load(session, code))


@router.put("/{code}/category-mappings", response_model=list[CategoryMappingPublic])
async def put_category_mappings(
    code: str,
    payload: list[CategoryMappingWrite],
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> list[CategoryMappingPublic]:
    """Create or replace the listed rules (keyed by their source couple).

    Rules not listed stay. Products already in base are not moved: see
    ``POST …/category-mappings/reapply``.
    """
    actor_id = current_user.id
    supplier = await _load(session, code)
    rules = await save_mappings(session, supplier, payload)
    await session.commit()
    logger.info("Admin %s saved %d category rules for %s", actor_id, len(payload), code)
    return rules


@router.delete("/{code}/category-mappings/{mapping_id}", status_code=204)
async def remove_category_mapping(
    code: str,
    mapping_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> None:
    """Remove one rule: its couple falls back to the unmapped behaviour."""
    actor_id = current_user.id
    await delete_mapping(session, await _load(session, code), mapping_id)
    await session.commit()
    logger.info("Admin %s removed category rule %s of %s", actor_id, mapping_id, code)


@router.post("/{code}/category-mappings/reapply", response_model=ReapplyResult)
async def reapply_category_mappings(
    code: str, session: SessionDep, current_user: CurrentSuperUser
) -> ReapplyResult:
    """Apply the rules to the supplier's products already in base.

    Products move to their target category (unless their category was set by
    hand), couples set to « hors vitrine » / « ignorer » leave the storefront;
    list prices are refreshed for the moved products.
    """
    actor_id = current_user.id
    counts = await reapply_mappings(session, await _load(session, code))
    await session.commit()
    if counts["moved"]:
        await schedule_price_refresh(reason=f"category_mapping:{code}")
    logger.info(
        "Admin %s reapplied the category rules of %s: %s", actor_id, code, counts
    )
    return ReapplyResult(**counts)


@router.get("/{code}/observed-categories", response_model=list[ObservedCategory])
async def get_observed_categories(
    code: str, session: SessionDep, _current_user: CurrentSuperUser
) -> list[ObservedCategory]:
    """The (category, subcategory) couples of the supplier's products in base,
    with their count, their rule and where the next sync would put them."""
    supplier = await _load(session, code)
    return await describe_pairs(
        session,
        supplier.code,
        await observed_pairs(session, supplier.code),
        global_effect=_global_effect(supplier.code),
    )


def _global_effect(code: str) -> Any:
    def _effect(
        category: str | None, subcategory: str | None, has_rules: bool
    ) -> str | None:
        return global_filter_action(
            code,
            category=category,
            subcategory=subcategory,
            supplier_has_rules=has_rules,
        )

    return _effect


@router.delete("/{code}", response_model=SupplierPublic)
async def deactivate_supplier(
    code: str,
    session: SessionDep,
    current_user: CurrentSuperUser,
    products: Annotated[
        Literal["keep", "zero_stock", "hide"],
        Query(
            description=(
                "What happens to the supplier's products: keep (as they are), "
                "zero_stock (supplier stock set to 0: no longer sold on it), "
                "hide (zero_stock and taken off the storefront)"
            )
        ),
    ] = "keep",
) -> SupplierPublic:
    """Deactivate a supplier (its products keep their ``supplier_name``).

    Nothing is deleted: the code stays reserved so the links from products,
    mappings, sync logs and supplier orders keep resolving. A product keeps
    selling its last synced supplier stock unless ``products`` says otherwise:
    nobody refreshes it any more.
    """
    actor_id = current_user.id
    supplier = await _load(session, code)
    count_result = await session.exec(
        select(func.count(col(Product.id))).where(Product.supplier_name == code)
    )
    linked = int(count_result.one())
    supplier.is_active = False
    supplier.sync_enabled = False
    supplier.updated_at = datetime.now(timezone.utc)
    session.add(supplier)
    withdrawn: int | None = None
    if products != "keep":
        values: dict[str, Any] = {"supplier_quantity": Decimal("0")}
        if products == "hide":
            values["is_active"] = False
        result = await session.exec(
            sa_update(Product)
            .where(col(Product.supplier_name) == code)
            .values(**values)
        )
        withdrawn = int(result.rowcount or 0)
    await session.commit()
    await session.refresh(supplier)
    forget_adapter(code)
    logger.warning(
        "Admin %s deactivated supplier %s (%d linked products, products=%s)",
        actor_id,
        code,
        linked,
        products,
    )
    public = _public(supplier)
    public.products_withdrawn = withdrawn
    return public


__all__ = ["router", "adapter_for_supplier"]
