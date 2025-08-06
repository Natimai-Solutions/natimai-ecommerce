from sqlmodel import and_, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
import uuid

from app.api.base.crud import CrudBase
from app.api.base.models import User
from app.api.payment.model.payment import (
    Payment,
    PaymentCreate,
    PaymentUpdate,
)


class PaymentCrud(CrudBase[Payment, PaymentCreate, PaymentUpdate]):
    
    async def get_random_payments(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[Payment]:
        """Récupérer des paiements aléatoires (pour démonstration)"""
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
    
    async def get_payments_by_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> list[Payment]:
        """Récupérer tous les paiements d'une commande"""
        statement = (
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.created_at.desc())
        )
        result = await session.exec(statement)
        return result.all()
    
    async def get_payments_by_user(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 100,
    ) -> list[Payment]:
        """Récupérer les paiements d'un utilisateur"""
        statement = (
            select(Payment)
            .where(Payment.created_by == user_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        result = await session.exec(statement)
        return result.all()
    
    async def get_payments_by_status(
        self,
        session: AsyncSession,
        status_id: uuid.UUID,
        limit: int = 100,
    ) -> list[Payment]:
        """Récupérer les paiements par statut"""
        statement = (
            select(Payment)
            .where(Payment.status_id == status_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
        result = await session.exec(statement)
        return result.all()
    
    async def get_total_amount_by_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> float:
        """Calculer le montant total des paiements pour une commande"""
        statement = (
            select(func.sum(Payment.amount))
            .where(
                Payment.order_id == order_id,
                Payment.is_active.is_(True),
            )
        )
        result = await session.exec(statement)
        return result.first() or 0.0


crud_payment = PaymentCrud(
    model=Payment,
    schema_create=PaymentCreate,
    schema_update=PaymentUpdate,
    default_filter=and_(
        Payment.is_admin_active.is_(True),
    ),
    order_by=Payment.created_at.desc(),
)
