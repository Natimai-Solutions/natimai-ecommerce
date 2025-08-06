from sqlmodel import and_, func, select
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
        """Récupérer des méthodes de paiement aléatoires (pour démonstration)"""
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
    
    async def get_by_name(
        self, 
        session: AsyncSession, 
        name: str
    ) -> PaymentMethod | None:
        """Récupérer une méthode de paiement par son nom"""
        statement = select(PaymentMethod).where(PaymentMethod.name == name)
        result = await session.exec(statement)
        return result.first()
    
    async def get_active_methods(
        self, 
        session: AsyncSession
    ) -> list[PaymentMethod]:
        """Récupérer toutes les méthodes de paiement actives"""
        statement = (
            select(PaymentMethod)
            .where(
                PaymentMethod.is_active.is_(True),
                PaymentMethod.is_admin_active.is_(True),
            )
            .order_by(PaymentMethod.name)
        )
        result = await session.exec(statement)
        return result.all()
    
    async def get_enabled_for_checkout(
        self, 
        session: AsyncSession
    ) -> list[PaymentMethod]:
        """Récupérer les méthodes disponibles pour le checkout"""
        statement = (
            select(PaymentMethod)
            .where(
                PaymentMethod.is_active.is_(True),
                PaymentMethod.is_admin_active.is_(True),
                PaymentMethod.enabled_for_checkout.is_(True),  # Si ce champ existe
            )
            .order_by(PaymentMethod.name)
        )
        result = await session.exec(statement)
        return result.all()


crud_payment_method = PaymentMethodCrud(
    model=PaymentMethod,
    schema_create=PaymentMethodCreate,
    schema_update=PaymentMethodUpdate,
    default_filter=and_(
        PaymentMethod.is_admin_active.is_(True),
    ),
    order_by=PaymentMethod.name,
)
