import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.payment.models.payment_attachment import (
    PaymentAttachment,
    PaymentAttachmentCreate,
    PaymentAttachmentUpdate,
)


class PaymentAttachmentCrud(
    CrudBase[PaymentAttachment, PaymentAttachmentCreate, PaymentAttachmentUpdate]
):
    """Represents payment attachment crud."""

    async def list_for_payment(
        self,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
    ) -> list[PaymentAttachment]:
        """List for payment."""
        statement = (
            select(self.model)
            .where(self.model.payment_id == payment_id)
            .order_by(col(self.model.created_at).asc())
        )
        result = await session.exec(statement)
        return list(result.all())

    async def get_by_file_key(
        self,
        session: AsyncSession,
        *,
        file_key: str,
    ) -> PaymentAttachment | None:
        """Get by file key."""
        statement = select(self.model).where(self.model.file_key == file_key)
        result = await session.exec(statement)
        return result.first()


crud_payment_attachment = PaymentAttachmentCrud(
    model=PaymentAttachment,
    schema_create=PaymentAttachmentCreate,
    schema_update=PaymentAttachmentUpdate,
    order_by=PaymentAttachment.created_at,
)
