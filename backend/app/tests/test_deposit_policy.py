"""Deposit policy: plan choice, fee, split, amount due per payment kind."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.routes.cart import _snapshot_checkout_amounts
from app.core.errors import AppError
from app.features.payment.services.deposit import (
    DepositPolicy,
    balance_amount,
    balance_due,
    choose_plan,
    deposit_fee,
    deposit_split,
    expected_amount,
    next_payment_kind,
)

POLICY = DepositPolicy(
    pct=Decimal("30"), fee_pct=Decimal("2"), fee_fixed=Decimal("100")
)


def test_policy_reads_the_price_group_and_defaults_to_none() -> None:
    assert not DepositPolicy.of(None).available
    assert not DepositPolicy.of(SimpleNamespace(deposit_pct=None)).available
    policy = DepositPolicy.of(
        SimpleNamespace(
            deposit_pct=Decimal("50"),
            deposit_fee_pct=None,
            deposit_fee_fixed=Decimal("0"),
            deposit_required=True,
        )
    )
    assert policy == DepositPolicy(pct=Decimal("50"), required=True)


def test_choose_plan_honours_the_policy() -> None:
    assert choose_plan(DepositPolicy(), None) == "full"
    assert choose_plan(POLICY, None) == "full"
    assert choose_plan(POLICY, "deposit") == "deposit"
    assert choose_plan(DepositPolicy(pct=Decimal("50"), required=True), "full") == (
        "deposit"
    )
    with pytest.raises(AppError) as refused:
        choose_plan(DepositPolicy(), "deposit")
    assert refused.value.code == "checkout.deposit.unavailable"


def test_fee_and_split_add_up_in_xpf() -> None:
    # 2 % of 10 000 + 100 fixed = 300, rounded to the XPF unit.
    assert deposit_fee(POLICY, Decimal("10000"), "XPF") == Decimal("300")
    deposit, balance = deposit_split(POLICY, Decimal("10300"), "XPF")
    assert (deposit, balance) == (Decimal("3090"), Decimal("7210"))
    assert deposit + balance == Decimal("10300")
    # An odd total still splits exactly (the balance takes the rounding).
    deposit, balance = deposit_split(POLICY, Decimal("10001"), "XPF")
    assert deposit + balance == Decimal("10001")


def test_checkout_amounts_carry_the_deposit_fee_in_the_fees_total() -> None:
    items = [SimpleNamespace(unit_price=Decimal("500"), quantity=2)]
    subtotal, shipping, payment, fees, total = _snapshot_checkout_amounts(
        items=items,
        currency="XPF",
        shipping_fee_amount=Decimal("200"),
        payment_fee_amount=Decimal("0"),
        deposit_fee_amount=Decimal("24"),
    )
    assert (subtotal, shipping, payment, fees, total) == (
        Decimal("1000"),
        Decimal("200"),
        Decimal("0"),
        Decimal("224"),
        Decimal("1224"),
    )


def test_amount_due_follows_the_plan_and_the_settled_kinds() -> None:
    full = SimpleNamespace(payment_plan="full", total_amount=Decimal("1000"))
    assert next_payment_kind(full, set()) == "full"
    assert next_payment_kind(full, {"full"}) is None
    assert expected_amount(full, "full") == Decimal("1000")
    assert balance_amount(full) == Decimal("0")

    deposit = SimpleNamespace(
        payment_plan="deposit",
        total_amount=Decimal("1224"),
        deposit_amount=Decimal("367"),
        balance_paid_at=None,
        balance_requested_at=None,
    )
    assert next_payment_kind(deposit, set()) == "deposit"
    assert expected_amount(deposit, "deposit") == Decimal("367")
    assert next_payment_kind(deposit, {"deposit"}) == "balance"
    assert expected_amount(deposit, "balance") == Decimal("857")
    assert next_payment_kind(deposit, {"deposit", "balance"}) is None
    assert not balance_due(deposit)
    deposit.balance_requested_at = "2026-10-01"
    assert balance_due(deposit)
    deposit.balance_paid_at = "2026-10-02"
    assert not balance_due(deposit)
    assert next_payment_kind(deposit, {"deposit"}) is None
