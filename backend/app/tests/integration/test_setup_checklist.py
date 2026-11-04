"""Integration tests: the admin start-up checklist is computed from the data."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import admin_setup_checklist as checklist
from app.features.payment.models.payment_method import PaymentMethod
from app.features.place.models import Place
from app.features.system.legal_identity import REQUIRED_FOR_INVOICING
from app.features.user.models.user import User


def _settings(monkeypatch: pytest.MonkeyPatch, values: dict[str, Any]) -> None:
    async def _get(key: str, _session: object = None, **_kw: object) -> Any:
        return values.get(key)

    monkeypatch.setattr("app.core.runtime_settings.get", _get)


def _legal(monkeypatch: pytest.MonkeyPatch, identity: dict[str, str]) -> None:
    async def _load(_session: object) -> dict[str, str]:
        return identity

    monkeypatch.setattr(checklist, "load_legal_identity", _load)


def _statuses(result: checklist.SetupChecklist) -> dict[str, tuple[str, int]]:
    return {item.key: (item.status, item.count) for item in result.items}


@pytest.mark.asyncio
async def test_a_new_shop_has_everything_to_do(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, {})
    _legal(monkeypatch, {})

    result = await checklist.get_setup_checklist(db_session, cast(User, None))

    statuses = _statuses(result)
    assert statuses["legal_identity"] == ("todo", len(REQUIRED_FOR_INVOICING))
    assert statuses["support_email"][0] == "todo"
    assert statuses["payment_methods"][0] == "todo"
    assert statuses["catalogue"] == ("todo", 0)
    assert statuses["insurance_rate"][0] == "check"
    assert not result.ready
    assert result.total == len(result.items)


@pytest.mark.asyncio
async def test_a_configured_shop_only_misses_its_catalogue(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, {"email_support": "boutique@example.pf"})
    _legal(monkeypatch, dict.fromkeys(REQUIRED_FOR_INVOICING, "x"))
    db_session.add(PaymentMethod(name="Virement", provider_code="manual"))
    db_session.add(
        Place(
            name="Port de Papeete", type="port", code="PPT-PORT", customs_clearance=True
        )
    )
    db_session.add(
        Place(
            name="Aéroport de Faa'a",
            type="airport",
            code="PPT-AIR",
            customs_clearance=True,
            customs_declaration_fee=Decimal("3500"),
        )
    )
    await db_session.commit()

    result = await checklist.get_setup_checklist(db_session, cast(User, None))

    statuses = _statuses(result)
    assert statuses["legal_identity"] == ("done", 0)
    assert statuses["support_email"][0] == "done"
    assert statuses["payment_methods"][0] == "done"
    # One clearance place has no declaration fee: to confirm, not blocking.
    assert statuses["customs_declaration_fees"] == ("check", 1)
    assert statuses["insurance_rate"][0] == "check"
    # The empty catalogue is the only thing left.
    assert [k for k, (s, _) in statuses.items() if s == "todo"] == ["catalogue"]
    assert not result.ready
