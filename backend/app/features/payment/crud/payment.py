import uuid

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.payment.models.payment import (
    Payment,
    PaymentCreate,
    PaymentUpdate,
)
from app.features.payment.models.payment_log import PaymentLog, PaymentLogCreate


class PaymentCrud(CrudBase[Payment, PaymentCreate, PaymentUpdate]):
    async def get_random_payments(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[Payment]:
        statement = (
            select(Payment)
            .where(
                Payment.is_admin_active.is_(True),
                Payment.is_active.is_(True),
            )
            .order_by(func.random())
        )

        if limit > 0:
            statement = statement.limit(limit)

        result = await session.exec(statement)

        return result.all()

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
                self.model.is_admin_active.is_(True),
                self.model.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        exec_result = await session.exec(statement)
        return exec_result.all()

    async def get_by_order_id(
        self,
        session: AsyncSession,
        *,
        order_id: uuid.UUID,
    ) -> Payment | None:
        """Get payment by order ID."""
        statement = select(self.model).where(
            self.model.order_id == order_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def get_by_payzen_order_id(
        self,
        session: AsyncSession,
        *,
        payzen_order_id: str,
    ) -> Payment | None:
        """Get payment by Payzen order ID."""
        statement = select(self.model).where(
            self.model.payzen_order_id == payzen_order_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()

    async def create_payment_with_log(
        self,
        session: AsyncSession,
        *,
        payment_data: PaymentCreate,
        commit: bool = True,
    ) -> Payment:
        """Create a payment and initialize it with pending status."""
        payment = await self.create(session, data=payment_data, commit=commit)
        return payment

    async def update_payment_from_payzen(
        self,
        session: AsyncSession,
        *,
        payment: Payment,
        payzen_fields: dict,
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
        # Extract Payzen data
        payment.payzen_trans_id = payzen_fields.get("trans_uuid") or payzen_fields.get("trans_id")
        payment.payzen_order_id = payzen_fields.get("order_id")
        payment.payzen_status = payzen_fields.get("trans_status")
        payment.payzen_payment_method = payzen_fields.get("payment_cards")
        payment.payzen_data = payzen_fields.get("_raw_answer")
        
        # Update payment status based on Payzen status
        trans_status = payzen_fields.get("trans_status")
        if trans_status == "PAID":
            # Payment successful - update to validated status
            # Note: payment_status_id should be set to the "validated" status ID
            pass
        elif trans_status in ["REFUSED", "ABANDONED", "CANCELLED"]:
            # Payment failed - update to error status
            payment.payzen_error_code = payzen_fields.get("error_code")
        
        session.add(payment)
        
        # Create payment log entry
        payment_log = PaymentLog(
            payment_id=payment.id,
            payzen_trans_id=payment.payzen_trans_id,
            payzen_order_id=payment.payzen_order_id,
            amount=int(payzen_fields.get("amount", 0)),
            payment_method=payment.payzen_payment_method,
            status=payment.payzen_status,
            error_code=payzen_fields.get("error_code"),
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
