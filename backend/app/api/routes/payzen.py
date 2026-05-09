"""
PayZen payment integration routes.

This module provides API endpoints for PayZen payment gateway integration,
including form token generation and IPN (Instant Payment Notification) handling.
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import PaymentCreate
from app.features.payment.utils.payzen import (
    create_payzen_form_token,
    validate_ipn_signature,
)

logger = logging.getLogger(__name__)


# Pydantic models for API requests/responses
class FormTokenRequest(BaseModel):
    """Request model for PayZen form token generation."""

    amount: int = Field(..., gt=0, description="Amount in cents/smallest currency unit")
    currency: str = Field(default="XPF", description="Currency code (XPF, EUR, etc.)")
    order_id: uuid.UUID | None = Field(
        default=None, description="Order ID to associate with payment (optional)"
    )
    return_url: str | None = Field(
        default=None, description="URL to return to after payment"
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Additional metadata for the payment"
    )


class FormTokenResponse(BaseModel):
    """Response model for PayZen form token generation."""

    form_token: str = Field(..., description="PayZen form token")
    server_url: str = Field(..., description="PayZen server URL")
    public_key: str = Field(..., description="PayZen public key")
    payment_id: uuid.UUID = Field(..., description="Payment ID created in database")


router = APIRouter(prefix="/payzen", tags=["payment", "payzen"])


@router.post("/form-token", response_model=FormTokenResponse)
async def generate_form_token(
    session: SessionDep,
    request: FormTokenRequest,
    current_user: CurrentUser,
) -> FormTokenResponse:
    """
    Generate a PayZen form token for JavaScript payment integration.

    Conforms to PayZen documentation:
    https://secure.osb.pf/doc/fr-FR/rest/V4.0/javascript/guide/formToken/presentation.html

    This endpoint:
    1. Creates a Payment record with PENDING status
    2. Generates a PayZen form token
    3. Returns the token and payment info to the frontend
    """
    # Create payment record with pending status
    payment_data = PaymentCreate(
        amount=request.amount,
        currency=request.currency,
        order_id=request.order_id,
        user_id=current_user.id,
    )

    payment = await crud_payment.create_payment_with_log(
        session,
        payment_data=payment_data,
        user=current_user,
        commit=False,
    )

    # Generate PayZen form token
    try:
        payzen_result = await create_payzen_form_token(
            amount=request.amount,
            currency=request.currency,
            order_id=str(payment.id),  # Use payment ID as order ID
            customer_email=current_user.email,
            customer_reference=str(current_user.id),
            customer_first_name=current_user.full_name.split()[0]
            if current_user.full_name
            else "",
            customer_last_name=" ".join(current_user.full_name.split()[1:])
            if current_user.full_name and len(current_user.full_name.split()) > 1
            else "",
            return_url=request.return_url,
            form_action="SILENT",
            metadata=request.metadata,
        )

        # Update payment with PayZen data
        payment.payzen_form_token = payzen_result["form_token"]
        payment.payzen_order_id = str(payment.id)
        session.add(payment)

        await session.commit()
        await session.refresh(payment)

        return FormTokenResponse(
            form_token=payzen_result["form_token"],
            server_url=payzen_result["server_url"],
            public_key=payzen_result["public_key"],
            payment_id=payment.id,
        )

    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        logger.error(f"Error generating form token: {e}")
        raise HTTPException(500, "Error generating payment form token")


@router.post("/ipn")
async def payzen_ipn(session: SessionDep, request: Request) -> JSONResponse:
    """
    PayZen IPN (Instant Payment Notification) endpoint.

    Handles payment notifications from PayZen after a payment is processed.

    This endpoint:
    1. Validates the PayZen signature
    2. Updates the Payment record with the transaction result
    3. Creates a PaymentLog entry
    4. Updates payment status (PENDING -> VALIDATED or ERROR)
    """
    error = None
    fields = {}

    try:
        # Get form data from PayZen
        form_data = await request.form()
        fields_dict = dict(form_data)

        # Validate PayZen IPN signature and extract payment data
        fields = validate_ipn_signature(fields_dict)
        # Log IPN notification
        logger.info(
            f"PayZen IPN received: "
            f"order_id={fields.get('order_id')}, "
            f"trans_status={fields.get('trans_status')}, "
            f"amount={fields.get('amount')}"
        )

    except Exception as e:
        error = str(e)
        logger.error(f"Error processing PayZen IPN: {error}")
        return JSONResponse(
            status_code=400, content={"status": "error", "message": error}
        )

    # Process the payment
    try:
        # Find the payment by PayZen order ID
        payzen_order_id = fields.get("order_id")
        if not payzen_order_id:
            raise ValueError("Missing order_id in PayZen IPN")

        payment = await crud_payment.get_by_payzen_order_id(
            session, payzen_order_id=payzen_order_id
        )

        if not payment:
            # Try to find by UUID conversion
            try:
                payment_uuid = uuid.UUID(payzen_order_id)
                payment = await crud_payment.read(session, id=payment_uuid)
            except (ValueError, AttributeError):
                pass

        if not payment:
            logger.error(f"Payment not found for order_id: {payzen_order_id}")
            raise ValueError(f"Payment not found: {payzen_order_id}")

        # Update payment with PayZen data
        await crud_payment.update_payment_from_payzen(
            session, payment=payment, payzen_fields=fields, commit=True
        )

        logger.info(
            f"Payment updated successfully: payment_id={payment.id}, "
            f"status={fields.get('trans_status')}"
        )

    except Exception as e:
        logger.error(f"Error updating payment from IPN: {e}")
        await session.rollback()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Error processing payment"},
        )

    return JSONResponse(content={"status": "ok"})
