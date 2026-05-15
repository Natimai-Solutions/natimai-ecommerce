import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.features.attachment.service import (
    AttachmentValidationError,
    issue_upload_intent,
    register_uploaded_attachment,
)
from app.features.base.crud import RecordNotFoundError
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.order.models.order_status import OrderStatus, OrderStatusCreate
from app.features.payment.crud.payment import crud_payment
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment, PaymentCreate
from app.features.payment.models.payment_status import (
    PaymentStatus,
    PaymentStatusCreate,
)
from app.features.payment.providers import get_provider
from app.features.payment.providers.base import (
    ApiPaymentProvider,
    DocumentValidatedProvider,
    InitiationRequest,
    ManualPaymentProvider,
    UnknownPaymentProviderError,
)
from app.features.payment.services.document_payment import (
    DOCUMENT_PROVIDER_CODES,
    PaymentNotDocumentValidatedError,
    mark_document_uploaded,
)
from app.features.payment.services.document_payment import (
    register_intent as register_document_intent,
)
from app.features.payment.services.manual_payment import (
    register_intent as register_manual_intent,
)
from app.features.payment.services.provider_dispatch import (
    PaymentApiProviderResolutionError,
    PaymentMethodInactiveError,
    PaymentMethodNotFoundError,
    PaymentMethodResolutionError,
    initiate_api_payment,
    parse_api_webhook,
    resolve_api_provider,
    resolve_provider_code_for_payment_method,
)
from app.utils.money import decimal_to_minor_units

logger = logging.getLogger(__name__)

_PAID_TRANS_STATUS = "PAID"
_FAILED_TRANS_STATUSES = {"REFUSED", "ABANDONED", "CANCELLED"}
_TERMINAL_TRANS_STATUSES = {_PAID_TRANS_STATUS, *_FAILED_TRANS_STATUSES}

_PAYMENT_STATUS_COMPLETED = "Completed"
_PAYMENT_STATUS_FAILED = "Failed"

_ORDER_STATUS_PAID = "Paid"
_ORDER_STATUS_PAYMENT_FAILED = "PaymentFailed"


def validate_ipn_signature(fields_dict: dict[str, Any]) -> dict[str, Any]:
    webhook_result = parse_api_webhook("payzen", fields_dict)
    return webhook_result.payload


def _normalize_trans_status(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().upper()
    return normalized or None


def _extract_trans_id(fields: dict[str, object]) -> str | None:
    trans_id = fields.get("trans_uuid") or fields.get("trans_id")
    if trans_id is None:
        return None

    normalized = str(trans_id).strip()
    return normalized or None


def _is_duplicate_retry_for_payment(
    payment: Payment,
    *,
    trans_status: str | None,
    trans_id: str | None,
) -> bool:
    existing_status = _normalize_trans_status(payment.payzen_status)
    if existing_status is None or trans_status is None:
        return False

    if existing_status != trans_status:
        return False

    if trans_status in _TERMINAL_TRANS_STATUSES:
        return True

    if trans_id is None:
        return True

    return payment.payzen_trans_id == trans_id


def _is_conflicting_terminal_retry(
    payment: Payment,
    *,
    trans_status: str | None,
) -> bool:
    existing_status = _normalize_trans_status(payment.payzen_status)
    if existing_status is None or trans_status is None:
        return False

    return (
        existing_status in _TERMINAL_TRANS_STATUSES
        and trans_status in _TERMINAL_TRANS_STATUSES
        and existing_status != trans_status
    )


def _resolve_checkout_status_targets(
    trans_status: str | None,
) -> tuple[str | None, str | None]:
    if trans_status == _PAID_TRANS_STATUS:
        return _PAYMENT_STATUS_COMPLETED, _ORDER_STATUS_PAID

    if trans_status in _FAILED_TRANS_STATUSES:
        return _PAYMENT_STATUS_FAILED, _ORDER_STATUS_PAYMENT_FAILED

    return None, None


async def _get_or_create_payment_status(
    session: SessionDep,
    *,
    name: str,
) -> PaymentStatus:
    status_record = await crud_payment_status.get_by_name(session, name=name)
    if status_record is not None:
        return status_record

    return await crud_payment_status.create_draft(
        session=session,
        data=PaymentStatusCreate(
            name=name,
            description=f"Auto-created by PayZen IPN: {name}",
        ),
        user=None,
    )


async def _get_or_create_order_status(
    session: SessionDep,
    *,
    name: str,
) -> OrderStatus:
    status_record = await crud_order_status.get_by_name(session, name=name)
    if status_record is not None:
        return status_record

    return await crud_order_status.create_draft(
        session=session,
        data=OrderStatusCreate(name=name),
        user=None,
    )


async def _sync_checkout_entities_for_payzen_status(
    session: SessionDep,
    *,
    payment: Payment,
    trans_status: str | None,
) -> None:
    payment_status_name, order_status_name = _resolve_checkout_status_targets(
        trans_status
    )

    if payment_status_name is not None:
        payment_status = await _get_or_create_payment_status(
            session=session,
            name=payment_status_name,
        )
        payment.payment_status_id = payment_status.id
        session.add(payment)

    if payment.order_id is None or order_status_name is None:
        return

    order = await crud_order.read(session, id=payment.order_id)
    if order is None:
        logger.warning(
            "Unable to sync order status from IPN: order %s not found for payment %s",
            payment.order_id,
            payment.id,
        )
        return

    order_status = await _get_or_create_order_status(
        session=session,
        name=order_status_name,
    )
    order.order_status_id = order_status.id
    session.add(order)


async def payzen_ipn(session: SessionDep, request: Request) -> JSONResponse:
    error = None
    fields: dict[str, object] = {}

    try:
        form_data = await request.form()
        fields_dict = dict(form_data)
        fields = validate_ipn_signature(fields_dict)

        logger.info(
            "PayZen IPN received: order_id=%s, trans_status=%s, amount=%s",
            fields.get("order_id"),
            fields.get("trans_status"),
            fields.get("amount"),
        )

    except Exception as e:
        error = str(e)
        logger.error(f"Error processing PayZen IPN: {error}")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": error},
        )

    try:
        payzen_order_id_obj = fields.get("order_id")
        payzen_order_id = str(payzen_order_id_obj) if payzen_order_id_obj else ""
        if not payzen_order_id:
            raise ValueError("Missing order_id in PayZen IPN")

        payment = await crud_payment.get_by_payzen_order_id(
            session,
            payzen_order_id=payzen_order_id,
        )

        if not payment:
            try:
                payment_uuid = uuid.UUID(payzen_order_id)
                payment = await crud_payment.read(session, id=payment_uuid)
            except (ValueError, AttributeError):
                pass

        if not payment:
            logger.error(f"Payment not found for order_id: {payzen_order_id}")
            raise ValueError(f"Payment not found: {payzen_order_id}")

        trans_status = _normalize_trans_status(fields.get("trans_status"))
        trans_id = _extract_trans_id(fields)

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
                payment.payzen_status,
                trans_status,
            )
            return JSONResponse(
                content={
                    "status": "ok",
                    "message": "IPN terminal contradictoire ignore",
                },
            )

        if trans_status is not None:
            fields["trans_status"] = trans_status

        payment = await crud_payment.update_payment_from_payzen(
            session,
            payment=payment,
            payzen_fields=fields,
            commit=False,
        )

        await _sync_checkout_entities_for_payzen_status(
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

    except Exception as e:
        logger.error(f"Error updating payment from IPN: {e}")
        await session.rollback()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error processing payment"},
        )

    return JSONResponse(content={"status": "ok"})


class PaymentsInitiateRequest(BaseModel):
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
    payment_id: uuid.UUID
    provider_code: str
    provider_reference: str | None = None
    form_token: str | None = None
    server_url: str | None = None
    public_key: str | None = None
    redirect_url: str | None = None
    instructions: str | None = None


router = APIRouter(prefix="/payments", tags=["payment"])


def _build_initiation_request(
    *,
    payment_id: uuid.UUID,
    request: "PaymentsInitiateRequest",
    current_user: CurrentUser,
) -> InitiationRequest:
    amount_minor = decimal_to_minor_units(request.amount, request.currency)
    name_parts = current_user.full_name.split() if current_user.full_name else []
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    return InitiationRequest(
        amount=amount_minor,
        currency=request.currency,
        order_id=str(payment_id),
        customer_email=current_user.email,
        customer_reference=str(current_user.id),
        customer_first_name=first_name,
        customer_last_name=last_name,
        return_url=request.return_url,
        form_action="SILENT",
        metadata=request.metadata,
    )


@router.post("/initiate", response_model=PaymentsInitiateResponse)
async def initiate_payment(
    session: SessionDep,
    request: PaymentsInitiateRequest,
    current_user: CurrentUser,
) -> PaymentsInitiateResponse:
    try:
        provider_code = await resolve_provider_code_for_payment_method(
            session,
            request.payment_method_id,
        )
    except PaymentMethodNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except (PaymentMethodInactiveError, PaymentMethodResolutionError) as e:
        raise HTTPException(400, str(e)) from e

    try:
        provider = get_provider(provider_code)
    except UnknownPaymentProviderError as e:
        raise HTTPException(400, str(e)) from e

    payment_data = PaymentCreate(
        amount=request.amount,
        currency=request.currency,
        provider_code=provider_code,
        order_id=request.order_id,
        user_id=current_user.id,
    )
    payment = await crud_payment.create_payment_with_log(
        session,
        payment_data=payment_data,
        user=current_user,
        commit=False,
    )
    payment.payment_method_id = request.payment_method_id

    initiation_request = _build_initiation_request(
        payment_id=payment.id,
        request=request,
        current_user=current_user,
    )

    try:
        if isinstance(provider, ApiPaymentProvider):
            provider_result = await initiate_api_payment(
                provider_code,
                initiation_request,
            )

            payment.provider_code = provider_code
            payment.provider_reference = provider_result.provider_reference or str(
                payment.id
            )
            payment.provider_data = provider_result.raw_response

            if provider_code == "payzen":
                payment.payzen_form_token = provider_result.form_token
                payment.payzen_order_id = str(payment.id)

            session.add(payment)

        elif isinstance(provider, ManualPaymentProvider):
            provider_result = await provider.register_intent(initiation_request)

            payment.provider_code = provider_code
            payment.provider_reference = provider_result.provider_reference or str(
                payment.id
            )
            payment.provider_data = provider_result.raw_response

            await register_manual_intent(
                session,
                payment=payment,
                instructions=provider_result.instructions,
                user=current_user,
            )

        elif isinstance(provider, DocumentValidatedProvider):
            provider_result = await provider.register_intent(initiation_request)

            payment.provider_code = provider_code
            payment.provider_reference = provider_result.provider_reference or str(
                payment.id
            )
            payment.provider_data = provider_result.raw_response

            await register_document_intent(
                session,
                payment=payment,
                instructions=provider_result.instructions,
                user=current_user,
            )

        else:
            raise HTTPException(
                400,
                f"Provider '{provider_code}' does not support payment initiation",
            )

        await session.commit()
        await session.refresh(payment)

        return PaymentsInitiateResponse(
            payment_id=payment.id,
            provider_code=provider_code,
            provider_reference=payment.provider_reference,
            form_token=provider_result.form_token,
            server_url=provider_result.server_url,
            public_key=provider_result.public_key,
            redirect_url=provider_result.redirect_url,
            instructions=provider_result.instructions,
        )

    except HTTPException:
        await session.rollback()
        raise
    except PaymentApiProviderResolutionError as e:
        await session.rollback()
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        await session.rollback()
        logger.error(f"Error initiating payment: {e}")
        raise HTTPException(500, "Error initiating payment")


class UploadDocumentRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    mimetype: str = Field(..., min_length=1, max_length=100)
    document_type: str = Field(default="purchase_order", max_length=50)


class UploadDocumentResponse(BaseModel):
    payment_id: uuid.UUID
    file_key: str
    upload_url: str
    upload_method: str
    upload_headers: dict[str, str]
    expires_in: int
    max_bytes: int
    allowed_mime: list[str]


class DocumentUploadedRequest(BaseModel):
    file_key: str = Field(..., min_length=1, max_length=512)
    filename: str = Field(..., min_length=1, max_length=255)
    mimetype: str = Field(..., min_length=1, max_length=100)
    document_type: str = Field(default="purchase_order", max_length=50)


class DocumentUploadedResponse(BaseModel):
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
    try:
        payment = await crud_payment.read(session, id=payment_id)
    except RecordNotFoundError as e:
        raise HTTPException(404, f"Payment {payment_id} not found") from e

    if payment.user_id != current_user.id:
        raise HTTPException(403, "You cannot operate on this payment")

    if payment.provider_code not in DOCUMENT_PROVIDER_CODES:
        raise HTTPException(
            400,
            f"Payment provider '{payment.provider_code}' is not document-validated",
        )
    return payment


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
        raise HTTPException(400, str(e)) from e

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
    payment = await _resolve_owned_document_payment(
        session, payment_id=payment_id, current_user=current_user
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
        raise HTTPException(400, str(e)) from e

    try:
        await mark_document_uploaded(
            session,
            payment=payment,
            attachment=attachment,
            user=current_user,
        )
    except PaymentNotDocumentValidatedError as e:
        await session.rollback()
        raise HTTPException(400, str(e)) from e

    await session.commit()
    await session.refresh(payment)
    await session.refresh(attachment)

    return DocumentUploadedResponse(
        payment_id=payment.id,
        attachment_id=attachment.id,
        payment_status_id=payment.payment_status_id,
        av_scan="queued",
    )


@router.post("/webhooks/{provider_code}")
async def process_provider_webhook(
    provider_code: str,
    session: SessionDep,
    request: Request,
) -> JSONResponse:
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
