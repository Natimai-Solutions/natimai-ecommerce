"""Runtime settings registry (R5): typing, resolution order, snapshot cache."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core import runtime_settings as rs
from app.core.config import settings


def test_every_declared_setting_has_a_known_category_and_a_valid_fallback() -> None:
    from app.features.system.settings_catalog import CATEGORIES

    assert len(rs.specs()) > 40
    for spec in rs.specs():
        assert spec.category in CATEGORIES, spec.key
        assert spec.label.strip(), spec.key
        if spec.env:
            assert hasattr(settings, spec.env), spec.key
        value, _ = rs.fallback(spec)
        text = rs.serialize(spec, value)
        if text.strip():
            # The fallback itself passes the spec (no default out of bounds).
            rs.parse(spec, text)


def test_existing_keys_keep_their_names() -> None:
    for key in (
        "pricing_payment_commission_pct",
        "legal_trading_name",
        "tax_default_code",
        "payment_instructions_manual_cash",
        "payment_provider_payzen_enabled",
        "customs_free_countries",
        "social_webhook_url",
        "default_display_currency",
    ):
        assert rs.spec_for(key) is not None, key


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("notifications_email_enabled", "Oui", True),
        ("notifications_email_enabled", "off", False),
        ("stock_reservation_ttl_hours", "48", 48),
        ("pricing_payment_commission_pct", "2,5 %", Decimal("2.5")),
        ("checkout_supplier_check_timeout_seconds", "7.5", 7.5),
        ("customs_free_countries", "fr, de\nit", ["FR", "DE", "IT"]),
        ("tax_default_code", " tva_normale ", "TVA_NORMALE"),
        ("icecat_language", "en", "en"),
    ],
)
def test_values_are_typed(key: str, raw: str, expected: object) -> None:
    assert rs.parse(rs.require_spec(key), raw) == expected


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("notifications_email_enabled", "peut-être"),
        ("stock_reservation_ttl_hours", "1.5"),
        ("stock_reservation_ttl_hours", "-1"),
        ("pricing_payment_commission_pct", "100"),
        ("pricing_payment_commission_pct", "abc"),
        ("icecat_language", "klingon"),
        ("email_support", "pas une adresse"),
        ("social_webhook_url", "ftp://x"),
    ],
)
def test_values_out_of_spec_are_refused(key: str, raw: str) -> None:
    with pytest.raises(ValueError):
        rs.parse(rs.require_spec(key), raw)


def test_resolution_order_is_db_then_env_then_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = rs.require_spec("stock_reservation_ttl_hours")
    monkeypatch.setattr(settings, "STOCK_RESERVATION_TTL_HOURS", 12)
    fields_set = set(settings.model_fields_set) - {"STOCK_RESERVATION_TTL_HOURS"}
    monkeypatch.setattr(settings, "__pydantic_fields_set__", fields_set)

    assert rs.resolve_row(spec, None).source == "default"
    assert rs.resolve_row(spec, None).value == 12  # the code / env value
    assert rs.resolve_row(spec, "  ").source == "default"  # blank = not set

    monkeypatch.setattr(settings, "__pydantic_fields_set__", fields_set | {spec.env})
    assert rs.resolve_row(spec, None).source == "env"

    stored = rs.resolve_row(spec, "6")
    assert (stored.source, stored.value) == ("db", 6)

    broken = rs.resolve_row(spec, "beaucoup")
    assert broken.stored_invalid and broken.value == 12  # fallback, no crash


def test_spec_without_env_falls_back_to_its_default() -> None:
    spec = rs.require_spec("customs_free_countries")
    resolved = rs.resolve_row(spec, None)
    assert (resolved.value, resolved.source) == ([], "default")


@pytest.mark.asyncio
async def test_snapshot_is_cached_until_ttl_or_version_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loads: list[int] = []
    table = {"stock_reservation_ttl_hours": "5"}
    version = {"v": 1}

    async def _load(_session: object) -> dict[str, str]:
        loads.append(1)
        return dict(table)

    async def _version() -> int:
        return version["v"]

    monkeypatch.setattr(rs, "_load_rows", _load)
    monkeypatch.setattr(rs, "_remote_version", _version)
    monkeypatch.setattr(rs, "CACHE_TTL_SECONDS", 60.0)
    monkeypatch.setattr(rs, "VERSION_CHECK_SECONDS", 0.0)
    rs.invalidate_cache()

    assert await rs.get("stock_reservation_ttl_hours") == 5
    table["stock_reservation_ttl_hours"] = "7"
    # Same version: the snapshot answers.
    assert await rs.get("stock_reservation_ttl_hours") == 5
    assert len(loads) == 1
    # A fresh read goes to the table.
    assert await rs.get("stock_reservation_ttl_hours", fresh=True) == 7
    table["stock_reservation_ttl_hours"] = "9"
    # Another process wrote: the counter moved, the snapshot is reloaded.
    version["v"] = 2
    assert await rs.get("stock_reservation_ttl_hours") == 9
    # A local invalidation reloads as well.
    table["stock_reservation_ttl_hours"] = "3"
    rs.invalidate_cache()
    assert await rs.get("stock_reservation_ttl_hours") == 3
    rs.invalidate_cache()


def test_secrets_are_masked() -> None:
    from app.features.system.settings_service import MASK, shown

    spec = rs.require_spec("social_webhook_url")
    assert shown(spec, "https://hook.example/abc") == MASK
    assert shown(spec, "") == ""
    assert shown(rs.require_spec("shop_name"), "Natimai") == "Natimai"
