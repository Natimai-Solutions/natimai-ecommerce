"""PayPal (Orders API v2) — R3-P7.

The flow is a redirection:

1. ``initiate_payment`` creates a PayPal order and returns its approval link
   (``redirect_url``); the storefront sends the customer there;
2. PayPal sends the customer back to ``/paiement/retour?payment=<id>&provider=
   paypal``; the storefront calls ``POST /payments/me/{id}/confirm`` and
   ``confirm_payment`` captures (or authorizes) the order server-side;
3. PayPal's notifications (``POST /payments/webhooks/paypal``) are verified
   with PayPal's own API and go through the generic pipeline — a capture
   the confirmation already applied is recognised as a duplicate.

PayPal does not know the Pacific franc: an XPF order is charged in euros at
the fixed parity (1 000 XPF = 8,38 EUR). What was charged is recorded on the
payment (``charged_amount_minor`` / ``charged_currency``) and every
notification is checked against it.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from app.core.config import settings
from app.features.payment.providers.base import (
    OUTCOME_AUTHORIZED,
    OUTCOME_COMPLETED,
    OUTCOME_FAILED,
    OUTCOME_REFUNDED,
    ApiPaymentProvider,
    CaptureResult,
    InitiationRequest,
    InitiationResult,
    PaymentProviderError,
    ProviderOutcome,
    RefundResult,
    WebhookResult,
)
from app.utils.money import decimal_to_minor_units, minor_units_to_decimal

logger = logging.getLogger(__name__)

_BASE_URLS = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
}
#: 1 000 XPF = 8,38 EUR (parité fixe du franc Pacifique).
XPF_PER_EUR_RATE = Decimal("8.38") / Decimal("1000")

#: Test seam: an ``httpx`` transport replacing the network (MockTransport).
transport: httpx.AsyncBaseTransport | None = None

# (client id, mode) → (access token, expiry as time.monotonic()).
_token_cache: dict[tuple[str, str], tuple[str, float]] = {}

_CAPTURE_OUTCOMES = {
    "COMPLETED": OUTCOME_COMPLETED,
    "DECLINED": OUTCOME_FAILED,
    "FAILED": OUTCOME_FAILED,
    "REFUNDED": OUTCOME_REFUNDED,
    "PARTIALLY_REFUNDED": OUTCOME_REFUNDED,
}
_WEBHOOK_OUTCOMES = {
    "PAYMENT.CAPTURE.COMPLETED": OUTCOME_COMPLETED,
    "PAYMENT.CAPTURE.DENIED": OUTCOME_FAILED,
    "PAYMENT.CAPTURE.DECLINED": OUTCOME_FAILED,
    "PAYMENT.CAPTURE.REFUNDED": OUTCOME_REFUNDED,
    "PAYMENT.CAPTURE.REVERSED": OUTCOME_REFUNDED,
    "PAYMENT.AUTHORIZATION.CREATED": OUTCOME_AUTHORIZED,
    "PAYMENT.AUTHORIZATION.VOIDED": OUTCOME_FAILED,
}


def charge_amount(amount_minor: int, currency: str) -> tuple[Decimal, str]:
    """What PayPal charges for an amount of the shop (value, currency)."""
    target = settings.PAYPAL_CURRENCY.upper()
    source = currency.upper()
    amount = minor_units_to_decimal(amount_minor, source)
    if source == target:
        return amount, target
    if source == "XPF" and target == "EUR":
        return (amount * XPF_PER_EUR_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ), target
    raise PaymentProviderError(f"PayPal: no conversion from {source} to {target}")


def _with_query(url: str, **params: str) -> str:
    parts = urlsplit(url)
    query = f"{parts.query}&{urlencode(params)}" if parts.query else urlencode(params)
    return urlunsplit(parts._replace(query=query))


class PaypalProvider(ApiPaymentProvider):
    """PayPal checkout (redirection) with server-side capture."""

    code = "paypal"
    supports_in_app_refund = True
    generic_webhooks = True

    # -- HTTP ---------------------------------------------------------------

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=_BASE_URLS[settings.PAYPAL_MODE],
            timeout=20.0,
            transport=transport,
        )

    async def _token(self, client: httpx.AsyncClient) -> str:
        client_id = settings.PAYPAL_CLIENT_ID or ""
        secret = settings.PAYPAL_CLIENT_SECRET or ""
        if not client_id or not secret:
            raise PaymentProviderError("PayPal credentials are not configured")
        key = (client_id, settings.PAYPAL_MODE)
        cached = _token_cache.get(key)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        response = await client.post(
            "/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, secret),
        )
        if response.status_code != 200:
            raise PaymentProviderError(
                f"PayPal authentication failed ({response.status_code})"
            )
        body = response.json()
        token = str(body["access_token"])
        # Renewed a minute before PayPal expires it.
        _token_cache[key] = (
            token,
            time.monotonic() + max(int(body.get("expires_in", 0)) - 60, 0),
        )
        return token

    async def _call(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> httpx.Response:
        async with self._client() as client:
            token = await self._token(client)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            }
            if request_id:
                # PayPal's idempotency key: a retried call is not re-executed.
                headers["PayPal-Request-Id"] = request_id
            try:
                return await client.request(
                    method, path, json=json_body, headers=headers
                )
            except httpx.HTTPError as exc:
                raise PaymentProviderError(f"PayPal unreachable: {exc}") from exc

    # -- Initiation -----------------------------------------------------------

    async def initiate_payment(self, request: InitiationRequest) -> InitiationResult:
        value, currency = charge_amount(request.amount, request.currency)
        payment_id = request.order_id
        return_base = request.return_url or f"{settings.FRONTEND_HOST}/paiement/retour"
        return_url = _with_query(return_base, payment=payment_id, provider=self.code)
        cancel_url = _with_query(
            return_base, payment=payment_id, provider=self.code, cancelled="1"
        )
        body = {
            "intent": settings.PAYPAL_INTENT,
            "purchase_units": [
                {
                    "reference_id": payment_id,
                    "custom_id": payment_id,
                    "invoice_id": payment_id,
                    "description": f"{settings.PROJECT_NAME} — paiement {payment_id[:8]}",
                    "amount": {"currency_code": currency, "value": f"{value:.2f}"},
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "brand_name": settings.PROJECT_NAME[:127],
                        "locale": "fr-FR",
                        "shipping_preference": "NO_SHIPPING",
                        "user_action": "PAY_NOW",
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                    }
                }
            },
        }
        response = await self._call(
            "POST", "/v2/checkout/orders", json_body=body, request_id=payment_id
        )
        if response.status_code not in (200, 201):
            logger.error(
                "PayPal order creation failed (%s): %s",
                response.status_code,
                response.text[:500],
            )
            raise PaymentProviderError("PayPal refused to create the order")
        order = response.json()
        approve = next(
            (
                link["href"]
                for link in order.get("links", [])
                if link.get("rel") in ("payer-action", "approve")
            ),
            None,
        )
        if not approve:
            raise PaymentProviderError("PayPal returned no approval link")
        return InitiationResult(
            provider_code=self.code,
            provider_reference=str(order["id"]),
            redirect_url=str(approve),
            raw_response={
                "paypal_order_id": str(order["id"]),
                "intent": settings.PAYPAL_INTENT,
                "charged_amount_minor": decimal_to_minor_units(value, currency),
                "charged_currency": currency,
            },
        )

    # -- Confirmation after the customer's approval ---------------------------

    async def confirm_payment(
        self, *, provider_reference: str, provider_data: Mapping[str, Any] | None
    ) -> ProviderOutcome:
        intent = str((provider_data or {}).get("intent") or settings.PAYPAL_INTENT)
        action = "authorize" if intent == "AUTHORIZE" else "capture"
        response = await self._call(
            "POST",
            f"/v2/checkout/orders/{provider_reference}/{action}",
            json_body={},
            request_id=f"{provider_reference}-{action}",
        )
        if response.status_code == 422:
            issue = _issue(response)
            if issue in ("ORDER_ALREADY_CAPTURED", "ORDER_ALREADY_AUTHORIZED"):
                response = await self._call(
                    "GET", f"/v2/checkout/orders/{provider_reference}"
                )
            elif issue in ("INSTRUMENT_DECLINED", "PAYER_ACTION_REQUIRED"):
                return ProviderOutcome(
                    provider_code=self.code,
                    status=OUTCOME_FAILED,
                    payment_reference=provider_reference,
                    event_type=f"CONFIRM.{issue}",
                    payload={"issue": issue},
                )
            elif issue == "ORDER_NOT_APPROVED":
                # The customer came back without approving: nothing happened.
                return ProviderOutcome(
                    provider_code=self.code,
                    status=None,
                    payment_reference=provider_reference,
                    event_type=f"CONFIRM.{issue}",
                )
        if response.status_code not in (200, 201):
            logger.error(
                "PayPal %s of order %s failed (%s): %s",
                action,
                provider_reference,
                response.status_code,
                response.text[:500],
            )
            raise PaymentProviderError(f"PayPal {action} failed")
        return self._order_outcome(response.json(), provider_reference)

    def _order_outcome(
        self, order: dict[str, Any], provider_reference: str
    ) -> ProviderOutcome:
        unit = (order.get("purchase_units") or [{}])[0]
        payments = unit.get("payments") or {}
        custom_id = unit.get("custom_id") or unit.get("reference_id")
        capture = (payments.get("captures") or [None])[0]
        if capture:
            amount = capture.get("amount") or {}
            return ProviderOutcome(
                provider_code=self.code,
                status=_CAPTURE_OUTCOMES.get(str(capture.get("status"))),
                payment_reference=custom_id or provider_reference,
                event_type=f"CONFIRM.CAPTURE.{capture.get('status')}",
                transaction_id=capture.get("id"),
                amount_minor=_minor(amount),
                currency=amount.get("currency_code"),
                payload={"order_id": order.get("id"), "capture": capture},
                extra={"capture_id": capture.get("id")},
            )
        authorization = (payments.get("authorizations") or [None])[0]
        if authorization:
            amount = authorization.get("amount") or {}
            status = str(authorization.get("status"))
            return ProviderOutcome(
                provider_code=self.code,
                status=OUTCOME_AUTHORIZED
                if status in ("CREATED", "PENDING")
                else OUTCOME_FAILED
                if status in ("DENIED", "VOIDED", "EXPIRED")
                else None,
                payment_reference=custom_id or provider_reference,
                event_type=f"CONFIRM.AUTHORIZATION.{status}",
                transaction_id=authorization.get("id"),
                amount_minor=_minor(amount),
                currency=amount.get("currency_code"),
                payload={"order_id": order.get("id"), "authorization": authorization},
                extra={"authorization_id": authorization.get("id")},
            )
        return ProviderOutcome(
            provider_code=self.code,
            status=None,
            payment_reference=custom_id or provider_reference,
            event_type=f"CONFIRM.ORDER.{order.get('status')}",
        )

    # -- Notifications --------------------------------------------------------

    async def parse_webhook(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> ProviderOutcome:
        if not settings.PAYPAL_WEBHOOK_ID:
            raise PaymentProviderError("PAYPAL_WEBHOOK_ID is not configured")
        try:
            event = json.loads(raw_body)
        except ValueError as exc:
            raise PaymentProviderError("PayPal notification is not JSON") from exc
        if not isinstance(event, dict):
            raise PaymentProviderError("PayPal notification is not an object")

        lowered = {key.lower(): value for key, value in headers.items()}
        verification = {
            "auth_algo": lowered.get("paypal-auth-algo"),
            "cert_url": lowered.get("paypal-cert-url"),
            "transmission_id": lowered.get("paypal-transmission-id"),
            "transmission_sig": lowered.get("paypal-transmission-sig"),
            "transmission_time": lowered.get("paypal-transmission-time"),
            "webhook_id": settings.PAYPAL_WEBHOOK_ID,
            "webhook_event": event,
        }
        if not all(verification.values()):
            raise PaymentProviderError("PayPal signature headers are missing")
        response = await self._call(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            json_body=verification,
        )
        if (
            response.status_code != 200
            or response.json().get("verification_status") != "SUCCESS"
        ):
            raise PaymentProviderError("PayPal signature verification failed")

        event_type = str(event.get("event_type") or "")
        resource = event.get("resource") or {}
        amount = resource.get("amount") or {}
        related = (resource.get("supplementary_data") or {}).get("related_ids") or {}
        extra: dict[str, Any] = {}
        if event_type.startswith("PAYMENT.CAPTURE."):
            extra["capture_id"] = resource.get("id")
        elif event_type.startswith("PAYMENT.AUTHORIZATION."):
            extra["authorization_id"] = resource.get("id")
        return ProviderOutcome(
            provider_code=self.code,
            status=_WEBHOOK_OUTCOMES.get(event_type),
            payment_reference=resource.get("custom_id") or related.get("order_id"),
            event_id=str(event.get("id")) if event.get("id") else None,
            event_type=event_type,
            transaction_id=resource.get("id"),
            amount_minor=_minor(amount),
            currency=amount.get("currency_code"),
            payload={"event_type": event_type, "resource": resource},
            extra={key: value for key, value in extra.items() if value},
        )

    def parse_webhook_notification(self, payload: dict[str, Any]) -> WebhookResult:
        raise PaymentProviderError(
            "PayPal notifications must be verified: use parse_webhook"
        )

    # -- Back office: capture of an authorization, refunds --------------------

    def capture_reference(self, provider_data: Mapping[str, Any] | None) -> str | None:
        raw = (provider_data or {}).get("authorization_id")
        return str(raw) if raw else None

    def refund_reference(
        self,
        *,
        provider_data: Mapping[str, Any] | None,
        provider_reference: str | None,
        fallback: str,
    ) -> str:
        raw = (provider_data or {}).get("capture_id")
        if not raw:
            raise PaymentProviderError("PayPal capture id unknown for this payment")
        return str(raw)

    async def capture(
        self,
        *,
        payment_reference: str,
        amount: Decimal,
        currency: str,
    ) -> CaptureResult:
        response = await self._call(
            "POST",
            f"/v2/payments/authorizations/{payment_reference}/capture",
            json_body={"final_capture": True},
            request_id=f"{payment_reference}-capture",
        )
        if response.status_code not in (200, 201):
            logger.error(
                "PayPal capture of %s failed (%s): %s",
                payment_reference,
                response.status_code,
                response.text[:500],
            )
            return CaptureResult(status="failed", message="PayPal a refusé la capture.")
        capture = response.json()
        status = str(capture.get("status"))
        if status not in ("COMPLETED", "PENDING"):
            return CaptureResult(
                status="failed", message=f"Capture PayPal au statut {status}."
            )
        return CaptureResult(
            status="completed",
            provider_reference=capture.get("id"),
            message="Capture PayPal effectuée."
            if status == "COMPLETED"
            else "Capture PayPal en cours de traitement chez PayPal.",
        )

    async def refund(
        self,
        *,
        payment_reference: str,
        amount: Decimal,
        currency: str,
        reason: str | None = None,
    ) -> RefundResult:
        value, charged_currency = charge_amount(
            decimal_to_minor_units(amount, currency), currency
        )
        body: dict[str, Any] = {
            "amount": {"currency_code": charged_currency, "value": f"{value:.2f}"}
        }
        if reason:
            body["note_to_payer"] = reason[:255]
        response = await self._call(
            "POST",
            f"/v2/payments/captures/{payment_reference}/refund",
            json_body=body,
            request_id=str(uuid.uuid4()),
        )
        if response.status_code not in (200, 201):
            logger.error(
                "PayPal refund of %s failed (%s): %s",
                payment_reference,
                response.status_code,
                response.text[:500],
            )
            return RefundResult(
                status="failed",
                message=f"PayPal a refusé le remboursement ({_issue(response) or response.status_code}).",
            )
        refund = response.json()
        status = str(refund.get("status"))
        return RefundResult(
            status="completed" if status == "COMPLETED" else "pending",
            provider_reference=refund.get("id"),
            message="Remboursement PayPal effectué."
            if status == "COMPLETED"
            else "Remboursement PayPal en cours de traitement chez PayPal.",
            metadata={
                "charged_amount": str(value),
                "charged_currency": charged_currency,
            },
        )


def _minor(amount: Mapping[str, Any]) -> int | None:
    value = amount.get("value")
    currency = amount.get("currency_code")
    if value is None or not currency:
        return None
    try:
        return decimal_to_minor_units(Decimal(str(value)), str(currency))
    except ArithmeticError:
        return None


def _issue(response: httpx.Response) -> str | None:
    try:
        details = response.json().get("details") or []
    except ValueError:
        return None
    return str(details[0].get("issue")) if details else None


__all__ = ["PaypalProvider", "XPF_PER_EUR_RATE", "charge_amount"]
