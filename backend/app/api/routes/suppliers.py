"""
Generic supplier integration routes.

One router serves every supplier declared in the ``suppliers`` table; the
``{supplier_name}`` path parameter is the supplier ``code``. API-backed
suppliers (kind ``api``) expose catalog / inventory sync triggers and a health
probe; every supplier accepts a CSV / Excel catalog upload
(``/import-file``), which is how ``file`` suppliers are fed.

Declaring suppliers is the job of ``/admin/suppliers`` (admin_suppliers.py).
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.config import settings
from app.core.errors import AppError
from app.features.attachment.storage.factory import get_file_storage
from app.features.base.crud import RecordNotFoundError
from app.features.integrations.crud.supplier_sync import supplier_sync_log_crud
from app.features.integrations.models.supplier import (
    FILE_MAPPING_REQUIRED,
    FILE_MAPPING_TARGETS,
    Supplier,
    SupplierKind,
)
from app.features.integrations.models.supplier_sync import SyncStatus, SyncType
from app.features.integrations.services.file_import_run import (
    ERROR_SAMPLE_SIZE,
    orchestrator_for_file_import,
    run_file_import,
)
from app.services.suppliers import (
    SupplierAdapter,
    adapter_for_supplier,
    has_adapter,
    load_supplier,
)
from app.services.suppliers import (
    list_suppliers as list_supplier_rows,
)
from app.services.suppliers.base import SupplierConfig
from app.services.suppliers.file_import import (
    MAX_ROWS,
    FileImportError,
    read_tabular_file,
    rows_to_products,
    validate_mapping,
)
from app.tasks.supplier_file_import_tasks import (
    build_import_storage_key,
    trigger_file_import,
)
from app.tasks.supplier_tasks import (
    backfill_product_categories_task,
    trigger_inventory_refresh,
    trigger_manual_sync,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

#: Upload size cap for catalog files (bytes).
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


async def get_supplier(
    supplier_name: Annotated[str, Path(description="Supplier code")],
    session: SessionDep,
) -> Supplier:
    """Load the active supplier row for ``supplier_name`` (404 otherwise)."""
    supplier = await load_supplier(session, supplier_name)
    if supplier is None:
        registered = [row.code for row in await list_supplier_rows(session)]
        raise AppError(
            code="supplier.not_found",
            status_code=404,
            message=f"Unknown supplier '{supplier_name}'. "
            f"Registered: {', '.join(registered)}",
            details={"supplier_name": supplier_name, "registered": registered},
        )
    return supplier


SupplierDep = Annotated[Supplier, Depends(get_supplier)]


def get_supplier_adapter(supplier: SupplierDep) -> SupplierAdapter:
    """Build the live adapter of an API supplier (400 for manual / file ones)."""
    if supplier.kind != SupplierKind.API or not has_adapter(supplier.adapter_key):
        raise AppError(
            code="supplier.not_api",
            status_code=400,
            message=(
                f"Supplier '{supplier.code}' has no live API integration "
                f"(kind={supplier.kind.value}, adapter_key={supplier.adapter_key!r})"
            ),
            details={
                "supplier_name": supplier.code,
                "kind": supplier.kind.value,
                "adapter_key": supplier.adapter_key,
            },
        )
    return adapter_for_supplier(supplier)


AdapterDep = Annotated[SupplierAdapter, Depends(get_supplier_adapter)]


# -- schemas --------------------------------------------------------------


class SupplierSummary(BaseModel):
    """Represents supplier summary."""

    name: str
    display_name: str
    kind: SupplierKind
    configured: bool
    sync_enabled: bool
    is_domestic: bool = False
    default_categories: list[str] = Field(default_factory=list)


class SyncRequest(BaseModel):
    """Represents sync request."""

    categories: list[str] | None = Field(
        default=None,
        description="Categories to sync (defaults to the supplier's configured list)",
    )


class InventoryRefreshRequest(BaseModel):
    """Represents inventory refresh request."""

    skus: list[str] | None = Field(
        default=None,
        description="Specific SKUs to refresh (defaults to all stale products)",
    )


class SyncResponse(BaseModel):
    """Represents sync response."""

    job_id: str
    supplier_name: str
    status: str
    message: str
    timestamp: datetime


class HealthResponse(BaseModel):
    """Represents health response."""

    supplier_name: str
    status: str
    api_responsive: bool
    configuration_valid: bool
    last_sync: datetime | None = None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class FileInspectResponse(BaseModel):
    """Headers and sample rows of an uploaded catalog file (mapping helper)."""

    filename: str
    headers: list[str]
    sample_rows: list[dict[str, str]]
    total_rows: int
    mapping_targets: list[str] = Field(
        default_factory=lambda: list(FILE_MAPPING_TARGETS)
    )
    required_targets: list[str] = Field(
        default_factory=lambda: list(FILE_MAPPING_REQUIRED)
    )
    #: Problems of the supplier's stored mapping against these headers.
    mapping_problems: list[str] = Field(default_factory=list)


class FileImportRowError(BaseModel):
    """A rejected row."""

    row_number: int
    message: str


class FileImportResolutionRow(BaseModel):
    """How one parsed row would be (or was) matched against the catalog."""

    supplier_sku: str
    name: str
    #: new | updated | adopted | ambiguous | skipped
    action: str
    #: mapping | supplier_sku | gtin | manufacturer_part | null
    match_key: str | None = None
    product_id: str | None = None
    product_name: str | None = None
    message: str | None = None


class FileImportResponse(BaseModel):
    """Outcome of a catalog file import (or of its dry run)."""

    supplier_name: str
    filename: str
    dry_run: bool
    total_rows: int
    parsed_products: int
    rejected_rows: int
    row_errors: list[FileImportRowError] = Field(default_factory=list)
    statistics: dict[str, int] = Field(default_factory=dict)
    sync_errors: list[dict[str, str]] = Field(default_factory=list)
    sync_log_id: str | None = None
    #: Created / adopted rows were published as the file describes them.
    published_new: bool = False
    #: Large file: stored and handed to the worker; poll the status endpoint
    #: with ``sync_log_id``. ``statistics`` is empty until it completes.
    queued: bool = False
    job_id: str | None = None
    message: str | None = None
    sample: list[dict[str, Any]] = Field(default_factory=list)
    #: Dry run only: counters of the resolution step (new / updated / adopted /
    #: ambiguous / skipped and matched_by_<key>).
    resolution: dict[str, int] = Field(default_factory=dict)
    sample_resolutions: list[FileImportResolutionRow] = Field(default_factory=list)
    #: Dry run of a large file: only the first N rows were resolved.
    resolution_limited_to: int | None = None


class FileImportStatusResponse(BaseModel):
    """Progress and outcome of a queued catalog file import (its sync log)."""

    sync_log_id: str
    supplier_name: str
    status: SyncStatus
    filename: str | None = None
    total_rows: int | None = None
    parsed_products: int | None = None
    rejected_rows: int | None = None
    row_errors: list[FileImportRowError] = Field(default_factory=list)
    statistics: dict[str, int] = Field(default_factory=dict)
    sync_errors: list[dict[str, str]] = Field(default_factory=list)
    published_new: bool = False
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


# -- routes ---------------------------------------------------------------


@router.get("", response_model=list[SupplierSummary])
async def list_suppliers(
    session: SessionDep, _current_user: CurrentSuperUser
) -> list[SupplierSummary]:
    """List all declared suppliers and their configuration status.

    **Required permissions:** Superuser only
    """
    summaries = []
    for supplier in await list_supplier_rows(session):
        configured = True
        if supplier.kind == SupplierKind.API:
            configured = (
                has_adapter(supplier.adapter_key)
                and adapter_for_supplier(supplier).is_configured()
            )
        summaries.append(
            SupplierSummary(
                name=supplier.code,
                display_name=supplier.name,
                kind=supplier.kind,
                configured=configured,
                sync_enabled=supplier.sync_enabled,
                is_domestic=supplier.is_domestic,
                default_categories=list(supplier.default_categories or []),
            )
        )
    return summaries


def _ensure_sync_allowed(adapter: SupplierAdapter) -> None:
    if not adapter.is_sync_enabled():
        raise AppError(
            code="supplier.sync.disabled",
            status_code=400,
            message=f"{adapter.supplier_display_name} synchronization is disabled in settings",
            details={"supplier_name": adapter.name},
        )
    if not adapter.is_configured():
        raise AppError(
            code="supplier.credentials.not_configured",
            status_code=500,
            message=f"{adapter.supplier_display_name} credentials not configured",
            details={"supplier_name": adapter.name},
        )


@router.post("/{supplier_name}/sync/products", response_model=SyncResponse)
async def trigger_product_sync(
    adapter: AdapterDep,
    request: SyncRequest,
    _current_user: CurrentSuperUser,
) -> SyncResponse:
    """Queue a catalog synchronization for the supplier.

    **Required permissions:** Superuser only
    """
    _ensure_sync_allowed(adapter)

    categories = request.categories or list(adapter.default_categories)
    try:
        job_id = await trigger_manual_sync(adapter.name, categories=categories)
    except Exception as e:
        raise AppError(
            code="supplier.sync.queue_failed",
            status_code=500,
            message=f"Failed to queue product sync: {e}",
            details={
                "supplier_name": adapter.name,
                "sync_type": "product_catalog",
                "reason": str(e),
            },
        ) from e

    return SyncResponse(
        job_id=job_id,
        supplier_name=adapter.name,
        status="queued",
        message=f"Product sync queued for categories: {categories}",
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/{supplier_name}/sync/inventory", response_model=SyncResponse)
async def trigger_inventory_sync(
    adapter: AdapterDep,
    request: InventoryRefreshRequest,
    _current_user: CurrentSuperUser,
) -> SyncResponse:
    """Queue a price & availability refresh for the supplier.

    **Required permissions:** Superuser only
    """
    _ensure_sync_allowed(adapter)

    try:
        job_id = await trigger_inventory_refresh(adapter.name, skus=request.skus)
    except Exception as e:
        raise AppError(
            code="supplier.sync.queue_failed",
            status_code=500,
            message=f"Failed to queue inventory refresh: {e}",
            details={
                "supplier_name": adapter.name,
                "sync_type": "inventory",
                "reason": str(e),
            },
        ) from e

    count = len(request.skus) if request.skus else "all stale"
    return SyncResponse(
        job_id=job_id,
        supplier_name=adapter.name,
        status="queued",
        message=f"Inventory refresh queued for {count} products",
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/{supplier_name}/health", response_model=HealthResponse)
async def check_supplier_health(
    adapter: AdapterDep,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> HealthResponse:
    """Check the supplier API health, configuration and last successful sync.

    **Required permissions:** Superuser only
    """
    last_successful_sync = await supplier_sync_log_crud.get_last_successful_sync(
        session=session,
        supplier_name=adapter.name,
        sync_type=SyncType.PRODUCT_CATALOG,
    )
    last_sync = (
        (last_successful_sync.completed_at or last_successful_sync.started_at)
        if last_successful_sync
        else None
    )

    health = await adapter.health_check()
    if not health.configured:
        status = "misconfigured"
    elif not adapter.is_sync_enabled():
        status = "disabled"
    elif health.healthy:
        status = "healthy"
    else:
        status = "unhealthy"

    return HealthResponse(
        supplier_name=adapter.name,
        status=status,
        api_responsive=health.healthy,
        configuration_valid=health.configured,
        last_sync=last_sync,
        message=health.message,
        details=health.details,
    )


@router.get("/{supplier_name}/config")
async def get_supplier_config(
    supplier: SupplierDep,
    _current_user: CurrentSuperUser,
) -> dict[str, Any]:
    """Get the supplier's (credential-free) configuration.

    **Required permissions:** Superuser only
    """
    if supplier.kind == SupplierKind.API and has_adapter(supplier.adapter_key):
        return adapter_for_supplier(supplier).config_summary()
    config = SupplierConfig.from_row(supplier)
    return {
        "name": config.code,
        "display_name": config.display_name,
        "kind": config.kind,
        "adapter_key": config.adapter_key,
        "configured": True,
        "sync_enabled": config.sync_enabled,
        "sync_interval_hours": config.sync_interval_hours,
        "default_categories": list(config.default_categories),
        "is_domestic": config.is_domestic,
        "origin_place_id": (
            str(config.origin_place_id) if config.origin_place_id else None
        ),
        "price_currency": config.price_currency,
        "column_mapping": config.column_mapping,
        "settings": dict(config.settings),
    }


@router.get("/{supplier_name}/categories", response_model=list[str])
async def get_supplier_categories(
    supplier: SupplierDep,
    _current_user: CurrentSuperUser,
) -> list[str]:
    """Get the supplier's configured default categories.

    **Required permissions:** Superuser only
    """
    return list(supplier.default_categories or [])


# -- file import ------------------------------------------------------------


async def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    filename = file.filename or "catalogue.csv"
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise AppError(
            code="supplier.import.file_too_large",
            status_code=413,
            message=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
            details={"filename": filename, "size": len(content)},
        )
    return filename, content


def _parse_mapping_field(raw: str | None) -> dict[str, str] | None:
    if raw is None or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="supplier.import.mapping_invalid",
            status_code=400,
            message=f"mapping is not valid JSON: {exc}",
            details={"mapping": raw[:200]},
        ) from exc
    if not isinstance(parsed, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
    ):
        raise AppError(
            code="supplier.import.mapping_invalid",
            status_code=400,
            message="mapping must be a JSON object of {internal_field: column}",
            details={},
        )
    return {k: v for k, v in parsed.items() if v}


@router.post("/{supplier_name}/import-file/inspect", response_model=FileInspectResponse)
async def inspect_catalog_file(
    supplier: SupplierDep,
    _current_user: CurrentSuperUser,
    file: UploadFile = File(...),
) -> FileInspectResponse:
    """Read the headers and a few rows of a catalog file, to build the mapping.

    **Required permissions:** Superuser only
    """
    filename, content = await _read_upload(file)
    try:
        parsed = read_tabular_file(content, filename, max_rows=5)
    except FileImportError as exc:
        raise AppError(
            code="supplier.import.unreadable",
            status_code=400,
            message=str(exc),
            details={"filename": filename},
        ) from exc

    problems = (
        validate_mapping(supplier.column_mapping, parsed.headers)
        if supplier.column_mapping
        else []
    )
    return FileInspectResponse(
        filename=filename,
        headers=parsed.headers,
        sample_rows=parsed.rows,
        total_rows=parsed.total_rows,
        mapping_problems=problems,
    )


@router.post("/{supplier_name}/import-file", response_model=FileImportResponse)
async def import_catalog_file(
    supplier: SupplierDep,
    session: SessionDep,
    current_user: CurrentSuperUser,
    file: UploadFile = File(...),
    mapping: str | None = Form(
        default=None,
        description="JSON {internal_field: column}; defaults to the supplier's mapping",
    ),
    dry_run: bool = Query(
        default=False, description="Parse and report without writing anything"
    ),
    # Annotated so a direct call (tests) gets a real default, not the Form marker.
    publish_new: Annotated[
        bool,
        Form(
            description=(
                "Show the created (and adopted) products on the storefront "
                "without waiting for Icecat enrichment"
            ),
        ),
    ] = True,
) -> FileImportResponse:
    """Import a CSV / Excel catalog for the supplier through the column mapping.

    Up to ``SUPPLIER_FILE_IMPORT_INLINE_MAX_ROWS`` rows the import runs inline:
    each product is committed as it is upserted, so a failure on one row never
    rolls back the others. A larger file is stored and imported by the worker
    (``queued`` response; poll ``GET …/import-file/{sync_log_id}``). Newly
    created products are queued for Icecat enrichment like API-synced ones;
    with ``publish_new`` (the default) they are visible on the storefront
    meanwhile, as the file describes them.

    **Required permissions:** Superuser only
    """
    filename, content = await _read_upload(file)
    content_type = file.content_type or "application/octet-stream"
    # Captured before the per-product commits expire the session's instances.
    actor_id = current_user.id
    supplier_code = supplier.code
    supplier_currency = supplier.price_currency
    orchestrator = orchestrator_for_file_import(supplier)
    effective_mapping = _parse_mapping_field(mapping) or supplier.column_mapping

    try:
        parsed = read_tabular_file(content, filename, max_rows=MAX_ROWS)
    except FileImportError as exc:
        raise AppError(
            code="supplier.import.unreadable",
            status_code=400,
            message=str(exc),
            details={"filename": filename},
        ) from exc

    problems = validate_mapping(effective_mapping, parsed.headers)
    if problems or effective_mapping is None:
        raise AppError(
            code="supplier.import.mapping_invalid",
            status_code=400,
            message="; ".join(problems) or "Aucun mapping de colonnes défini",
            details={"problems": problems, "headers": parsed.headers},
        )
    if parsed.total_rows > MAX_ROWS:
        raise AppError(
            code="supplier.import.too_many_rows",
            status_code=413,
            message=f"File has {parsed.total_rows} rows; the limit is {MAX_ROWS}",
            details={"total_rows": parsed.total_rows, "limit": MAX_ROWS},
        )

    inline_limit = settings.SUPPLIER_FILE_IMPORT_INLINE_MAX_ROWS
    if not dry_run and parsed.total_rows > inline_limit:
        return await _queue_file_import(
            session,
            supplier_code=supplier_code,
            actor_id=actor_id,
            filename=filename,
            content=content,
            content_type=content_type,
            mapping=effective_mapping,
            publish_new=publish_new,
            total_rows=parsed.total_rows,
        )

    result = rows_to_products(
        parsed.rows, effective_mapping, default_currency=supplier_currency
    )
    row_errors = [
        FileImportRowError(row_number=e.row_number, message=e.message)
        for e in result.errors[:ERROR_SAMPLE_SIZE]
    ]
    sample = [
        {
            "supplier_sku": p.supplier_sku,
            "name": p.name,
            "manufacturer": p.manufacturer,
            "price": str(p.price) if p.price is not None else None,
            "currency": p.currency,
            "quantity": str(p.quantity) if p.quantity is not None else None,
            "category": p.category,
            "subcategory": p.subcategory,
        }
        for p in result.products[:5]
    ]

    if dry_run:
        # Resolution reads the catalog row by row: a large file is previewed
        # on its first rows only, the real import runs in the worker.
        limited = len(result.products) > inline_limit
        counts, resolved_rows = await orchestrator.preview_items(
            session, result.products[:inline_limit]
        )
        return FileImportResponse(
            supplier_name=supplier_code,
            filename=filename,
            dry_run=True,
            total_rows=parsed.total_rows,
            parsed_products=len(result.products),
            rejected_rows=len(result.errors),
            row_errors=row_errors,
            sample=sample,
            resolution=counts,
            sample_resolutions=[
                FileImportResolutionRow.model_validate(r) for r in resolved_rows
            ],
            resolution_limited_to=inline_limit if limited else None,
        )

    sync_log = await supplier_sync_log_crud.create_sync_log(
        session=session,
        supplier_name=supplier_code,
        sync_type=SyncType.PRODUCT_CATALOG,
        categories=None,
        created_by=actor_id,
    )
    sync_log_id = sync_log.id

    try:
        outcome = await run_file_import(
            session,
            orchestrator=orchestrator,
            products=result.products,
            row_errors=result.errors,
            sync_log_id=sync_log_id,
            filename=filename,
            total_rows=parsed.total_rows,
            publish_new=publish_new,
        )
    except Exception as exc:
        raise AppError(
            code="supplier.import.failed",
            status_code=500,
            message=f"Import failed: {exc}",
            details={"supplier_name": supplier_code, "filename": filename},
        ) from exc

    logger.info(
        "Catalog file %s imported inline for %s by %s",
        filename,
        supplier_code,
        actor_id,
    )
    return FileImportResponse(
        supplier_name=supplier_code,
        filename=filename,
        dry_run=False,
        total_rows=parsed.total_rows,
        parsed_products=len(result.products),
        rejected_rows=len(result.errors),
        row_errors=row_errors,
        statistics=outcome.statistics,
        sync_errors=outcome.sync_errors[:ERROR_SAMPLE_SIZE],
        sync_log_id=str(sync_log_id),
        published_new=publish_new,
        sample=sample,
    )


async def _queue_file_import(
    session: SessionDep,
    *,
    supplier_code: str,
    actor_id: uuid.UUID,
    filename: str,
    content: bytes,
    content_type: str,
    mapping: dict[str, str],
    publish_new: bool,
    total_rows: int,
) -> FileImportResponse:
    """Store the file, open its sync log and hand the import to the worker.

    The sync log exists before the job so the admin can poll it right away;
    a storage or queue failure closes it ``FAILED`` and answers 503 — nothing
    was imported, the admin can retry.
    """
    sync_log = await supplier_sync_log_crud.create_sync_log(
        session=session,
        supplier_name=supplier_code,
        sync_type=SyncType.PRODUCT_CATALOG,
        categories=None,
        created_by=actor_id,
    )
    sync_log_id = sync_log.id
    storage_key = build_import_storage_key(supplier_code, sync_log_id, filename)
    storage = get_file_storage()
    try:
        await storage.put_bytes(
            key=storage_key, data=content, content_type=content_type
        )
        job_id = await trigger_file_import(
            sync_log_id=sync_log_id,
            supplier_code=supplier_code,
            storage_key=storage_key,
            filename=filename,
            mapping=mapping,
            publish_new=publish_new,
        )
    except Exception as exc:
        logger.error(
            "Could not queue catalog file %s for %s: %s", filename, supplier_code, exc
        )
        await supplier_sync_log_crud.complete_sync(
            session=session,
            sync_log_id=sync_log_id,
            status=SyncStatus.FAILED,
            error_message=f"Mise en file d'attente impossible : {exc}",
        )
        try:
            await storage.delete(key=storage_key)
        except Exception:  # noqa: BLE001 - best effort cleanup
            logger.warning("Stored import file %s left behind", storage_key)
        raise AppError(
            code="supplier.import.queue_unavailable",
            status_code=503,
            message="L'import en tâche de fond est indisponible ; réessayez plus tard",
            details={"supplier_name": supplier_code, "filename": filename},
        ) from exc

    await supplier_sync_log_crud.update(
        session=session, id=sync_log_id, data={"job_id": job_id}
    )
    logger.info(
        "Catalog file %s (%d rows) queued for %s by %s: job %s, sync log %s",
        filename,
        total_rows,
        supplier_code,
        actor_id,
        job_id,
        sync_log_id,
    )
    return FileImportResponse(
        supplier_name=supplier_code,
        filename=filename,
        dry_run=False,
        total_rows=total_rows,
        parsed_products=0,
        rejected_rows=0,
        sync_log_id=str(sync_log_id),
        published_new=publish_new,
        queued=True,
        job_id=job_id,
        message=(
            f"{total_rows} lignes : import lancé en tâche de fond, "
            "suivez son avancement ici"
        ),
    )


@router.get(
    "/{supplier_name}/import-file/{sync_log_id}",
    response_model=FileImportStatusResponse,
)
async def get_catalog_import_status(
    supplier: SupplierDep,
    session: SessionDep,
    _current_user: CurrentSuperUser,
    sync_log_id: uuid.UUID,
) -> FileImportStatusResponse:
    """Progress and outcome of a file import, queued or inline (its sync log).

    **Required permissions:** Superuser only
    """
    try:
        log = await supplier_sync_log_crud.read(session, id=sync_log_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="supplier.import.not_found",
            status_code=404,
            message=f"Import {sync_log_id} not found",
            details={"sync_log_id": str(sync_log_id)},
        ) from exc
    if log.supplier_name != supplier.code:
        raise AppError(
            code="supplier.import.not_found",
            status_code=404,
            message=f"Import {sync_log_id} not found for {supplier.code}",
            details={"sync_log_id": str(sync_log_id), "supplier_name": supplier.code},
        )

    stats: dict[str, Any] = dict(log.statistics or {})
    row_errors = stats.pop("row_errors", None) or []
    sync_errors = stats.pop("sync_errors", None) or []
    return FileImportStatusResponse(
        sync_log_id=str(log.id),
        supplier_name=log.supplier_name,
        status=log.status,
        filename=stats.get("filename"),
        total_rows=stats.get("total_rows"),
        parsed_products=stats.get("parsed_products"),
        rejected_rows=stats.get("rejected_rows"),
        row_errors=[FileImportRowError.model_validate(e) for e in row_errors],
        statistics={
            k: v for k, v in stats.items() if isinstance(v, int) and k != "source"
        },
        sync_errors=[dict(e) for e in sync_errors],
        published_new=bool(stats.get("published_without_enrichment")),
        error_message=log.error_message,
        started_at=log.started_at,
        completed_at=log.completed_at,
    )


# -- maintenance ------------------------------------------------------------


@router.post("/admin/backfill-product-categories")
async def trigger_category_backfill(
    _current_user: CurrentSuperUser,
    batch_size: int = 200,
) -> dict[str, Any]:
    """Trigger a one-shot backfill: populate Product.category_id from supplier_subcategory.

    Safe to re-run (idempotent). Runs inline (blocking) — use for maintenance windows.
    **Required permissions:** Superuser only
    """
    stats = await backfill_product_categories_task({}, batch_size=batch_size)
    return {"status": "completed", **stats}


@router.post("/admin/refresh-prices")
async def trigger_price_refresh_inline(
    _current_user: CurrentSuperUser,
    category_id: str | None = None,
) -> dict[str, Any]:
    """Recompute the materialized storefront prices (``sale_price_cached``).

    First fill after the migration, or after a change the write hooks and the
    nightly refresh have not caught up with. Runs inline (blocking) — use for
    maintenance windows. Optionally scope to one ``category_id``.

    **Required permissions:** Superuser only
    """
    from app.tasks.pricing_tasks import refresh_sale_prices_task

    return await refresh_sale_prices_task(
        {}, category_id=category_id, reason="admin_inline"
    )


@router.post("/admin/reproject-specs")
async def trigger_spec_reprojection(
    _current_user: CurrentSuperUser,
    category_id: str | None = None,
) -> dict[str, Any]:
    """Rebuild the normalized ``product_spec`` table from each product's stored
    Icecat ``technical_specifications`` (no Icecat re-fetch).

    Needed for products enriched before the projection existed, and after any
    spec-definition alias change. Runs inline (blocking) — use for maintenance
    windows. Optionally scope to one ``category_id``.

    **Required permissions:** Superuser only
    """
    from app.tasks.icecat_tasks import reproject_product_specs_task

    stats = await reproject_product_specs_task({}, category_id=category_id)
    return stats
