import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.errors import AppError
from app.features.attachment.service import (
    AttachmentValidationError,
    issue_upload_intent,
    register_uploaded_attachment,
)
from app.features.base.crud import RecordNotFoundError
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import (
    PaymentStatus,
    PaymentStatusCreate,
)
from app.features.payment.services.document_payment import (
    DOCUMENT_PROVIDER_CODES,
    PaymentNotDocumentValidatedError,
    mark_document_uploaded,
)
from app.features.payment.services.eligibility import (
    get_eligible_payment_methods,
)
from app.features.payment.services.payment_initiation import (
    initiate_payment_for_method,
)
from app.features.payment.services.provider_dispatch import (
    PaymentApiProviderResolutionError,
    parse_api_webhook,
    resolve_api_provider,
)
from app.outbox.registry import outbox_registry
from app.utils.money import minor_units_to_decimal, parse_minor_units, quantize_amount

logger = logging.getLogger(__name__)

_PAID_TRANS_STATUS = "PAID"
# Card authorised but not captured (PayZen manual-validation / deferred capture).
_AUTHORISED_TRANS_STATUS = "AUTHORISED"
_FAILED_TRANS_STATUSES = {"REFUSED", "ABANDONED", "CANCELLED"}
_TERMINAL_TRANS_STATUSES = {_PAID_TRANS_STATUS, *_FAILED_TRANS_STATUSES}
_SUCCESS_TRANS_STATUSES = {_PAID_TRANS_STATUS, _AUTHORISED_TRANS_STATUS}
# Order statuses that must not accept a new client-initiated payment.
# "PaymentReview" is set by app.handlers.payment when a capture does not match
# the order total: the order is under human arbitration, never re-payable.
_NON_PAYABLE_ORDER_STATUS_NAMES: frozenset[str] = frozenset(
    {"Paid", "Refunded", "PartiallyRefunded", "PaymentReview"}
)
_WEBHOOK_RECEIVED_EVENT = "payment.webhook_received"

_PAYMENT_STATUS_COMPLETED = "Completed"
_PAYMENT_STATUS_FAILED = "Failed"
_PAYMENT_STATUS_AUTHORIZED = "Authorized"
_TERMINAL_PAYMENT_STATUS_NAMES: frozenset[str] = frozenset(
    {_PAYMENT_STATUS_COMPLETED, _PAYMENT_STATUS_FAILED}
)
# Payment statuses meaning "this order has already been charged". The order
# status alone cannot be trusted here: it only flips to Paid asynchronously
# (outbox), leaving a window where a second charge would pass the status guard.
_SETTLED_PAYMENT_STATUS_NAMES: frozenset[str] = frozenset(
    {
        _PAYMENT_STATUS_COMPLETED,
        _PAYMENT_STATUS_AUTHORIZED,
        "Refunded",
        "PartiallyRefunded",
    }
)
# Order status names live in app.handlers.payment now — they are derived
# from the outbox event types this module publishes (payment.captured /
# payment.rejected).


def validate_ipn_signature(fields_dict: dict[str, Any]) -> dict[str, Any]:
    """Validate ipn signature."""
    webhook_result = parse_api_webhook("payzen", fields_dict)
    return webhook_result.payload


def _normalize_trans_status(value: object | None) -> str | None:
    """Execute normalize trans status."""
    if not isinstance(value, str):
        return None

    normalized = value.strip().upper()
    return normalized or None


def _extract_trans_id(fields: dict[str, object]) -> str | None:
    """Execute extract trans id."""
    trans_id = fields.get("trans_uuid") or fields.get("trans_id")
    if trans_id is None:
        return None

    normalized = str(trans_id).strip()
    return normalized or None


def _jsonable_webhook_payload(payload: dict[str, Any]) -> dict[str, object]:
    """Execute jsonable webhook payload."""
    jsonable: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, str | int | float | bool) or value is None:
            jsonable[key] = value
        else:
            jsonable[key] = str(value)
    return jsonable


def _provider_data_as_dict(payment: Payment) -> dict[str, object]:
    """Execute provider data as dict."""
    if isinstance(payment.provider_data, dict):
        return payment.provider_data
    return {}


def _get_existing_provider_status(payment: Payment) -> str | None:
    """Get existing provider status."""
    provider_data = _provider_data_as_dict(payment)
    return _normalize_trans_status(provider_data.get("trans_status"))


def _get_existing_provider_trans_id(payment: Payment) -> str | None:
    """Get existing provider trans id."""
    provider_data = _provider_data_as_dict(payment)
    return _extract_trans_id(provider_data)


def _is_duplicate_retry_for_payment(
    payment: Payment,
    *,
    trans_status: str | None,
    trans_id: str | None,
) -> bool:
    """Check whether duplicate retry for payment."""
    existing_status = _get_existing_provider_status(payment)
    if existing_status is None or trans_status is None:
        return False

    if existing_status != trans_status:
        return False

    if trans_status in _TERMINAL_TRANS_STATUSES:
        return True

    if trans_id is None:
        return True

    return _get_existing_provider_trans_id(payment) == trans_id


def _is_conflicting_terminal_retry(
    payment: Payment,
    *,
    trans_status: str | None,
) -> bool:
    """Check whether conflicting terminal retry."""
    existing_status = _get_existing_provider_status(payment)
    if existing_status is None or trans_status is None:
        return False

    return (
        existing_status in _TERMINAL_TRANS_STATUSES
        and trans_status in _TERMINAL_TRANS_STATUSES
        and existing_status != trans_status
    )


def _resolve_payment_status_for_trans_status(trans_status: str | None) -> str | None:
    """Execute resolve payment status for trans status."""
    if trans_status == _PAID_TRANS_STATUS:
        return _PAYMENT_STATUS_COMPLETED
    if trans_status == _AUTHORISED_TRANS_STATUS:
        return _PAYMENT_STATUS_AUTHORIZED
    if trans_status in _FAILED_TRANS_STATUSES:
        return _PAYMENT_STATUS_FAILED
    return None


def _resolve_outcome_event_for_trans_status(trans_status: str | None) -> str | None:
    """Map a Payzen trans_status to the outbox event type the IPN should publish.

    Returning None means we do not publish (intermediate / non-terminal status).
    """
    if trans_status == _PAID_TRANS_STATUS:
        return "payment.captured"
    if trans_status in _FAILED_TRANS_STATUSES:
        return "payment.rejected"
    return None


async def _get_or_create_payment_status(
    session: SessionDep,
    *,
    name: str,
) -> PaymentStatus:
    """Get or create payment status."""
    status_record = await crud_payment_status.get_by_name(session, name=name)
    if status_record is not None:
        return status_record

    return await crud_payment_status.create_draft(
        session=session,
        data=PaymentStatusCreate(
            name=name,
            description=f"Auto-created by provider webhook: {name}",
        ),
        user=None,
    )


async def _sync_payment_status_for_provider_status(
    session: SessionDep,
    *,
    payment: Payment,
    trans_status: str | None,
) -> None:
    """Update Payment.payment_status_id inline. Order status sync is deferred to
    outbox handlers (`on_payment_captured` / `on_payment_rejected`).
    """
    payment_status_name = _resolve_payment_status_for_trans_status(trans_status)
    if payment_status_name is None:
        return

    payment_status = await _get_or_create_payment_status(
        session=session, name=payment_status_name
    )
    payment.payment_status_id = payment_status.id
    session.add(payment)


async def _publish_provider_outcome_event(
    session: SessionDep,
    *,
    payment: Payment,
    trans_status: str | None,
) -> None:
    """Execute publish provider outcome event."""
    event_type = _resolve_outcome_event_for_trans_status(trans_status)
    if event_type is None:
        return

    trans_id = _get_existing_provider_trans_id(payment)

    payload = {
        "payment_id": str(payment.id),
        "order_id": str(payment.order_id) if payment.order_id else None,
        "user_id": str(payment.user_id) if payment.user_id else None,
        "provider_code": payment.provider_code or "payzen",
        "provider_reference": payment.provider_reference,
        "action": "webhook",
        "admin_user_id": None,
        "reason": None,
        "reference": trans_id,
        "metadata": {
            "trans_status": trans_status,
            "trans_id": trans_id,
        },
    }
    await outbox_registry.publish(
        session=session,
        event_type=event_type,
        payload=payload,
        correlation_id=payment.id,
    )


async def _publish_provider_webhook_received_event(
    session: SessionDep,
    *,
    payment: Payment,
    raw_payload: dict[str, Any],
    validated_payload: dict[str, object],
    trans_status: str | None,
    trans_id: str | None,
) -> None:
    """Execute publish provider webhook received event."""
    user_id = getattr(payment, "user_id", None)
    order_id = getattr(payment, "order_id", None)

    payload = {
        "payment_id": str(payment.id),
        "order_id": str(order_id) if order_id else None,
        "user_id": str(user_id) if user_id else None,
        "provider_code": (getattr(payment, "provider_code", None) or "payzen"),
        "provider_reference": getattr(payment, "provider_reference", None),
        "action": "webhook_received",
        "admin_user_id": None,
        "reason": None,
        "reference": trans_id,
        "metadata": {
            "trans_status": trans_status,
            "trans_id": trans_id,
            "raw_payload": _jsonable_webhook_payload(raw_payload),
            "validated_payload": _jsonable_webhook_payload(validated_payload),
        },
    }
    await outbox_registry.publish(
        session=session,
        event_type=_WEBHOOK_RECEIVED_EVENT,
        payload=payload,
        correlation_id=payment.id,
    )


async def payzen_ipn(session: SessionDep, request: Request) -> JSONResponse:
    """Execute payzen ipn."""
    raw_fields: dict[str, Any] = {}
    fields: dict[str, Any] = {}

    try:
        form_data = await request.form()
        fields_dict = dict(form_data)
        raw_fields = dict(fields_dict)
        fields = validate_ipn_signature(fields_dict)

        logger.info(
            "PayZen IPN received: order_id=%s, trans_status=%s, amount=%s",
            fields.get("order_id"),
            fields.get("trans_status"),
            fields.get("amount"),
        )
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error processing PayZen IPN: {error_message}")
        raise AppError(
            code="payment.webhook.invalid_signature",
            status_code=400,
            message=error_message,
            details={"provider_code": "payzen"},
        ) from e

    provider_order_reference_obj = fields.get("order_id")
    provider_order_reference = (
        str(provider_order_reference_obj) if provider_order_reference_obj else ""
    )
    if not provider_order_reference:
        raise AppError(
            code="payment.webhook.missing_order_id",
            status_code=400,
            message="Missing order_id in PayZen IPN",
            details={"provider_code": "payzen"},
        )

    payment = await crud_payment.get_by_provider_reference(
        session,
        provider_code="payzen",
        provider_reference=provider_order_reference,
    )

    if not payment:
        try:
            payment_uuid = uuid.UUID(provider_order_reference)
            payment = await crud_payment.read(session, id=payment_uuid)
        except (ValueError, AttributeError, RecordNotFoundError):
            payment = None

    if not payment:
        logger.error(f"Payment not found for order_id: {provider_order_reference}")
        raise AppError(
            code="payment.webhook.payment_not_found",
            status_code=400,
            message=f"Payment not found: {provider_order_reference}",
            details={
                "provider_code": "payzen",
                "provider_reference": provider_order_reference,
            },
        )

    try:
        trans_status = _normalize_trans_status(fields.get("trans_status"))
        trans_id = _extract_trans_id(fields)

        await _publish_provider_webhook_received_event(
            session=session,
            payment=payment,
            raw_payload=raw_fields,
            validated_payload=fields,
            trans_status=trans_status,
            trans_id=trans_id,
        )

        if _is_duplicate_retry_for_payment(
            payment,
            trans_status=trans_status,
            trans_id=trans_id,
        ):
            logger.info(
                "Duplicate PayZen IPN ignored for payment_id=%s, trans_status=%s",
                payment.id,
                trans_status,
            )
            await session.commit()
            return JSONResponse(
                content={"status": "ok", "message": "IPN deja traite"},
            )

        if _is_conflicting_terminal_retry(
            payment,
            trans_status=trans_status,
        ):
            logger.warning(
                "Conflicting terminal PayZen IPN ignored for payment_id=%s: existing=%s incoming=%s",
                payment.id,
                _get_existing_provider_status(payment),
                trans_status,
            )
            await session.commit()
            return JSONResponse(
                content={
                    "status": "ok",
                    "message": "IPN terminal contradictoire ignore",
                },
            )

        # Defence in depth: a success IPN must charge exactly the amount the
        # payment was created with (derived from the order total at initiation).
        # The IPN is signed, so a mismatch means a tampered initiation or a
        # provider misconfiguration — record it and never complete the payment.
        raw_ipn_amount = fields.get("amount")
        if trans_status in _SUCCESS_TRANS_STATUSES and raw_ipn_amount is not None:
            try:
                ipn_amount: Decimal | None = minor_units_to_decimal(
                    parse_minor_units(raw_ipn_amount), payment.currency
                )
            except ValueError as parse_error:
                # An unreadable amount is handled exactly like a mismatch. The
                # payload is signed, so the error is deterministic: letting it
                # bubble up would answer 500 to every replay and PayZen would
                # retry the same IPN forever without ever succeeding.
                logger.error(
                    "PayZen IPN unreadable amount %r for payment_id=%s: %s",
                    raw_ipn_amount,
                    payment.id,
                    parse_error,
                )
                ipn_amount = None

            if ipn_amount != payment.amount:
                received_repr = (
                    str(ipn_amount) if ipn_amount is not None else str(raw_ipn_amount)
                )
                logger.error(
                    "PayZen IPN amount mismatch for payment_id=%s: "
                    "expected=%s received=%s trans_status=%s trans_id=%s "
                    "— payment left un-completed for manual review",
                    payment.id,
                    payment.amount,
                    received_repr,
                    trans_status,
                    trans_id,
                )
                provider_data = dict(_provider_data_as_dict(payment))
                provider_data["amount_mismatch"] = {
                    "expected": str(payment.amount),
                    "received": received_repr,
                    "unreadable": ipn_amount is None,
                    "trans_status": trans_status,
                    "trans_id": trans_id,
                }
                payment.provider_data = provider_data
                session.add(payment)
                await session.commit()
                return JSONResponse(
                    content={
                        "status": "error",
                        "message": "Montant IPN inattendu — paiement non complete",
                    },
                )

        if trans_status is not None:
            fields["trans_status"] = trans_status

        payment = await crud_payment.update_payment_from_webhook_payload(
            session,
            payment=payment,
            webhook_fields=fields,
            commit=False,
        )

        await _sync_payment_status_for_provider_status(
            session=session,
            payment=payment,
            trans_status=trans_status,
        )

        await _publish_provider_outcome_event(
            session=session,
            payment=payment,
            trans_status=trans_status,
        )

        await session.commit()
        await session.refresh(payment)

        logger.info(
            "Payment updated successfully: payment_id=%s, status=%s",
            payment.id,
            trans_status,
        )
    except AppError:
        await session.rollback()
        raise
    except Exception as e:
        logger.error(f"Error updating payment from IPN: {e}")
        await session.rollback()
        raise

    return JSONResponse(content={"status": "ok"})


class PaymentsInitiateRequest(BaseModel):
    """Represents payments initiate request."""

    payment_method_id: uuid.UUID = Field(
        ..., description="Payment method to use for provider dispatch"
    )
    amount: Decimal = Field(
        ...,
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="Amount expressed in the payment currency",
    )
    currency: str = Field(default="XPF", description="Currency code (XPF, EUR, etc.)")
    order_id: uuid.UUID | None = Field(
        default=None,
        description="Order ID to associate with payment (optional)",
    )
    return_url: str | None = Field(
        default=None,
        description="URL to return to after payment",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Additional metadata for the payment",
    )


class PaymentsInitiateResponse(BaseModel):
    """Represents payments initiate response."""

    payment_id: uuid.UUID
    provider_code: str
    provider_reference: str | None = None
    form_token: str | None = None
    server_url: str | None = None
    public_key: str | None = None
    redirect_url: str | None = None
    instructions: str | None = None


router = APIRouter(prefix="/payments", tags=["payment"])


async def _validate_order_for_initiation(
    session: SessionDep,
    *,
    order_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    current_user: Any,
) -> None:
    """Server-side revalidation of a client-initiated payment tied to an order.

    The client-supplied amount and currency are never trusted: the order must
    exist and belong to the caller, must still be payable, must not already
    carry a settled payment, and the amount must equal the order total
    snapshotted at checkout. A foreign order is reported exactly like a missing
    one so ids cannot be probed.

    Caveat kept explicit: ``order.total_amount`` embeds the ``payment_fee_amount``
    the client sent at checkout (``routes/cart.py``), so this guard pins the
    payment to the order snapshot — it does not re-derive the fee itself.
    """
    order = await session.get(Order, order_id)
    if order is None or order.user_id != current_user.id:
        raise AppError(
            code="payment.order.not_found",
            status_code=404,
            message="Order not found",
            details={"order_id": str(order_id)},
        )

    order_status = await session.get(OrderStatus, order.order_status_id)
    if (
        order_status is not None
        and order_status.name in _NON_PAYABLE_ORDER_STATUS_NAMES
    ):
        raise AppError(
            code="payment.order.not_payable",
            status_code=409,
            message=f"Order does not accept payments in status '{order_status.name}'",
            details={
                "order_id": str(order_id),
                "order_status": order_status.name,
            },
        )

    # Every order gets a payment at checkout, oldest-first here, soft-deleted
    # rows included: that first payment is the currency reference (the order
    # itself does not store a currency) and the whole list tells us whether the
    # order has already been charged.
    order_payments = await crud_payment.list_with_status_by_order_id(
        session, order_id=order_id
    )

    settled = next(
        (
            (payment, status_name)
            for payment, status_name in order_payments
            if status_name in _SETTLED_PAYMENT_STATUS_NAMES
        ),
        None,
    )
    if settled is not None:
        settled_payment, settled_status = settled
        raise AppError(
            code="payment.order.already_paid",
            status_code=409,
            message="Order already has a settled payment",
            details={
                "order_id": str(order_id),
                "payment_id": str(settled_payment.id),
                "payment_status": settled_status,
            },
        )

    if not order_payments:
        # Fail closed: without a reference payment the currency cannot be
        # checked, and an unchecked currency lets a XPF amount settle an EUR
        # total (or the reverse).
        logger.error(
            "No payment found for order %s — refusing to initiate a payment "
            "whose currency cannot be validated",
            order_id,
        )
        raise AppError(
            code="payment.order.no_reference",
            status_code=409,
            message="Order has no reference payment to validate against",
            details={"order_id": str(order_id)},
        )

    reference_currency = order_payments[0][0].currency
    if currency != reference_currency:
        raise AppError(
            code="payment.currency.mismatch",
            status_code=409,
            message="Payment currency does not match the order currency",
            details={
                "order_id": str(order_id),
                "expected_currency": reference_currency,
            },
        )

    expected_amount = quantize_amount(order.total_amount, currency)
    if quantize_amount(amount, currency) != expected_amount:
        raise AppError(
            code="payment.amount.mismatch",
            status_code=409,
            message="Payment amount does not match the order total",
            details={
                "order_id": str(order_id),
                "expected_amount": str(expected_amount),
            },
        )


@router.post("/initiate", response_model=PaymentsInitiateResponse)
async def initiate_payment(
    session: SessionDep,
    request: PaymentsInitiateRequest,
    current_user: CurrentUser,
) -> PaymentsInitiateResponse:
    """Initiate a standalone payment for a method (CB SmartForm / manual / document)."""
    try:
        if request.order_id is not None:
            await _validate_order_for_initiation(
                session,
                order_id=request.order_id,
                amount=request.amount,
                currency=request.currency,
                current_user=current_user,
            )

        result = await initiate_payment_for_method(
            session,
            payment_method_id=request.payment_method_id,
            amount=request.amount,
            currency=request.currency,
            order_id=request.order_id,
            return_url=request.return_url,
            metadata=request.metadata,
            current_user=current_user,
        )

        await session.commit()
        await session.refresh(result.payment)

        return PaymentsInitiateResponse(
            payment_id=result.payment.id,
            provider_code=result.provider_code,
            provider_reference=result.provider_reference,
            form_token=result.form_token,
            server_url=result.server_url,
            public_key=result.public_key,
            redirect_url=result.redirect_url,
            instructions=result.instructions,
        )

    except AppError:
        await session.rollback()
        raise
    except PaymentApiProviderResolutionError as e:
        await session.rollback()
        raise AppError(
            code="payment.provider.api_resolution_failed",
            status_code=400,
            message=str(e),
            details={"payment_method_id": str(request.payment_method_id)},
        ) from e
    except Exception as e:
        await session.rollback()
        logger.error(f"Error initiating payment: {e}")
        raise


class UploadDocumentRequest(BaseModel):
    """Represents upload document request."""

    filename: str = Field(..., min_length=1, max_length=255)
    mimetype: str = Field(..., min_length=1, max_length=100)
    document_type: str = Field(default="purchase_order", max_length=50)


class UploadDocumentResponse(BaseModel):
    """Represents upload document response."""

    payment_id: uuid.UUID
    file_key: str
    upload_url: str
    upload_method: str
    upload_headers: dict[str, str]
    expires_in: int
    max_bytes: int
    allowed_mime: list[str]


class DocumentUploadedRequest(BaseModel):
    """Represents document uploaded request."""

    file_key: str = Field(..., min_length=1, max_length=512)
    filename: str = Field(..., min_length=1, max_length=255)
    mimetype: str = Field(..., min_length=1, max_length=100)
    document_type: str = Field(default="purchase_order", max_length=50)


class DocumentUploadedResponse(BaseModel):
    """Represents document uploaded response."""

    payment_id: uuid.UUID
    attachment_id: uuid.UUID
    payment_status_id: uuid.UUID | None
    av_scan: str = "queued"


async def _resolve_owned_document_payment(
    session: SessionDep,
    *,
    payment_id: uuid.UUID,
    current_user: CurrentUser,
) -> Any:
    """Execute resolve owned document payment."""
    try:
        payment = await crud_payment.read(session, id=payment_id)
    except RecordNotFoundError as e:
        raise AppError(
            code="payment.not_found",
            status_code=404,
            message=f"Payment {payment_id} not found",
            details={"payment_id": str(payment_id)},
        ) from e

    if payment.user_id != current_user.id:
        raise AppError(
            code="payment.not_owned",
            status_code=403,
            message="You cannot operate on this payment",
            details={"payment_id": str(payment_id)},
        )

    if payment.provider_code not in DOCUMENT_PROVIDER_CODES:
        raise AppError(
            code="payment.not_document_validated",
            status_code=400,
            message=(
                f"Payment provider '{payment.provider_code}' is not document-validated"
            ),
            details={
                "payment_id": str(payment_id),
                "provider_code": payment.provider_code,
            },
        )
    return payment


def _map_attachment_validation_error(
    error: AttachmentValidationError,
    *,
    mimetype: str,
) -> AppError:
    """Map attachment validation exceptions to stable API error codes."""
    message = str(error)

    if "is not allowed" in message:
        return AppError(
            code="attachment.mimetype_unsupported",
            status_code=400,
            message=message,
            details={
                "mimetype": mimetype,
                "allowed": ", ".join(settings.PAYMENT_ATTACHMENT_ALLOWED_MIME),
            },
        )

    if "exceeds the limit" in message:
        return AppError(
            code="attachment.too_large",
            status_code=400,
            message=message,
            details={"max_bytes": settings.PAYMENT_ATTACHMENT_MAX_BYTES},
        )

    return AppError(
        code="attachment.validation_failed",
        status_code=400,
        message=message,
        details={"reason": message},
    )


@router.post(
    "/{payment_id}/upload-document",
    response_model=UploadDocumentResponse,
)
async def issue_document_upload_url(
    payment_id: uuid.UUID,
    body: UploadDocumentRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> UploadDocumentResponse:
    """Execute issue document upload url."""
    await _resolve_owned_document_payment(
        session, payment_id=payment_id, current_user=current_user
    )

    try:
        intent = issue_upload_intent(
            payment_id=payment_id,
            filename=body.filename,
            mimetype=body.mimetype,
            document_type=body.document_type,
        )
    except AttachmentValidationError as e:
        raise _map_attachment_validation_error(e, mimetype=body.mimetype) from e

    return UploadDocumentResponse(
        payment_id=payment_id,
        file_key=intent.file_key,
        upload_url=intent.upload.url,
        upload_method=intent.upload.method,
        upload_headers=intent.upload.headers,
        expires_in=intent.upload.expires_in,
        max_bytes=intent.max_bytes,
        allowed_mime=intent.allowed_mime,
    )


@router.post(
    "/{payment_id}/document-uploaded",
    response_model=DocumentUploadedResponse,
)
async def confirm_document_uploaded(
    payment_id: uuid.UUID,
    body: DocumentUploadedRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> DocumentUploadedResponse:
    """Execute confirm document uploaded."""
    payment = await _resolve_owned_document_payment(
        session, payment_id=payment_id, current_user=current_user
    )

    expected_prefix = f"payments/{payment.id}/"
    if not body.file_key.startswith(expected_prefix):
        raise AppError(
            code="attachment.key_mismatch",
            status_code=400,
            message=(
                f"Uploaded file key '{body.file_key}' does not belong to payment '{payment.id}'"
            ),
            details={"file_key": body.file_key},
        )

    try:
        attachment = await register_uploaded_attachment(
            session,
            payment_id=payment.id,
            file_key=body.file_key,
            filename=body.filename,
            mimetype=body.mimetype,
            document_type=body.document_type,
            user=current_user,
        )
    except AttachmentValidationError as e:
        await session.rollback()
        raise _map_attachment_validation_error(e, mimetype=body.mimetype) from e

    try:
        await mark_document_uploaded(
            session,
            payment=payment,
            attachment=attachment,
            user=current_user,
        )
    except PaymentNotDocumentValidatedError as e:
        await session.rollback()
        raise AppError(
            code="payment.not_document_validated",
            status_code=400,
            message=str(e),
            details={
                "payment_id": str(payment_id),
                "provider_code": payment.provider_code,
            },
        ) from e

    await session.commit()
    await session.refresh(payment)
    await session.refresh(attachment)

    return DocumentUploadedResponse(
        payment_id=payment.id,
        attachment_id=attachment.id,
        payment_status_id=payment.payment_status_id,
        av_scan="queued",
    )


class PaymentStatusResponse(BaseModel):
    """Lightweight payment status for frontend polling."""

    payment_id: uuid.UUID
    status_name: str | None = None
    is_terminal: bool = False
    provider_code: str | None = None
    amount: Decimal
    currency: str
    order_id: uuid.UUID | None = None


@router.get("/me/methods", response_model=list[dict[str, Any]])
async def list_my_payment_methods(
    session: SessionDep,
    current_user: CurrentUser,
    cart_total: Decimal | None = None,
) -> list[dict[str, Any]]:
    """Return active payment methods available for the authenticated user.

    Filters by the user's price group and optional cart_total (max_amount check).
    Methods with no eligibility restriction are always included.

    IMPORTANT: declared BEFORE ``/me/{payment_id}`` — otherwise Starlette matches
    ``/me/methods`` against the parametrized route and tries to parse "methods"
    as a payment_id UUID (422).
    """
    from app.features.payment.models.payment_method import PaymentMethodPublic

    methods = await get_eligible_payment_methods(
        session,
        price_group_id=current_user.price_group_id,
        cart_total=cart_total,
    )
    return [PaymentMethodPublic.model_validate(m).model_dump() for m in methods]


@router.get("/me/{payment_id}", response_model=PaymentStatusResponse)
async def get_my_payment_status(
    payment_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> PaymentStatusResponse:
    """Return the current status of a payment belonging to the authenticated user.

    Designed for frontend polling after a Payzen SmartForm submission.
    Returns immediately with the latest DB state — no blocking wait.
    """
    try:
        payment = await crud_payment.read(session, id=payment_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="payment.not_found",
            status_code=404,
            message=f"Payment {payment_id} not found",
            details={"payment_id": str(payment_id)},
        ) from exc

    if payment.user_id != current_user.id:
        raise AppError(
            code="payment.not_owned",
            status_code=403,
            message="You cannot access this payment",
            details={"payment_id": str(payment_id)},
        )

    status_name: str | None = None
    if payment.payment_status_id is not None:
        status_record = await session.get(PaymentStatus, payment.payment_status_id)
        if status_record is not None:
            status_name = status_record.name

    return PaymentStatusResponse(
        payment_id=payment.id,
        status_name=status_name,
        is_terminal=status_name in _TERMINAL_PAYMENT_STATUS_NAMES,
        provider_code=payment.provider_code,
        amount=payment.amount,
        currency=payment.currency,
        order_id=payment.order_id,
    )


@router.post("/webhooks/{provider_code}")
async def process_provider_webhook(
    provider_code: str,
    session: SessionDep,
    request: Request,
) -> JSONResponse:
    """Execute process provider webhook."""
    normalized_provider_code = provider_code.strip().lower()

    if normalized_provider_code == "payzen":
        return await payzen_ipn(session=session, request=request)

    try:
        resolve_api_provider(normalized_provider_code)
    except PaymentApiProviderResolutionError as e:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": str(e)},
        )

    return JSONResponse(
        status_code=501,
        content={
            "status": "error",
            "message": f"Webhook processing not implemented for provider: {normalized_provider_code}",
        },
    )
