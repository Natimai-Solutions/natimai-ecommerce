"""Unit: the stored-file key of a queued catalog import. No database."""

from __future__ import annotations

import uuid

from app.tasks.supplier_file_import_tasks import build_import_storage_key


def test_storage_key_is_one_per_sync_log_and_filename_safe() -> None:
    log_id = uuid.uuid4()
    key = build_import_storage_key("distrib_tahiti", log_id, "Tarif été 2026 (v2).xlsx")
    assert key == f"supplier-imports/distrib_tahiti/{log_id}/Tarif_t_2026_v2_.xlsx"


def test_storage_key_never_ends_empty() -> None:
    log_id = uuid.uuid4()
    assert build_import_storage_key("s", log_id, "...").endswith("/catalogue")
