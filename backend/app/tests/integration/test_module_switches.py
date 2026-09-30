"""Modules and integrations switched on and off in base (R4 / S1, S6).

``SHOP_MODE`` is only a preset; the stored switch wins and takes effect
without a restart. Covers the Icecat switch, the admin routes, the seed of
the historical supplier in simple mode and the withdrawal of a deactivated
supplier's products.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_modules import ModuleWrite, list_modules, switch_module
from app.api.routes.admin_suppliers import deactivate_supplier
from app.api.routes.system_settings import get_shop_config
from app.core.config import secret_is_set, settings
from app.core.errors import AppError
from app.features import initial_data as seed
from app.features.integrations.models.supplier import Supplier, SupplierKind
from app.features.integrations.services import supplier_sync_orchestrator
from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
from app.features.product.models.product import Product
from app.features.system.models.system_setting import SystemSetting
from app.features.system.modules import (
    invalidate_cache,
    module_enabled,
    set_module,
)
from app.features.user.models.user import User
from app.services.suppliers.ingram_micro import IngramMicroAdapter

ADMIN = cast(User, SimpleNamespace(id=uuid.uuid4(), is_superuser=True))


@pytest.mark.asyncio
async def test_preset_follows_shop_mode_until_a_value_is_stored(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert await module_enabled(db_session, "icecat") is True

    monkeypatch.setattr(settings, "SHOP_MODE", "simple")
    invalidate_cache()
    assert await module_enabled(db_session, "icecat") is False

    # Stored: the mode no longer decides.
    await set_module(db_session, "icecat", True)
    await db_session.commit()
    assert await module_enabled(db_session, "icecat") is True


@pytest.mark.asyncio
async def test_env_kill_switch_wins_over_the_stored_switch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await set_module(db_session, "icecat", True)
    await db_session.commit()
    monkeypatch.setattr(settings, "ICECAT_ENABLED", False)

    assert await module_enabled(db_session, "icecat") is False
    states = await list_modules(db_session, ADMIN)
    icecat = next(s for s in states if s.key == "icecat")
    assert icecat.switched_on is True
    assert icecat.enabled is False
    assert icecat.blocked_by_env == "ICECAT_ENABLED"


@pytest.mark.asyncio
async def test_admin_switch_is_visible_in_the_public_config(
    db_session: AsyncSession,
) -> None:
    state = await switch_module("icecat", ModuleWrite(enabled=False), db_session, ADMIN)
    assert state.switched_on is False and state.enabled is False

    config = await get_shop_config(db_session)
    assert config.modules["icecat"] is False

    stored = (
        await db_session.exec(
            select(SystemSetting).where(SystemSetting.key == "module.icecat")
        )
    ).one()
    assert stored.value == "false"


@pytest.mark.asyncio
async def test_unknown_module_is_a_404(db_session: AsyncSession) -> None:
    with pytest.raises(AppError) as refused:
        await switch_module("teleport", ModuleWrite(enabled=True), db_session, ADMIN)
    assert refused.value.status_code == 404
    assert refused.value.code == "module.unknown"


@pytest.mark.asyncio
async def test_no_enrichment_is_enqueued_while_icecat_is_off(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trigger = AsyncMock(return_value="job")
    monkeypatch.setattr(supplier_sync_orchestrator, "trigger_batch_enrichment", trigger)
    orchestrator = SupplierSyncOrchestrator(IngramMicroAdapter())

    await set_module(db_session, "icecat", False)
    await db_session.commit()
    await orchestrator._enqueue_enrichment(db_session, 3)
    trigger.assert_not_awaited()

    await set_module(db_session, "icecat", True)
    await db_session.commit()
    await orchestrator._enqueue_enrichment(db_session, 3)
    trigger.assert_awaited_once()


def test_placeholder_secrets_do_not_count_as_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert secret_is_set("real-value") is True
    assert secret_is_set("") is False
    assert secret_is_set(None) is False
    assert secret_is_set("changeme-ingram-client-id") is False
    monkeypatch.setattr(settings, "INGRAM_CLIENT_ID", "changeme-ingram-client-id")
    monkeypatch.setattr(settings, "INGRAM_CLIENT_SECRET", "secret")
    monkeypatch.setattr(settings, "INGRAM_CUSTOMER_NUMBER", "20-123456")
    assert IngramMicroAdapter.credentials_present() is False


async def _ingram(session: AsyncSession) -> Supplier:
    return (
        await session.exec(select(Supplier).where(Supplier.code == "ingram_micro"))
    ).one()


@pytest.mark.asyncio
async def test_simple_mode_seeds_ingram_switched_off(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SHOP_MODE", "simple")
    await seed._seed_suppliers(db_session)
    await db_session.commit()

    ingram = await _ingram(db_session)
    assert ingram.is_active is False
    assert ingram.sync_enabled is False


@pytest.mark.asyncio
async def test_simple_mode_switches_an_existing_row_off_once_only(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A row seeded active by an earlier version (crons were never scheduled).
    await seed._seed_suppliers(db_session)
    await db_session.commit()
    assert (await _ingram(db_session)).is_active is True

    monkeypatch.setattr(settings, "SHOP_MODE", "simple")
    await seed._seed_suppliers(db_session)
    await db_session.commit()
    ingram = await _ingram(db_session)
    assert ingram.is_active is False and ingram.sync_enabled is False

    # The admin reactivates it: the next deployment's seed leaves it alone.
    ingram.is_active = True
    ingram.sync_enabled = True
    db_session.add(ingram)
    await db_session.commit()
    await seed._seed_suppliers(db_session)
    await db_session.commit()
    ingram = await _ingram(db_session)
    assert ingram.is_active is True and ingram.sync_enabled is True


@pytest.mark.asyncio
async def test_module_seed_never_rewrites_a_choice(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SHOP_MODE", "simple")
    await seed._seed_module_switches(db_session)
    await db_session.commit()
    row = (
        await db_session.exec(
            select(SystemSetting).where(SystemSetting.key == "module.icecat")
        )
    ).one()
    assert row.value == "false"

    await set_module(db_session, "icecat", True)
    await db_session.commit()
    monkeypatch.setattr(settings, "SHOP_MODE", "full")
    await seed._seed_module_switches(db_session)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.value == "true"


async def _supplier_with_products(session: AsyncSession) -> None:
    session.add(Supplier(code="acme", name="Acme", kind=SupplierKind.FILE))
    for sku in ("A-1", "A-2"):
        session.add(
            Product(
                name=f"ACME-{sku}",
                supplier_name="acme",
                supplier_sku=sku,
                is_supplier_managed=True,
                supplier_quantity=Decimal("12"),
            )
        )
    session.add(Product(name="OWN-1", supplier_quantity=Decimal("3")))
    await session.commit()


async def _products(session: AsyncSession) -> dict[str, Any]:
    rows = (await session.exec(select(Product))).all()
    return {p.name: (p.supplier_quantity, p.is_active) for p in rows}


@pytest.mark.asyncio
async def test_deactivation_keeps_products_by_default(
    db_session: AsyncSession,
) -> None:
    await _supplier_with_products(db_session)
    public = await deactivate_supplier("acme", db_session, ADMIN)
    assert public.is_active is False
    assert public.products_withdrawn is None
    products = await _products(db_session)
    assert products["ACME-A-1"][0] == Decimal("12")


@pytest.mark.asyncio
async def test_deactivation_can_zero_the_supplier_stock(
    db_session: AsyncSession,
) -> None:
    await _supplier_with_products(db_session)
    public = await deactivate_supplier("acme", db_session, ADMIN, products="zero_stock")
    assert public.products_withdrawn == 2
    products = await _products(db_session)
    assert products["ACME-A-1"] == (Decimal("0"), True)
    assert products["OWN-1"][0] == Decimal("3")


@pytest.mark.asyncio
async def test_deactivation_can_hide_the_products(db_session: AsyncSession) -> None:
    await _supplier_with_products(db_session)
    await deactivate_supplier("acme", db_session, ADMIN, products="hide")
    products = await _products(db_session)
    assert products["ACME-A-2"] == (Decimal("0"), False)
    assert products["OWN-1"][1] is True
