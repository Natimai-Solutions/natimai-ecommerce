"""
PayZen payment gateway utilities.

This module provides utility functions for integrating with the PayZen payment gateway,
including signature validation, API communication, and payment form token generation.
"""

import base64
import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


def validate_ipn_signature(fields_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Validate the signature of a PayZen IPN notification (REST API V4.0).

    Args:
        fields_dict: Dictionary containing IPN fields (kr-* format)

    Returns:
        dict: Extracted payment data (without prefix)

    Raises:
        ValueError: If signature is invalid or data is missing
    """
    # PayZen REST API V4.0 uses kr-* format (KryptonClient)
    kr_hash = fields_dict.get("kr-hash")
    kr_hash_algorithm = fields_dict.get("kr-hash-algorithm")
    kr_answer = fields_dict.get("kr-answer")

    if not kr_hash:
        logger.warning(f"IPN fields received: {list(fields_dict.keys())}")
        raise ValueError("Missing signature in IPN (field 'kr-hash')")

    if not kr_answer:
        raise ValueError("Missing response data (field 'kr-answer')")

    # Get the appropriate HMAC key based on mode
    mode = settings.PAYZEN_MODE
    hmac_key = (
        settings.PAYZEN_API_PASSWORD_PROD
        if mode == "PRODUCTION"
        else settings.PAYZEN_API_PASSWORD_TEST
    )

    if not hmac_key:
        raise ValueError(
            f"PayZen API password not configured for mode {mode}. "
            f"Set PAYZEN_API_PASSWORD_{mode} in .env"
        )

    # Calculate HMAC-SHA256 signature of kr-answer
    # According to official PHP example:
    # - Key is used directly (UTF-8 string)
    # - Result is in HEXADECIMAL (not base64)
    # - Comparison: hash_hmac('sha256', $kr_answer, $key) == $kr_hash
    signature_calculated = hmac.new(
        hmac_key.encode("utf-8"),  # Key in UTF-8
        kr_answer.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()  # ← HEXADECIMAL (like PHP hash_hmac)

    # Verify signature — constant-time comparison (timing-safe)
    if not hmac.compare_digest(signature_calculated, kr_hash):
        logger.error(
            f"Invalid IPN signature - Expected: {signature_calculated[:20]}..., "
            f"Received: {kr_hash[:20]}..."
        )
        raise ValueError("Invalid IPN signature")

    # Parse kr-answer JSON
    try:
        answer_data = json.loads(kr_answer)
    except json.JSONDecodeError as e:
        raise ValueError(f"kr-answer is not valid JSON: {e}")

    logger.info(
        f"IPN signature validated successfully (algorithm: {kr_hash_algorithm})"
    )

    # Extract first transaction (main payment)
    transactions = answer_data.get("transactions", [])
    if not transactions:
        raise ValueError("No transaction found in kr-answer")

    transaction = transactions[0]
    order_details = answer_data.get("orderDetails", {})
    card_details = transaction.get("transactionDetails", {}).get("cardDetails", {})

    # Return fields without prefix (simpler)
    return {
        "order_id": order_details.get("orderId"),
        "trans_id": transaction.get("uuid"),
        "trans_uuid": transaction.get("uuid"),
        "amount": str(transaction.get("amount", 0)),
        "currency": str(transaction.get("currency", "953")),  # 953 = XPF
        "trans_status": transaction.get("status"),  # PAID, REFUSED, etc.
        "order_status": answer_data.get("orderStatus"),
        "payment_cards": card_details.get("brand", ""),
        "error_code": transaction.get("errorCode"),
        "error_message": transaction.get("errorMessage"),
        "url_check_src": answer_data.get("metadata", {}).get("source", "PAYMENT_FORM"),
        "_raw_answer": answer_data,  # Raw data for reference
    }


def _payzen_basic_auth() -> str:
    """Basic-auth credentials header value for the PayZen REST API."""
    username = settings.PAYZEN_SITE_ID
    password = (
        settings.PAYZEN_API_PASSWORD_TEST
        if settings.PAYZEN_MODE == "TEST"
        else settings.PAYZEN_API_PASSWORD_PROD
    )
    return base64.b64encode(f"{username}:{password}".encode()).decode()


async def capture_payzen_transaction(trans_uuid: str) -> dict[str, Any]:
    """Capture (validate) a PayZen transaction previously AUTHORISED in
    manual-validation mode — this triggers the actual card debit.

    Calls REST V4 ``Transaction/Validate``.
    ⚠️ To verify against the PayZen sandbox before production use.

    Returns the PayZen ``answer`` payload. Raises AppError on gateway/transport
    errors so the caller can mark the capture as failed.
    """
    api_url = f"{settings.PAYZEN_API_ENDPOINT}/api-payment/V4/Transaction/Validate"
    headers = {
        "Authorization": f"Basic {_payzen_basic_auth()}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url, json={"uuid": trans_uuid}, headers=headers, timeout=30.0
            )
            result = response.json()
            if result.get("status") == "ERROR":
                err = result.get("answer", {})
                logger.error(
                    "PayZen capture error [%s]: %s",
                    err.get("errorCode"),
                    err.get("errorMessage"),
                )
                raise AppError(
                    code="payment.provider.gateway_error",
                    status_code=502,
                    message=err.get("errorMessage") or "PayZen capture failed",
                    details={
                        "provider_code": "payzen",
                        "error_code": str(err.get("errorCode") or ""),
                    },
                )
            response.raise_for_status()
            answer: dict[str, Any] = result.get("answer", {})
            return answer
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.error("PayZen capture transport error: %s", e)
        raise AppError(
            code="internal.unavailable",
            status_code=503,
            message="Communication error with PayZen during capture",
            details={"service": "payzen"},
        ) from e


async def refund_payzen_transaction(
    trans_uuid: str, *, amount_minor: int, currency: str
) -> dict[str, Any]:
    """Refund (or cancel, when not yet settled) a PayZen card transaction.

    Calls REST V4 ``Transaction/CancelOrRefund``; used only when
    ``PAYZEN_API_REFUND_ENABLED`` is on. Returns the PayZen ``answer``.
    ⚠️ To verify against the PayZen sandbox before production use.
    """
    api_url = (
        f"{settings.PAYZEN_API_ENDPOINT}/api-payment/V4/Transaction/CancelOrRefund"
    )
    headers = {
        "Authorization": f"Basic {_payzen_basic_auth()}",
        "Content-Type": "application/json",
    }
    body = {"uuid": trans_uuid, "amount": amount_minor, "currency": currency}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url, json=body, headers=headers, timeout=30.0
            )
            result = response.json()
            if result.get("status") == "ERROR":
                err = result.get("answer", {})
                logger.error(
                    "PayZen refund error [%s]: %s",
                    err.get("errorCode"),
                    err.get("errorMessage"),
                )
                raise AppError(
                    code="payment.provider.gateway_error",
                    status_code=502,
                    message=err.get("errorMessage") or "PayZen refund failed",
                    details={
                        "provider_code": "payzen",
                        "error_code": str(err.get("errorCode") or ""),
                    },
                )
            response.raise_for_status()
            answer: dict[str, Any] = result.get("answer", {})
            return answer
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.error("PayZen refund transport error: %s", e)
        raise AppError(
            code="internal.unavailable",
            status_code=503,
            message="Communication error with PayZen during refund",
            details={"service": "payzen"},
        ) from e


async def create_payzen_form_token(
    *,
    amount: int,
    currency: str,
    order_id: str,
    customer_email: str,
    customer_reference: str,
    customer_first_name: str = "",
    customer_last_name: str = "",
    return_url: str | None = None,
    form_action: str = "SILENT",
    metadata: dict[str, Any] | None = None,
    manual_validation: bool = False,
) -> dict[str, Any]:
    """
    Create a formToken via PayZen REST API.

    Args:
        amount: Amount in cents (or smallest currency unit)
        currency: Currency code (XPF, EUR, etc.)
        order_id: Unique order identifier
        customer_email: Customer email
        customer_reference: Unique customer reference
        customer_first_name: Customer first name
        customer_last_name: Customer last name
        return_url: Return URL after payment (optional)
        form_action: Form action (SILENT, ASK_REGISTER_PAY, etc.)
        metadata: Additional metadata (optional)

    Returns:
        dict containing formToken and other PayZen info

    Raises:
        AppError on error
    """
    payload = {
        "amount": amount,
        "currency": currency,
        "orderId": order_id,
        "customer": {
            "email": customer_email,
            "reference": customer_reference,
            "billingDetails": {
                "firstName": customer_first_name,
                "lastName": customer_last_name,
            },
        },
        "ipnTargetUrl": settings.payzen_ipn_url_computed,
        "formAction": form_action,
    }

    # Authorise only (capture later, e.g. at shipment) instead of immediate debit.
    if manual_validation:
        payload["manualValidation"] = "YES"

    # Add metadata if provided
    if metadata:
        payload["metadata"] = metadata

    # Add return URL
    if return_url:
        payload["contrib"] = return_url
    elif settings.PAYZEN_RETURN_URL:
        payload["contrib"] = settings.PAYZEN_RETURN_URL

    # Authentication
    username = settings.PAYZEN_SITE_ID
    password = (
        settings.PAYZEN_API_PASSWORD_TEST
        if settings.PAYZEN_MODE == "TEST"
        else settings.PAYZEN_API_PASSWORD_PROD
    )
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()

    # API URL
    base_url = settings.PAYZEN_API_ENDPOINT
    api_url = f"{base_url}/api-payment/V4/Charge/CreatePayment"

    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url, json=payload, headers=headers, timeout=30.0
            )
            try:
                result = response.json()
            except ValueError as e:
                logger.error(f"Invalid JSON response from PayZen: {e}")
                raise AppError(
                    code="payment.provider.invalid_response",
                    status_code=502,
                    message="Invalid response from PayZen",
                    details={"provider_code": "payzen", "reason": "invalid_json"},
                ) from e

            logger.info(f"PayZen CreatePayment - Status: {response.status_code}")
            logger.debug(f"PayZen Response: {json.dumps(result, indent=2)}")

            # Handle PayZen errors
            if result.get("status") == "ERROR":
                error_code = result.get("answer", {}).get("errorCode")
                error_msg = result.get("answer", {}).get("errorMessage")
                detailed_msg = result.get("answer", {}).get("detailedErrorMessage")

                logger.error(f"PayZen error [{error_code}]: {error_msg}")
                logger.error(f"Details: {detailed_msg}")

                # Specific help messages
                if error_code == "INT_010":
                    help_msg = f"Currency {currency} is not supported."
                elif error_code == "PSP_610":
                    help_msg = f"No acceptance contract for currency {currency}."
                else:
                    help_msg = detailed_msg or error_msg

                raise AppError(
                    code="payment.provider.gateway_error",
                    status_code=502,
                    message=help_msg or "PayZen gateway returned an error",
                    details={
                        "provider_code": "payzen",
                        "error_code": str(error_code) if error_code else None,
                    },
                )

            response.raise_for_status()

            # Check for formToken presence
            if "answer" in result and "formToken" in result["answer"]:
                return {
                    "form_token": result["answer"]["formToken"],
                    "server_url": settings.PAYZEN_STATIC_URL,
                    "public_key": settings.PAYZEN_PUBLIC_KEY_TEST
                    if settings.PAYZEN_MODE == "TEST"
                    else settings.PAYZEN_PUBLIC_KEY_PROD,
                    "raw_response": result.get("answer", {}),
                }
            else:
                logger.error(f"Invalid PayZen response: {result}")
                raise AppError(
                    code="payment.provider.invalid_response",
                    status_code=502,
                    message="Error generating formToken",
                    details={
                        "provider_code": "payzen",
                        "reason": "missing_form_token",
                    },
                )

    except httpx.RequestError as e:
        logger.error(f"Error during PayZen request: {e}")
        raise AppError(
            code="internal.unavailable",
            status_code=503,
            message="Communication error with PayZen",
            details={"service": "payzen"},
        ) from e
    except httpx.HTTPStatusError as e:
        logger.error(f"PayZen HTTP error: {e.response.status_code} - {e.response.text}")
        raise AppError(
            code="internal.unavailable",
            status_code=503,
            message=f"PayZen error: {e.response.status_code}",
            details={"service": "payzen", "status_code": e.response.status_code},
        ) from e
    except AppError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise AppError(
            code="payment.provider.gateway_error",
            status_code=500,
            message="Internal server error during PayZen payment initiation",
            details={"provider_code": "payzen", "reason": type(e).__name__},
        ) from e
