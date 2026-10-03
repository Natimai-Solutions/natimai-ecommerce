"""Every state-changing request of an administrator is journaled (R6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.system.audit import purge_older_than
from app.features.system.models.audit_log import AdminAuditEntry

API = settings.API_V1_STR


def test_an_admin_mutation_is_journaled_without_its_body(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    marker = uuid.uuid4().hex[:8]
    response = client.put(
        f"{API}/admin/modules/icecat?trace={marker}&password=hunter2",
        json={"enabled": True},
        headers=superuser_token_headers,
    )
    assert response.status_code == 200

    page = client.get(
        f"{API}/admin/audit-log",
        params={"path_contains": "/admin/modules/icecat", "limit": 50},
        headers=superuser_token_headers,
    )
    assert page.status_code == 200
    entries = [
        e
        for e in page.json()["data"]
        if (e.get("details") or {}).get("query", {}).get("trace") == marker
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["event"] == "http"
    assert entry["method"] == "PUT"
    assert entry["route"] == f"{API}/admin/modules/{{key}}"
    assert entry["status_code"] == 200
    assert entry["actor_email"] == settings.FIRST_SUPERUSER
    assert entry["details"]["path_params"] == {"key": "icecat"}
    # Sensitive-looking parameters are never stored as typed.
    assert entry["details"]["query"]["password"] == "***"


def test_reads_and_customers_are_not_journaled(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    marker = uuid.uuid4().hex[:8]
    client.get(f"{API}/admin/modules?trace={marker}", headers=superuser_token_headers)
    client.patch(
        f"{API}/users/me?trace={marker}",
        json={"full_name": "Client"},
        headers=normal_user_token_headers,
    )
    page = client.get(
        f"{API}/admin/audit-log",
        params={"limit": 200},
        headers=superuser_token_headers,
    ).json()
    assert not [
        e
        for e in page["data"]
        if (e.get("details") or {}).get("query", {}).get("trace") == marker
    ]


@pytest.mark.asyncio
async def test_retention_purges_old_entries(db: AsyncSession) -> None:
    old = AdminAuditEntry(
        event="http",
        path="/old",
        created_at=datetime.now(UTC) - timedelta(days=500),
    )
    recent = AdminAuditEntry(event="http", path="/recent")
    old_id, recent_id = old.id, recent.id
    db.add_all([old, recent])
    await db.commit()

    assert await purge_older_than(db, 400) >= 1
    assert await db.get(AdminAuditEntry, old_id) is None
    assert await db.get(AdminAuditEntry, recent_id) is not None
    assert await purge_older_than(db, 0) == 0
