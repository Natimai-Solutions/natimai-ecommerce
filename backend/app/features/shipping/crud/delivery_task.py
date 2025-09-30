"""
CRUD for delivery tasks and packages.
"""

import uuid
from datetime import datetime

from sqlmodel import and_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.shipping.models.delivery_task import (
    DeliveryTask,
    DeliveryTaskCreate,
    DeliveryTaskUpdate,
)


class DeliveryTaskCrud(CrudBase[DeliveryTask, DeliveryTaskCreate, DeliveryTaskUpdate]):
    async def get_tasks_for_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> list[DeliveryTask]:
        """Retrieve delivery tasks for an order"""

        statement = (
            select(DeliveryTask)
            .where(
                and_(
                    DeliveryTask.order_id == order_id,
                    DeliveryTask.is_active.is_(True),
                )
            )
            .order_by(DeliveryTask.created_at.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_tasks_by_status(
        self,
        session: AsyncSession,
        status_code: str,
        assignee: str | None = None,
    ) -> list[DeliveryTask]:
        """Retrieve tasks by status"""

        conditions = [
            DeliveryTask.status_code == status_code,
            DeliveryTask.is_active.is_(True),
        ]

        if assignee:
            conditions.append(DeliveryTask.assignee == assignee)

        statement = (
            select(DeliveryTask)
            .where(and_(*conditions))
            .order_by(DeliveryTask.scheduled_at.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_tasks_by_delivery_type(
        self,
        session: AsyncSession,
        delivery_type: str,
        status_code: str | None = None,
    ) -> list[DeliveryTask]:
        """Récupère les tâches par type de livraison"""

        conditions = [
            DeliveryTask.delivery_type == delivery_type,
            DeliveryTask.is_active.is_(True),
        ]

        if status_code:
            conditions.append(DeliveryTask.status_code == status_code)

        statement = (
            select(DeliveryTask)
            .where(and_(*conditions))
            .order_by(DeliveryTask.scheduled_at.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_tasks_by_place(
        self,
        session: AsyncSession,
        address_place_id: uuid.UUID,
        status_code: str | None = None,
    ) -> list[DeliveryTask]:
        """Récupère les tâches pour un lieu donné"""

        conditions = [
            DeliveryTask.address_place_id == address_place_id,
            DeliveryTask.is_active.is_(True),
        ]

        if status_code:
            conditions.append(DeliveryTask.status_code == status_code)

        statement = (
            select(DeliveryTask)
            .where(and_(*conditions))
            .order_by(DeliveryTask.scheduled_at.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_tasks_by_window(
        self,
        session: AsyncSession,
        start_datetime: datetime,
        end_datetime: datetime,
        assignee: str | None = None,
    ) -> list[DeliveryTask]:
        """Récupère les tâches dans une fenêtre temporelle"""

        conditions = [
            DeliveryTask.window_start >= start_datetime,
            DeliveryTask.window_end <= end_datetime,
            DeliveryTask.is_active.is_(True),
        ]

        if assignee:
            conditions.append(DeliveryTask.assignee == assignee)

        statement = (
            select(DeliveryTask)
            .where(and_(*conditions))
            .order_by(DeliveryTask.window_start.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def get_pending_tasks(
        self,
        session: AsyncSession,
        assignee: str | None = None,
    ) -> list[DeliveryTask]:
        """Récupère les tâches en attente"""

        conditions = [
            DeliveryTask.status_code.in_(["pending", "assigned", "out_for_delivery"]),
            DeliveryTask.is_active.is_(True),
        ]

        if assignee:
            conditions.append(DeliveryTask.assignee == assignee)

        statement = (
            select(DeliveryTask)
            .where(and_(*conditions))
            .order_by(DeliveryTask.scheduled_at.asc())
        )

        result = await session.exec(statement)
        return result.all()

    async def assign_task(
        self,
        session: AsyncSession,
        task_id: uuid.UUID,
        assignee: str,
        delivery_service: str | None = None,
    ) -> DeliveryTask | None:
        """Assign a task to a delivery person"""

        task = await self.read(session, id=task_id)
        if not task:
            return None

        update_data = {
            "assignee": assignee,
            "status_code": "assigned",
        }

        if delivery_service:
            update_data["delivery_service"] = delivery_service

        updated_task = await self.update(session, db_obj=task, obj_in=update_data)

        return updated_task

    async def complete_delivery(
        self,
        session: AsyncSession,
        task_id: uuid.UUID,
        proof_url: str | None = None,
        signature_name: str | None = None,
        photo_url: str | None = None,
    ) -> DeliveryTask | None:
        """Marque une livraison comme terminée"""

        task = await self.read(session, id=task_id)
        if not task:
            return None

        update_data = {
            "status_code": "delivered",
            "delivered_at": datetime.utcnow(),
        }

        if proof_url:
            update_data["proof_url"] = proof_url

        if signature_name:
            update_data["signature_name"] = signature_name

        if photo_url:
            update_data["photo_url"] = photo_url

        updated_task = await self.update(session, db_obj=task, obj_in=update_data)

        return updated_task

crud_delivery_task = DeliveryTaskCrud(
    model=DeliveryTask,
    schema_create=DeliveryTaskCreate,
    schema_update=DeliveryTaskUpdate,
    default_filter=and_(
        DeliveryTask.is_active.is_(True),
    ),
    order_by=DeliveryTask.scheduled_at.asc(),
)
