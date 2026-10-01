"""Admin settings API on the typed registry (R5 / C2)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

import app.tasks.pricing_tasks as pricing_tasks
from app.api.routes.system_settings import (
    admin_get_setting,
    admin_list_settings,
    admin_reset_setting,
    admin_upsert_setting,
    get_public_settings,
    get_shop_config,
)
from app.core import runtime_settings as rs
from app.core.errors import AppError
from app.core.security import get_password_hash
from app.features import initial_data as seed
from app.features.system.models.audit_log import AdminAuditEntry
from app.features.system.models.system_setting import (
    SystemSetting,
    SystemSettingUpdate,
)
from app.features.system.settings_service import MASK
from app.features.user.models.user import User


async def _admin(session: AsyncSession) -> User:
    user = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=get_password_hash("x" * 12),
        is_superuser=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_only_declared_keys_are_accepted_and_values_are_validated(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    with pytest.raises(AppError) as unknown:
        await admin_upsert_setting(
            "whatever_i_like", SystemSettingUpdate(value="1"), db_session, admin
        )
    assert unknown.value.status_code == 404
    assert unknown.value.code == "system_setting.unknown_key"

    with pytest.raises(AppError) as invalid:
        await admin_upsert_setting(
            "stock_reservation_ttl_hours",
            SystemSettingUpdate(value="deux jours"),
            db_session,
            admin,
        )
    assert invalid.value.status_code == 400
    assert (
        await db_session.exec(
            select(SystemSetting).where(
                SystemSetting.key == "stock_reservation_ttl_hours"
            )
        )
    ).first() is None


@pytest.mark.asyncio
async def test_a_value_is_typed_attributed_journaled_and_resettable(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    admin_email = admin.email
    before = await admin_get_setting("stock_reservation_ttl_hours", db_session, admin)
    assert before.source in {"env", "default"}

    saved = await admin_upsert_setting(
        "stock_reservation_ttl_hours",
        SystemSettingUpdate(value=" 6 "),
        db_session,
        admin,
    )
    assert (saved.value, saved.source, saved.type) == ("6", "db", "int")
    assert saved.updated_by_email == admin_email
    assert await rs.get("stock_reservation_ttl_hours", db_session) == 6

    entry = (
        await db_session.exec(
            select(AdminAuditEntry).where(AdminAuditEntry.event == "setting.changed")
        )
    ).first()
    assert entry is not None
    assert entry.details == {
        "key": "stock_reservation_ttl_hours",
        "old": None,
        "new": "6",
    }

    reset = await admin_reset_setting("stock_reservation_ttl_hours", db_session, admin)
    assert reset.source == before.source
    assert reset.value == before.value


@pytest.mark.asyncio
async def test_secrets_are_masked_and_a_masked_value_sent_back_is_ignored(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    url = "https://hook.example/very-secret"
    saved = await admin_upsert_setting(
        "social_webhook_url", SystemSettingUpdate(value=url), db_session, admin
    )
    assert saved.value == MASK
    again = await admin_upsert_setting(
        "social_webhook_url", SystemSettingUpdate(value=MASK), db_session, admin
    )
    assert again.value == MASK
    assert await rs.get("social_webhook_url", db_session) == url
    entry = (
        await db_session.exec(
            select(AdminAuditEntry).where(AdminAuditEntry.event == "setting.changed")
        )
    ).one()
    assert url not in str(entry.details)


@pytest.mark.asyncio
async def test_hooks_run_only_on_a_change(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await _admin(db_session)
    scheduled: list[Any] = []

    async def _schedule(**kwargs: Any) -> str:
        scheduled.append(kwargs)
        return "job"

    monkeypatch.setattr(pricing_tasks, "schedule_price_refresh", _schedule)
    for _ in range(2):
        await admin_upsert_setting(
            "insurance_rate_pct", SystemSettingUpdate(value="1.5"), db_session, admin
        )
    assert scheduled == [{"reason": "system_setting:insurance_rate_pct"}]


@pytest.mark.asyncio
async def test_lists_every_declared_setting_and_public_ones_without_auth(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    listed = await admin_list_settings(db_session, admin)
    assert {s.key for s in listed} == {s.key for s in rs.specs()}

    await admin_upsert_setting(
        "legal_trading_name",
        SystemSettingUpdate(value="Ma Boutique SARL"),
        db_session,
        admin,
    )
    await admin_upsert_setting(
        "shop_name", SystemSettingUpdate(value="Ma Boutique"), db_session, admin
    )
    public = {s.key: s.value for s in await get_public_settings(db_session)}
    assert public["legal_trading_name"] == "Ma Boutique SARL"
    assert "social_webhook_url" not in public
    assert "stock_reservation_ttl_hours" not in public
    assert (await get_shop_config(db_session)).shop_name == "Ma Boutique"


@pytest.mark.asyncio
async def test_module_switches_still_go_through_the_endpoint(
    db_session: AsyncSession,
) -> None:
    admin = cast(User, SimpleNamespace(id=uuid.uuid4(), email="a@b.c"))
    out = await admin_upsert_setting(
        "module.quotes", SystemSettingUpdate(value="False"), db_session, admin
    )
    assert out.value == "false"


@pytest.mark.asyncio
async def test_seed_copies_the_environment_once_and_never_rewrites(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "INVOICE_SELLER_ADDRESS", "1 rue du Port, Papeete")
    await seed._seed_runtime_settings(db_session)
    await db_session.commit()
    assert (
        await rs.get("legal_head_office_address", db_session)
        == "1 rue du Port, Papeete"
    )

    row = (
        await db_session.exec(
            select(SystemSetting).where(
                SystemSetting.key == "legal_head_office_address"
            )
        )
    ).one()
    row.value = "Adresse saisie"
    db_session.add(row)
    await db_session.commit()
    await seed._seed_runtime_settings(db_session)
    await db_session.commit()
    assert await rs.get("legal_head_office_address", db_session) == "Adresse saisie"
