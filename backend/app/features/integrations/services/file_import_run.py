"""Run a supplier catalog file import: shared by the request and the worker.

``POST /suppliers/{code}/import-file`` imports a small file inline; a large
one is stored and handed to :mod:`app.tasks.supplier_file_import_tasks`.
Both paths end here, so the sync log carries the same statistics whichever
way the file came in: counters, the first rejected rows and sync errors,
and whether the created rows were published as the file describes them.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.integrations.crud.supplier_sync import supplier_sync_log_crud
from app.features.integrations.models.supplier import SupplierKind
from app.features.integrations.models.supplier_sync import SyncStatus
from app.features.integrations.services.supplier_sync_orchestrator import (
    ImportThresholds,
    SupplierSyncOrchestrator,
)
from app.services.suppliers import SupplierAdapter, adapter_for_supplier, has_adapter
from app.services.suppliers.base import SupplierConfig, SupplierHealth
from app.services.suppliers.file_import import RowError

logger = logging.getLogger(__name__)

#: How many rejected rows / sync errors the sync log keeps (the counters are
#: exact; the lists are a sample for the admin screen).
ERROR_SAMPLE_SIZE = 100


class FileSupplierAdapter(SupplierAdapter):
    """Inert adapter carrying a manual / file supplier's identity and regime.

    The orchestrator only reads ``name``, ``origin_place_id``,
    ``origin_place_code``, ``is_domestic`` and ``price_currency`` on the
    upsert path; nothing is ever fetched.
    """

    adapter_key = "file"
    display_name = "Fichier"

    async def fetch_catalog(self, category: str, **filters: Any) -> Any:
        del category, filters
        raise NotImplementedError("file suppliers are fed by /import-file")
        yield  # pragma: no cover

    async def fetch_price_and_availability(self, skus: list[str]) -> dict[str, Any]:
        del skus
        return {}

    async def health_check(self) -> Any:
        return SupplierHealth(
            healthy=True, configured=True, message="File supplier (no live API)"
        )


def orchestrator_for_file_import(supplier: Any) -> SupplierSyncOrchestrator:
    """The orchestrator that imports a file for ``supplier`` (any kind).

    An API supplier with a registered integration keeps its real adapter (its
    identity and origin are the same); every other supplier gets the inert
    file adapter. Reads the row's attributes right away: the import commits
    per product and expires the session's instances.
    """
    adapter: SupplierAdapter
    if supplier.kind == SupplierKind.API and has_adapter(supplier.adapter_key):
        adapter = adapter_for_supplier(supplier)
    else:
        adapter = FileSupplierAdapter(SupplierConfig.from_row(supplier))
    return SupplierSyncOrchestrator(adapter)


def thresholds_for(
    supplier: Any,
    *,
    min_quantity: Decimal | None = None,
    min_price: Decimal | None = None,
) -> ImportThresholds:
    """The minimums of an import: the ones given for this run, else the
    supplier's (``Supplier.min_quantity`` / ``min_price``). ``0`` given for a
    run disables that threshold for it."""
    return ImportThresholds(
        min_quantity=(
            min_quantity
            if min_quantity is not None
            else getattr(supplier, "min_quantity", None)
        ),
        min_price=(
            min_price if min_price is not None else getattr(supplier, "min_price", None)
        ),
    )


def thresholds_payload(thresholds: ImportThresholds) -> dict[str, str | None]:
    """JSON-safe form for an ARQ job (Decimal as text)."""
    return {
        "min_quantity": (
            str(thresholds.min_quantity)
            if thresholds.min_quantity is not None
            else None
        ),
        "min_price": (
            str(thresholds.min_price) if thresholds.min_price is not None else None
        ),
    }


def thresholds_from_payload(payload: dict[str, Any]) -> ImportThresholds:
    def _dec(value: Any) -> Decimal | None:
        return Decimal(str(value)) if value not in (None, "") else None

    return ImportThresholds(
        min_quantity=_dec(payload.get("min_quantity")),
        min_price=_dec(payload.get("min_price")),
    )


@dataclass(slots=True)
class FileImportOutcome:
    """What an import run produced, for the response and the sync log."""

    status: SyncStatus
    statistics: dict[str, int]
    sync_errors: list[dict[str, str]] = field(default_factory=list)


async def run_file_import(
    session: AsyncSession,
    *,
    orchestrator: SupplierSyncOrchestrator,
    products: list[Any],
    row_errors: list[RowError],
    sync_log_id: uuid.UUID,
    filename: str,
    total_rows: int,
    publish_new: bool,
    thresholds: ImportThresholds | None = None,
) -> FileImportOutcome:
    """Import parsed rows under an existing sync log and close it.

    Each product is committed as it is upserted (a failure on one row never
    rolls back the others). The log ends ``SUCCESS``, ``PARTIAL`` (rejected
    rows, ambiguous or failed products) or ``FAILED`` (the run itself broke,
    re-raised for the caller).
    """
    await supplier_sync_log_crud.start_sync(session=session, sync_log_id=sync_log_id)

    sync_errors: list[dict[str, str]] = []
    try:
        stats = await orchestrator.import_items(
            session,
            products,
            errors=sync_errors,
            publish_without_enrichment=publish_new,
            thresholds=thresholds,
        )
    except Exception as exc:
        await supplier_sync_log_crud.complete_sync(
            session=session,
            sync_log_id=sync_log_id,
            status=SyncStatus.FAILED,
            error_message=str(exc),
        )
        raise

    stats["rejected_rows"] = len(row_errors)
    stats["published_without_enrichment"] = int(publish_new)
    partial = stats["errors"] or stats["ambiguous_products"] or row_errors
    status = SyncStatus.PARTIAL if partial else SyncStatus.SUCCESS
    await supplier_sync_log_crud.complete_sync(
        session=session,
        sync_log_id=sync_log_id,
        status=status,
        statistics={
            **stats,
            "source": "file",
            "filename": filename,
            "total_rows": total_rows,
            "parsed_products": len(products),
            **(
                {"thresholds": thresholds_payload(thresholds)}
                if thresholds is not None and thresholds.active
                else {}
            ),
            "row_errors": [
                {"row_number": e.row_number, "message": e.message}
                for e in row_errors[:ERROR_SAMPLE_SIZE]
            ],
            "sync_errors": sync_errors[:ERROR_SAMPLE_SIZE],
        },
    )
    logger.info(
        "Catalog file %s imported for %s (%s): %s",
        filename,
        orchestrator.adapter.name,
        status.value,
        stats,
    )
    return FileImportOutcome(status=status, statistics=stats, sync_errors=sync_errors)
