"""ARQ task: import a large supplier catalog file in the background.

``POST /suppliers/{code}/import-file`` stores a file above the inline row
limit (``FILE_STORAGE_BACKEND``), opens a sync log and enqueues this task;
the admin screen polls ``GET …/import-file/{sync_log_id}``. The task parses
and imports exactly as the inline path does, records the outcome on the same
sync log, and discards the stored file afterwards — success or failure, the
file is not an archive.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.attachment.storage.factory import get_file_storage
from app.features.integrations.crud.supplier_sync import supplier_sync_log_crud
from app.features.integrations.models.supplier_sync import SyncStatus
from app.features.integrations.services.file_import_run import (
    orchestrator_for_file_import,
    run_file_import,
    thresholds_for,
    thresholds_from_payload,
)
from app.services.suppliers import load_supplier
from app.services.suppliers.file_import import (
    FileImportError,
    max_rows_setting,
    read_tabular_file,
    rows_to_products,
    validate_mapping,
)
from app.tasks.enqueue import enqueue_with_dedup

logger = logging.getLogger(__name__)

TASK_NAME = "import_supplier_file_task"
STORAGE_PREFIX = "supplier-imports"
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def build_import_storage_key(
    supplier_code: str, sync_log_id: uuid.UUID, filename: str
) -> str:
    """Where the uploaded file waits for the worker (one key per sync log)."""
    safe_name = _SAFE_FILENAME_RE.sub("_", filename).strip("._") or "catalogue"
    return f"{STORAGE_PREFIX}/{supplier_code}/{sync_log_id}/{safe_name}"


async def trigger_file_import(
    *,
    sync_log_id: uuid.UUID,
    supplier_code: str,
    storage_key: str,
    filename: str,
    mapping: dict[str, str],
    publish_new: bool,
    thresholds: dict[str, str | None] | None = None,
    default_category_id: str | None = None,
) -> str:
    """Queue the import of a stored file; returns the ARQ job id."""
    return await enqueue_with_dedup(
        TASK_NAME,
        dedup_namespace=f"file_import_dedup:{supplier_code}",
        job_prefix=f"file_import_{supplier_code}",
        payload_key=[str(sync_log_id)],
        job_kwargs={
            "sync_log_id": str(sync_log_id),
            "supplier_code": supplier_code,
            "storage_key": storage_key,
            "filename": filename,
            "mapping": mapping,
            "publish_new": publish_new,
            "thresholds": thresholds,
            "default_category_id": default_category_id,
        },
    )


async def _discard(storage: Any, key: str) -> None:
    """Drop the stored file; a failure here is logged, never raised."""
    try:
        await storage.delete(key=key)
    except Exception as exc:  # noqa: BLE001 - best effort cleanup
        logger.warning("Could not delete stored import file %s: %s", key, exc)


async def run_queued_file_import(
    session: AsyncSession,
    *,
    sync_log_id: uuid.UUID,
    supplier_code: str,
    storage_key: str,
    filename: str,
    mapping: dict[str, str],
    publish_new: bool,
    thresholds: dict[str, str | None] | None = None,
    default_category_id: str | None = None,
) -> dict[str, Any]:
    """Import the stored file under ``sync_log_id`` (the task body, testable).

    ``thresholds`` are the minimums chosen when the file was sent; a job
    queued without them (older version) uses the supplier's.
    """
    storage = get_file_storage()
    try:
        supplier = await load_supplier(session, supplier_code, include_inactive=True)
        if supplier is None:
            raise FileImportError(f"Fournisseur inconnu : {supplier_code}")
        # Attributes are read before any commit expires the instance.
        orchestrator = orchestrator_for_file_import(supplier)
        default_currency = supplier.price_currency
        run_thresholds = (
            thresholds_from_payload(thresholds)
            if thresholds is not None
            else thresholds_for(supplier)
        )
        await orchestrator.load_category_rules(
            session,
            default_category_id=(
                uuid.UUID(default_category_id) if default_category_id else None
            ),
        )

        content = await storage.get_bytes(key=storage_key)
        max_rows = await max_rows_setting(session)
        parsed = read_tabular_file(content, filename, max_rows=max_rows)
        if parsed.total_rows > max_rows:
            raise FileImportError(
                f"Le fichier compte {parsed.total_rows} lignes ; la limite est {max_rows}"
            )
        problems = validate_mapping(mapping, parsed.headers)
        if problems:
            raise FileImportError("; ".join(problems))
        result = rows_to_products(
            parsed.rows, mapping, default_currency=default_currency
        )
    except Exception as exc:
        logger.error(
            "Queued import %s for %s failed: %s", sync_log_id, supplier_code, exc
        )
        await supplier_sync_log_crud.complete_sync(
            session=session,
            sync_log_id=sync_log_id,
            status=SyncStatus.FAILED,
            error_message=str(exc),
        )
        await _discard(storage, storage_key)
        return {
            "status": "error",
            "sync_log_id": str(sync_log_id),
            "supplier_name": supplier_code,
            "message": str(exc),
        }

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
            thresholds=run_thresholds,
        )
    finally:
        await _discard(storage, storage_key)

    return {
        "status": outcome.status.value,
        "sync_log_id": str(sync_log_id),
        "supplier_name": supplier_code,
        "statistics": outcome.statistics,
    }


async def import_supplier_file_task(
    _ctx: dict[str, Any],
    *,
    sync_log_id: str,
    supplier_code: str,
    storage_key: str,
    filename: str,
    mapping: dict[str, str],
    publish_new: bool = True,
    thresholds: dict[str, str | None] | None = None,
    default_category_id: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """ARQ entry point: see :func:`run_queued_file_import`."""
    async with AsyncSession(engine) as session:
        return await run_queued_file_import(
            session,
            sync_log_id=uuid.UUID(sync_log_id),
            supplier_code=supplier_code,
            storage_key=storage_key,
            filename=filename,
            mapping=mapping,
            publish_new=publish_new,
            thresholds=thresholds,
            default_category_id=default_category_id,
        )
