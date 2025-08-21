from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.base.crud import CrudBase
from app.api.payment.model.payment_method import (
    PaymentMethod,
    PaymentMethodCreate,
    PaymentMethodUpdate,
)


class PaymentMethodCrud(
    CrudBase[PaymentMethod, PaymentMethodCreate, PaymentMethodUpdate]
):
    async def get_random_payment_methods(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[PaymentMethod]:
        statement = (
            select(PaymentMethod)
            .where(
                PaymentMethod.is_admin_active.is_(True),
                PaymentMethod.is_active.is_(True),
            )
            .order_by(func.random())
        )

        if limit > 0:
            statement = statement.limit(limit)

        result = await session.exec(statement)

        return result.all()


crud_payment_method = PaymentMethodCrud(
    model=PaymentMethod,
    create_model=PaymentMethodCreate,
    update_model=PaymentMethodUpdate,
    order_by=PaymentMethod.name,
)
