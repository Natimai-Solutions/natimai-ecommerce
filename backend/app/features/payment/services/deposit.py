"""Deposit at order time (« acompte à la commande »).

The policy lives on the customer's price group (share of the total, optional
fee, imposed or offered). An order placed with a deposit carries
``payment_plan="deposit"``: the checkout charges ``deposit_amount`` (kind
``deposit``), the balance is asked for when the goods are received (kind
``balance``). Every guard that used to assume « one payment = the order
total » asks :func:`expected_amount` instead.

Pure functions, no session: the checkout, the payment guards and the
handlers share them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.core.errors import AppError
from app.utils.money import quantize_amount

PLAN_FULL = "full"
PLAN_DEPOSIT = "deposit"
PAYMENT_PLANS: tuple[str, ...] = (PLAN_FULL, PLAN_DEPOSIT)

KIND_FULL = "full"
KIND_DEPOSIT = "deposit"
KIND_BALANCE = "balance"
PAYMENT_KINDS: tuple[str, ...] = (KIND_FULL, KIND_DEPOSIT, KIND_BALANCE)

#: Order status once the deposit is captured (the balance is still due).
ORDER_STATUS_DEPOSIT_PAID = "DepositPaid"

_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class DepositPolicy:
    """What a price group allows: ``pct`` None = no deposit offered."""

    pct: Decimal | None = None
    fee_pct: Decimal = _ZERO
    fee_fixed: Decimal = _ZERO
    required: bool = False

    @property
    def available(self) -> bool:
        return self.pct is not None and self.pct > 0

    @classmethod
    def of(cls, group: Any) -> DepositPolicy:
        """From a price group (or anything with the same attributes)."""
        if group is None:
            return cls()
        pct = getattr(group, "deposit_pct", None)
        return cls(
            pct=Decimal(str(pct)) if pct is not None else None,
            fee_pct=Decimal(str(getattr(group, "deposit_fee_pct", None) or 0)),
            fee_fixed=Decimal(str(getattr(group, "deposit_fee_fixed", None) or 0)),
            required=bool(getattr(group, "deposit_required", False)),
        )


def choose_plan(policy: DepositPolicy, requested: str | None) -> str:
    """The plan the order will follow: what the customer asked for, within
    what the policy allows (an imposed deposit wins, an unavailable one is
    refused rather than silently charged in full)."""
    if not policy.available:
        if requested == PLAN_DEPOSIT:
            raise AppError(
                code="checkout.deposit.unavailable",
                status_code=400,
                message="L'acompte à la commande n'est pas proposé pour votre compte",
                details={},
            )
        return PLAN_FULL
    if policy.required or requested == PLAN_DEPOSIT:
        return PLAN_DEPOSIT
    return PLAN_FULL


def deposit_fee(policy: DepositPolicy, base_total: Decimal, currency: str) -> Decimal:
    """Fee of the deposit option on ``base_total`` (goods + other fees)."""
    fee = base_total * policy.fee_pct / Decimal(100) + policy.fee_fixed
    return quantize_amount(fee, currency)


def deposit_split(
    policy: DepositPolicy, total: Decimal, currency: str
) -> tuple[Decimal, Decimal]:
    """``(deposit, balance)`` of ``total`` (fee included); they add up exactly."""
    deposit = quantize_amount(total * (policy.pct or _ZERO) / Decimal(100), currency)
    return deposit, quantize_amount(total - deposit, currency)


def balance_amount(order: Any) -> Decimal:
    """What is left to pay on a deposit order (0 for a full-payment order)."""
    if getattr(order, "payment_plan", PLAN_FULL) != PLAN_DEPOSIT:
        return _ZERO
    return Decimal(order.total_amount) - Decimal(order.deposit_amount or 0)


def expected_amount(order: Any, kind: str) -> Decimal:
    """The amount a payment of ``kind`` must carry to settle its part."""
    if kind == KIND_DEPOSIT:
        return Decimal(order.deposit_amount or 0)
    if kind == KIND_BALANCE:
        return balance_amount(order)
    return Decimal(order.total_amount)


def remaining_amount(order: Any, kind: str, settled: Mapping[str, Decimal]) -> Decimal:
    """What is left to pay on a part, given the amounts already settled on
    it (a store credit and a card payment can share one part)."""
    return max(_ZERO, expected_amount(order, kind) - settled.get(kind, _ZERO))


def next_payment_kind(order: Any, settled: Mapping[str, Decimal]) -> str | None:
    """Which payment the order still accepts, given the amounts already
    settled per kind; ``None`` when nothing is due any more."""
    if getattr(order, "payment_plan", PLAN_FULL) != PLAN_DEPOSIT:
        return KIND_FULL if remaining_amount(order, KIND_FULL, settled) > 0 else None
    if remaining_amount(order, KIND_DEPOSIT, settled) > 0:
        return KIND_DEPOSIT
    if getattr(order, "balance_paid_at", None):
        return None
    return KIND_BALANCE if remaining_amount(order, KIND_BALANCE, settled) > 0 else None


def balance_due(order: Any) -> bool:
    """A deposit order whose balance has been asked for and not paid yet."""
    return (
        getattr(order, "payment_plan", PLAN_FULL) == PLAN_DEPOSIT
        and getattr(order, "balance_requested_at", None) is not None
        and getattr(order, "balance_paid_at", None) is None
    )


__all__ = [
    "KIND_BALANCE",
    "KIND_DEPOSIT",
    "KIND_FULL",
    "ORDER_STATUS_DEPOSIT_PAID",
    "PAYMENT_KINDS",
    "PAYMENT_PLANS",
    "PLAN_DEPOSIT",
    "PLAN_FULL",
    "DepositPolicy",
    "balance_amount",
    "balance_due",
    "choose_plan",
    "deposit_fee",
    "deposit_split",
    "expected_amount",
    "next_payment_kind",
    "remaining_amount",
]
