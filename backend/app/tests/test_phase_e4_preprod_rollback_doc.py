from pathlib import Path


def test_e4_preprod_rollback_document_exists_and_contains_core_sections() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    # Archived under docs/development/done/ once the E4 phase shipped.
    doc_path = (
        backend_root
        / "docs"
        / "development"
        / "done"
        / "CHECKLIST_PREPROD_ROLLBACK_E4.md"
    )

    assert doc_path.exists(), "E4 document is missing"

    content = doc_path.read_text(encoding="utf-8")

    required_markers = [
        "# E4 Checklist Pre-Prod et Plan Rollback",
        "## 1) Checklist pre-prod",
        "## 2) Plan rollback",
        "### 2.2 Rollback niveau 1 (application only)",
        "### 2.3 Rollback niveau 2 (migration reversible)",
        "### 2.4 Rollback niveau 3 (restauration backup)",
        "./scripts/alembic-dev.ps1 downgrade -1",
        "pg_dump",
        "pg_restore",
        "/api/v1/utils/observability/dashboard",
    ]

    for marker in required_markers:
        assert marker in content, f"Missing marker in E4 doc: {marker}"
