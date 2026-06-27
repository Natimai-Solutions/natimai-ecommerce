import uuid
from decimal import Decimal

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.payment.models.refund import Refund, RefundCreate, RefundUpdate


class RefundCrud(CrudBase[Refund, RefundCreate, RefundUpdate]):
    """Represents refund crud."""

    async def list_for_payment(
        self, session: AsyncSession, *, payment_id: uuid.UUID
    ) -> list[Refund]:
        """All refunds recorded against a payment, oldest first."""
        statement = (
            select(Refund)
            .where(
                Refund.payment_id == payment_id,
                col(Refund.is_active).is_(True),
            )
            .order_by(col(Refund.created_at).asc())
        )
        result = await session.exec(statement)
        return list(result.all())

    async def get_total_refunded(
        self, session: AsyncSession, *, payment_id: uuid.UUID
    ) -> Decimal:
        """Sum of non-failed refunds for a payment.

        Pending refunds are counted so the reserved amount can never exceed the
        payment (no double-refund window).
        """
        refunds = await self.list_for_payment(session, payment_id=payment_id)
        return sum((r.amount for r in refunds if r.status != "failed"), Decimal("0"))


crud_refund = RefundCrud(
    model=Refund,
    schema_create=RefundCreate,
    schema_update=RefundUpdate,
    order_by=col(Refund.created_at),
)
