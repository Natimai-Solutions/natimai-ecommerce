"""Unit test: PayZen AUTHORISED trans_status maps to the 'Authorized' payment
status and does NOT publish a capture event (capture is deferred)."""

from app.api.routes.payments import (
    _resolve_outcome_event_for_trans_status,
    _resolve_payment_status_for_trans_status,
)


def test_authorised_maps_to_authorized_status_and_its_own_event() -> None:
    """Not a capture, but not silence either (audit 2026-11, B3): the order
    is secured and must leave « Pending »."""
    assert _resolve_payment_status_for_trans_status("AUTHORISED") == "Authorized"
    assert _resolve_outcome_event_for_trans_status("AUTHORISED") == "payment.authorized"


def test_paid_still_maps_to_completed_and_captured_event() -> None:
    assert _resolve_payment_status_for_trans_status("PAID") == "Completed"
    assert _resolve_outcome_event_for_trans_status("PAID") == "payment.captured"
