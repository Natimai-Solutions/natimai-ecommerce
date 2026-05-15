# mypy: disable-error-code="arg-type,assignment,call-overload"

import uuid

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.payment.models.payment import (
    Payment,
    PaymentCreate,
    PaymentUpdate,
)
from app.features.payment.models.payment_log import PaymentLog
from app.utils.money import minor_units_to_decimal, parse_minor_units


class PaymentCrud(CrudBase[Payment, PaymentCreate, PaymentUpdate]):
    async def get_random_payments(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[Payment]:
        statement = (
            select(Payment)
            .where(
                col(Payment.is_admin_active).is_(True),
                col(Payment.is_active).is_(True),
            )
            .order_by(func.random())
        )

        if limit > 0:
            statement = statement.limit(limit)

        result = await session.exec(statement)

        return list(result.all())

    async def get_by_user_id(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Payment]:
        """Get all payments for a specific user."""
        statement = (
            select(self.model)
            .where(
                self.model.user_id == user_id,
                col(self.model.is_admin_active).is_(True),
                col(self.model.is_active).is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(col(self.model.created_at).desc())
        )
        exec_result = await session.exec(statement)
        return list(exec_result.all())

    async def get_by_order_id(
        self,
        session: AsyncSession,
        *,
        order_id: uuid.UUID,
    ) -> Payment | None:
        """Get payment by order ID."""
        statement = select(self.model).where(
            self.model.order_id == order_id,
            col(self.model.is_admin_active).is_(True),
            col(self.model.is_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def get_by_provider_reference(
        self,
        session: AsyncSession,
        *,
        provider_code: str,
        provider_reference: str,
    ) -> Payment | None:
        """Get payment by provider code and provider-side reference."""
        statement = select(self.model).where(
            self.model.provider_code == provider_code,
            self.model.provider_reference == provider_reference,
            col(self.model.is_admin_active).is_(True),
            col(self.model.is_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def create_payment_with_log(
        self,
        session: AsyncSession,
        *,
        payment_data: PaymentCreate,
        user: object | None = None,
        commit: bool = True,
    ) -> Payment:
        """Create a payment and initialize it with pending status."""
        from app.features.payment.crud.payment_status import crud_payment_status

        # Get pending status
        pending_status = await crud_payment_status.get_by_name(session, name="Pending")

        payment = await self.create_draft(
            session=session,
            data=payment_data,
            user=user,
        )

        # Set pending status if found
        if pending_status:
            payment.payment_status_id = pending_status.id

        if commit:
            await self._safe_commit_and_refresh(
                session,
                record=payment,
                operation="create_payment_with_log",
            )
            await self.after_create_commit(
                session,
                record=payment,
                data=payment_data,
                user=user,
            )

        return payment

    async def update_payment_from_payzen(
        self,
        session: AsyncSession,
        *,
        payment: Payment,
        payzen_fields: dict[str, object],
        commit: bool = True,
    ) -> Payment:
        """
        Update payment with Payzen transaction data.

        Args:
            session: Database session
            payment: Payment to update
            payzen_fields: Payzen IPN fields
            commit: Whether to commit the transaction

        Returns:
            Updated payment
        """
        from app.features.payment.crud.payment_status import crud_payment_status

        # PayZen IPN reports amount in the smallest currency unit (e.g. cents for EUR).
        # Convert it back to a currency-aware Decimal so that the persisted amount
        # stays consistent with order/product totals.
        raw_amount = payzen_fields.get("amount")
        if raw_amount is not None:
            amount_minor = parse_minor_units(raw_amount)
            amount_decimal = minor_units_to_decimal(amount_minor, payment.currency)
        else:
            amount_decimal = payment.amount

        trans_id_raw = payzen_fields.get("trans_uuid") or payzen_fields.get("trans_id")
        trans_id = str(trans_id_raw).strip() if trans_id_raw is not None else None
        if trans_id == "":
            trans_id = None

        order_id_raw = payzen_fields.get("order_id")
        order_id = str(order_id_raw).strip() if order_id_raw is not None else None
        if order_id == "":
            order_id = None

        trans_status = payzen_fields.get("trans_status")
        payment_method = payzen_fields.get("payment_cards")
        error_code = payzen_fields.get("error_code")

        provider_data: dict[str, object] = {}
        if isinstance(payment.provider_data, dict):
            provider_data.update(payment.provider_data)
        provider_data.update(payzen_fields)
        if trans_id is not None:
            provider_data["trans_id"] = trans_id
            provider_data["trans_uuid"] = trans_id
        if order_id is not None:
            provider_data["order_id"] = order_id
        if payment_method is not None:
            provider_data["payment_cards"] = payment_method
        if error_code is not None:
            provider_data["error_code"] = error_code

        payment.provider_code = payment.provider_code or "payzen"
        if not payment.provider_reference:
            payment.provider_reference = order_id or trans_id
        payment.provider_data = provider_data or None
        payment.amount = amount_decimal

        # Update payment status based on Payzen status
        if trans_status == "PAID":
            # Payment successful - update to validated status
            validated_status = await crud_payment_status.get_by_name(
                session, name="Completed"
            )
            if validated_status:
                payment.payment_status_id = validated_status.id
        elif trans_status in ["REFUSED", "ABANDONED", "CANCELLED"]:
            # Payment failed - update to error status
            failed_status = await crud_payment_status.get_by_name(
                session, name="Failed"
            )
            if failed_status:
                payment.payment_status_id = failed_status.id

        session.add(payment)

        # Create payment log entry
        payment_log = PaymentLog(
            payment_id=payment.id,
            provider_reference=trans_id,
            provider_order_reference=order_id,
            amount=amount_decimal,
            payment_method=str(payment_method) if payment_method is not None else None,
            status=str(trans_status) if trans_status is not None else None,
            error_code=str(error_code) if error_code is not None else None,
            raw_data=payzen_fields,
        )
        session.add(payment_log)

        if commit:
            await session.commit()
            await session.refresh(payment)

        return payment


crud_payment = PaymentCrud(
    model=Payment,
    schema_create=PaymentCreate,
    schema_update=PaymentUpdate,
    order_by=Payment.created_at,
)
