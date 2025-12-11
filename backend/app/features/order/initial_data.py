"""Données initiales pour les statuts de commande."""

import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.order.constants import OrderStatusCode
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.order.models.order_status import OrderStatusCreate

logger = logging.getLogger(__name__)


async def init_order_statuses(session: AsyncSession) -> None:
    """Initialise les statuts de commande par défaut."""
    statuses = [
        OrderStatusCreate(
            name="En attente",
            code=OrderStatusCode.PENDING,
            sequence=0,
            is_final=False,
            is_error=False,
            is_cancellation=False,
            color="#FCD34D",
            description="La commande a été créée et est en attente de paiement",
        ),
        OrderStatusCreate(
            name="Paiement confirmé",
            code=OrderStatusCode.PAYMENT_CONFIRMED,
            sequence=10,
            is_final=False,
            is_error=False,
            is_cancellation=False,
            color="#34D399",
            description="Le paiement a été validé avec succès",
        ),
        OrderStatusCreate(
            name="En préparation",
            code=OrderStatusCode.PROCESSING,
            sequence=20,
            is_final=False,
            is_error=False,
            is_cancellation=False,
            color="#60A5FA",
            description="La commande est en cours de préparation",
        ),
        OrderStatusCreate(
            name="Expédiée",
            code=OrderStatusCode.SHIPPED,
            sequence=30,
            is_final=False,
            is_error=False,
            is_cancellation=False,
            color="#8B5CF6",
            description="La commande a été expédiée",
        ),
        OrderStatusCreate(
            name="Livrée",
            code=OrderStatusCode.DELIVERED,
            sequence=40,
            is_final=True,
            is_error=False,
            is_cancellation=False,
            color="#10B981",
            description="La commande a été livrée avec succès",
        ),
        OrderStatusCreate(
            name="Annulée",
            code=OrderStatusCode.CANCELLED,
            sequence=50,
            is_final=True,
            is_error=False,
            is_cancellation=True,
            color="#EF4444",
            description="La commande a été annulée",
        ),
        OrderStatusCreate(
            name="Paiement échoué",
            code=OrderStatusCode.PAYMENT_FAILED,
            sequence=60,
            is_final=True,
            is_error=True,
            is_cancellation=False,
            color="#DC2626",
            description="Le paiement a échoué",
        ),
    ]

    for status_data in statuses:
        existing = await crud_order_status.get_by_code(session, code=status_data.code)
        if not existing:
            await crud_order_status.create(session, data=status_data, user=None)
            logger.info(f"Created order status: {status_data.name} ({status_data.code})")
