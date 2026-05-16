from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.payment.models.payment_method import (
    PaymentMethod,
    PaymentMethodCreate,
    PaymentMethodUpdate,
)


class PaymentMethodCrud(
    CrudBase[PaymentMethod, PaymentMethodCreate, PaymentMethodUpdate]
):
    """Represents payment method crud."""

    async def get_random_payment_methods(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[PaymentMethod]:
        """Get random payment methods."""
        statement = (
            select(PaymentMethod)
            .where(
                col(PaymentMethod.is_admin_active).is_(True),
                col(PaymentMethod.is_active).is_(True),
            )
            .order_by(func.random())
        )

        if limit > 0:
            statement = statement.limit(limit)

        result = await session.exec(statement)

        return list(result.all())


crud_payment_method = PaymentMethodCrud(
    model=PaymentMethod,
    schema_create=PaymentMethodCreate,
    schema_update=PaymentMethodUpdate,
    order_by=col(PaymentMethod.name),
)
