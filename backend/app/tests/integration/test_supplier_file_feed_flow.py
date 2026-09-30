"""A file-feed supplier end to end (R4 / S3): declared, login stored
encrypted, catalogue synced with its minimums, never asked live."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_suppliers import (
    SupplierCredentialsWrite,
    create_supplier,
    delete_supplier_credentials,
    put_supplier_credentials,
)
from app.core.config import settings
from app.core.errors import AppError
from app.features.integrations.models.supplier import (
    Supplier,
    SupplierCreate,
    SupplierKind,
)
from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
from app.features.product.models.product import Product
from app.features.user.models.user import User
from app.services import suppliers as registry
from app.services.suppliers import file_feed
from app.services.suppliers.file_feed import FileFeedAdapter
from app.tasks.supplier_tasks import _due_suppliers

ADMIN = cast(User, SimpleNamespace(id=uuid.uuid4(), is_superuser=True))
CSV = "ref;nom;prix;stock\nFX-1;iPhone 12;30000;8\nFX-2;iPhone 11;20000;1\n"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "SUPPLIER_SECRETS_KEY", Fernet.generate_key().decode()
    )
    monkeypatch.setattr(settings, "SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST", [])
    monkeypatch.setattr(file_feed, "check_public_https_url", AsyncMock())
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(200, text=CSV)

    monkeypatch.setattr(FileFeedAdapter, "transport", httpx.MockTransport(handler))
    registry._INSTANCES.clear()


async def _declare(session: AsyncSession) -> None:
    await create_supplier(
        payload=SupplierCreate(
            code="foxway",
            name="Foxway",
            kind=SupplierKind.API,
            adapter_key="file_feed",
            is_domestic=True,
            price_currency="XPF",
            sync_interval_hours=6,
            min_quantity=Decimal("2"),
            column_mapping={
                "supplier_sku": "ref",
                "name": "nom",
                "price": "prix",
                "quantity": "stock",
            },
            settings={
                "feed_url": "https://portal.foxway.example/stock.csv",
                "auth_mode": "basic",
            },
        ),
        session=session,
        current_user=ADMIN,
    )


@pytest.mark.asyncio
async def test_feed_supplier_syncs_with_its_minimums(db_session: AsyncSession) -> None:
    await _declare(db_session)
    row = (
        await db_session.exec(select(Supplier).where(Supplier.code == "foxway"))
    ).one()
    assert registry.adapter_for_supplier(row).is_configured() is False  # no login

    public = await put_supplier_credentials(
        "foxway",
        SupplierCredentialsWrite(username="shop", password="very-secret"),
        db_session,
        ADMIN,
    )
    assert public.has_credentials is True
    assert "very-secret" not in public.model_dump_json()
    await db_session.refresh(row)
    assert "very-secret" not in (row.credentials_encrypted or "")

    adapter = registry.adapter_for_supplier(row)
    assert adapter.is_configured() is True
    # Due for its catalogue sync, never for the live inventory refresh.
    assert [c for c, _ in await _due_suppliers(db_session, catalog=True)] == ["foxway"]
    assert await _due_suppliers(db_session, catalog=False) == []

    stats = await SupplierSyncOrchestrator(adapter).sync_products_to_database(
        db_session
    )
    assert stats["new_products"] == 1
    assert stats["below_threshold_skipped"] == 1
    products = (
        await db_session.exec(select(Product).where(Product.supplier_name == "foxway"))
    ).all()
    assert [(p.supplier_sku, p.supplier_quantity) for p in products] == [
        ("FX-1", Decimal("8.00"))
    ]


@pytest.mark.asyncio
async def test_a_failing_feed_fails_the_sync(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _declare(db_session)
    await put_supplier_credentials(
        "foxway",
        SupplierCredentialsWrite(username="shop", password="pw"),
        db_session,
        ADMIN,
    )
    monkeypatch.setattr(
        FileFeedAdapter, "transport", httpx.MockTransport(lambda r: httpx.Response(503))
    )
    row = (
        await db_session.exec(select(Supplier).where(Supplier.code == "foxway"))
    ).one()
    with pytest.raises(file_feed.FeedError):
        await SupplierSyncOrchestrator(
            registry.adapter_for_supplier(row)
        ).sync_products_to_database(db_session)


@pytest.mark.asyncio
async def test_credentials_need_the_key_and_can_be_cleared(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _declare(db_session)
    monkeypatch.setattr(settings, "SUPPLIER_SECRETS_KEY", None)
    with pytest.raises(AppError) as refused:
        await put_supplier_credentials(
            "foxway",
            SupplierCredentialsWrite(username="shop", password="pw"),
            db_session,
            ADMIN,
        )
    assert refused.value.code == "supplier.credentials.no_key"
    await db_session.rollback()

    cleared = await delete_supplier_credentials("foxway", db_session, ADMIN)
    assert cleared.has_credentials is False


@pytest.mark.asyncio
async def test_feed_url_must_be_https(db_session: AsyncSession) -> None:
    with pytest.raises(AppError) as refused:
        await create_supplier(
            payload=SupplierCreate(
                code="picata",
                name="Picata",
                kind=SupplierKind.API,
                adapter_key="file_feed",
                settings={"feed_url": "http://picata.example/stock.csv"},
            ),
            session=db_session,
            current_user=ADMIN,
        )
    assert refused.value.code == "supplier.feed.https_required"
