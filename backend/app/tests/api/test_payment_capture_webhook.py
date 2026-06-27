"""Unit test: PayZen AUTHORISED trans_status maps to the 'Authorized' payment
status and does NOT publish a capture event (capture is deferred)."""

from app.api.routes.payments import (
    _resolve_outcome_event_for_trans_status,
    _resolve_payment_status_for_trans_status,
)


def test_authorised_maps_to_authorized_status_without_capture_event() -> None:
    assert _resolve_payment_status_for_trans_status("AUTHORISED") == "Authorized"
    assert _resolve_outcome_event_for_trans_status("AUTHORISED") is None


def test_paid_still_maps_to_completed_and_captured_event() -> None:
    assert _resolve_payment_status_for_trans_status("PAID") == "Completed"
    assert _resolve_outcome_event_for_trans_status("PAID") == "payment.captured"
