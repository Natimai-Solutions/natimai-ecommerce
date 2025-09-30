"""
CRUD pour les tâches de livraison et les colis.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import and_, select, or_
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.shipping.models.delivery_task import (
    DeliveryTask,
    DeliveryTaskCreate,
    DeliveryTaskUpdate,
    Package,
    PackageCreate,
    PackageUpdate,
)


class DeliveryTaskCrud(CrudBase[DeliveryTask, DeliveryTaskCreate, DeliveryTaskUpdate]):
    
    async def get_tasks_for_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> list[DeliveryTask]:
        """Récupère les tâches de livraison d'une commande"""
        
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
        assignee: Optional[str] = None,
    ) -> list[DeliveryTask]:
        """Récupère les tâches par statut"""
        
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
        status_code: Optional[str] = None,
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
        status_code: Optional[str] = None,
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
        assignee: Optional[str] = None,
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
        assignee: Optional[str] = None,
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
        delivery_service: Optional[str] = None,
    ) -> DeliveryTask | None:
        """Assigne une tâche à un livreur"""
        
        task = await self.read(session, id=task_id)
        if not task:
            return None
        
        update_data = {
            "assignee": assignee,
            "status_code": "assigned",
        }
        
        if delivery_service:
            update_data["delivery_service"] = delivery_service
        
        updated_task = await self.update(
            session,
            db_obj=task,
            obj_in=update_data
        )
        
        return updated_task
    
    async def complete_delivery(
        self,
        session: AsyncSession,
        task_id: uuid.UUID,
        proof_url: Optional[str] = None,
        signature_name: Optional[str] = None,
        photo_url: Optional[str] = None,
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
        
        updated_task = await self.update(
            session,
            db_obj=task,
            obj_in=update_data
        )
        
        return updated_task


class PackageCrud(CrudBase[Package, PackageCreate, PackageUpdate]):
    
    async def get_packages_for_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> list[Package]:
        """Récupère tous les colis d'une commande"""
        
        statement = (
            select(Package)
            .where(
                and_(
                    Package.order_id == order_id,
                    Package.is_active.is_(True),
                )
            )
            .order_by(Package.created_at.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_by_tracking_number(
        self,
        session: AsyncSession,
        tracking_number: str,
    ) -> Package | None:
        """Récupère un colis par son numéro de suivi"""
        
        statement = (
            select(Package)
            .where(
                and_(
                    Package.tracking_number == tracking_number,
                    Package.is_active.is_(True),
                )
            )
        )
        
        result = await session.exec(statement)
        return result.first()
    
    async def get_by_package_code(
        self,
        session: AsyncSession,
        package_code: str,
    ) -> Package | None:
        """Récupère un colis par son code"""
        
        statement = (
            select(Package)
            .where(
                and_(
                    Package.package_code == package_code,
                    Package.is_active.is_(True),
                )
            )
        )
        
        result = await session.exec(statement)
        return result.first()
    
    async def get_hazmat_packages(
        self,
        session: AsyncSession,
        order_id: Optional[uuid.UUID] = None,
    ) -> list[Package]:
        """Récupère les colis avec matières dangereuses"""
        
        conditions = [
            Package.is_hazmat.is_(True),
            Package.is_active.is_(True),
        ]
        
        if order_id:
            conditions.append(Package.order_id == order_id)
        
        statement = (
            select(Package)
            .where(and_(*conditions))
            .order_by(Package.created_at.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_temperature_controlled_packages(
        self,
        session: AsyncSession,
        order_id: Optional[uuid.UUID] = None,
    ) -> list[Package]:
        """Récupère les colis nécessitant un contrôle de température"""
        
        conditions = [
            Package.requires_temperature_control.is_(True),
            Package.is_active.is_(True),
        ]
        
        if order_id:
            conditions.append(Package.order_id == order_id)
        
        statement = (
            select(Package)
            .where(and_(*conditions))
            .order_by(Package.created_at.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def calculate_order_metrics(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> dict:
        """Calcule les métriques totales d'une commande"""
        
        packages = await self.get_packages_for_order(session, order_id)
        
        total_weight = sum(p.weight_kg or 0 for p in packages)
        total_volume = sum(p.volume_m3 or 0 for p in packages)
        total_value = sum(p.declared_value or 0 for p in packages)
        
        has_hazmat = any(p.is_hazmat for p in packages)
        has_fragile = any(p.is_fragile for p in packages)
        requires_temp_control = any(p.requires_temperature_control for p in packages)
        
        return {
            "order_id": order_id,
            "package_count": len(packages),
            "total_weight_kg": total_weight,
            "total_volume_m3": total_volume,
            "total_declared_value": total_value,
            "has_hazmat": has_hazmat,
            "has_fragile": has_fragile,
            "requires_temperature_control": requires_temp_control,
        }


crud_delivery_task = DeliveryTaskCrud(
    model=DeliveryTask,
    schema_create=DeliveryTaskCreate,
    schema_update=DeliveryTaskUpdate,
    default_filter=and_(
        DeliveryTask.is_active.is_(True),
    ),
    order_by=DeliveryTask.scheduled_at.asc(),
)

crud_package = PackageCrud(
    model=Package,
    schema_create=PackageCreate,
    schema_update=PackageUpdate,
    default_filter=and_(
        Package.is_active.is_(True),
    ),
    order_by=Package.created_at.asc(),
)