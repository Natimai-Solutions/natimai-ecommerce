"""
CRUD pour la consolidation et regroupement d'expéditions.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import and_, select, or_
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.shipping.models.consolidation import (
    ShippingRouteConsolidation,
    ShippingRouteConsolidationCreate,
    ShippingRouteConsolidationUpdate,
    ShippingOrderConsolidation,
    ShippingOrderConsolidationCreate,
    ShippingOrderConsolidationUpdate,
    ShippingOrderStepConsolidation,
    ShippingOrderStepConsolidationCreate,
    ShippingOrderStepConsolidationUpdate,
)


class ShippingRouteConsolidationCrud(CrudBase[ShippingRouteConsolidation, ShippingRouteConsolidationCreate, ShippingRouteConsolidationUpdate]):
    
    async def get_by_code(
        self,
        session: AsyncSession,
        consolidation_code: str,
    ) -> ShippingRouteConsolidation | None:
        """Récupère une consolidation par son code"""
        statement = (
            select(ShippingRouteConsolidation)
            .where(
                ShippingRouteConsolidation.consolidation_code == consolidation_code,
                ShippingRouteConsolidation.is_active.is_(True),
            )
        )
        
        result = await session.exec(statement)
        return result.first()
    
    async def get_open_consolidations(
        self,
        session: AsyncSession,
        route_id: Optional[uuid.UUID] = None,
    ) -> list[ShippingRouteConsolidation]:
        """Récupère les consolidations ouvertes pour ajout de commandes"""
        
        conditions = [
            ShippingRouteConsolidation.status_code.in_(["open", "pending"]),
            ShippingRouteConsolidation.is_done.is_(False),
            ShippingRouteConsolidation.is_active.is_(True),
        ]
        
        # Vérifier que la date limite n'est pas dépassée
        conditions.append(
            or_(
                ShippingRouteConsolidation.cutoff_datetime.is_(None),
                ShippingRouteConsolidation.cutoff_datetime > datetime.utcnow(),
            )
        )
        
        if route_id:
            conditions.append(ShippingRouteConsolidation.route_id == route_id)
        
        statement = (
            select(ShippingRouteConsolidation)
            .where(and_(*conditions))
            .order_by(ShippingRouteConsolidation.departure_planned_at.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_consolidations_for_route(
        self,
        session: AsyncSession,
        route_id: uuid.UUID,
        status_filter: Optional[list[str]] = None,
    ) -> list[ShippingRouteConsolidation]:
        """Récupère les consolidations d'une route"""
        
        conditions = [
            ShippingRouteConsolidation.route_id == route_id,
            ShippingRouteConsolidation.is_active.is_(True),
        ]
        
        if status_filter:
            conditions.append(ShippingRouteConsolidation.status_code.in_(status_filter))
        
        statement = (
            select(ShippingRouteConsolidation)
            .where(and_(*conditions))
            .order_by(ShippingRouteConsolidation.departure_planned_at.desc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_active_shipments(
        self,
        session: AsyncSession,
    ) -> list[ShippingRouteConsolidation]:
        """Récupère les expéditions en cours"""
        
        active_statuses = ["shipped", "in_transit", "customs"]
        
        statement = (
            select(ShippingRouteConsolidation)
            .where(
                and_(
                    ShippingRouteConsolidation.status_code.in_(active_statuses),
                    ShippingRouteConsolidation.is_active.is_(True),
                )
            )
            .order_by(ShippingRouteConsolidation.departure_actual_at.desc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_consolidations_ready_to_ship(
        self,
        session: AsyncSession,
    ) -> list[ShippingRouteConsolidation]:
        """Récupère les consolidations prêtes à être expédiées"""
        
        statement = (
            select(ShippingRouteConsolidation)
            .where(
                and_(
                    ShippingRouteConsolidation.status_code == "confirmed",
                    ShippingRouteConsolidation.is_done.is_(False),
                    ShippingRouteConsolidation.is_active.is_(True),
                    or_(
                        ShippingRouteConsolidation.departure_planned_at.is_(None),
                        ShippingRouteConsolidation.departure_planned_at <= datetime.utcnow(),
                    )
                )
            )
            .order_by(ShippingRouteConsolidation.departure_planned_at.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def close_expired_consolidations(
        self,
        session: AsyncSession,
    ) -> int:
        """Ferme automatiquement les consolidations expirées"""
        
        expired_consolidations = await session.exec(
            select(ShippingRouteConsolidation)
            .where(
                and_(
                    ShippingRouteConsolidation.status_code == "open",
                    ShippingRouteConsolidation.cutoff_datetime.is_not(None),
                    ShippingRouteConsolidation.cutoff_datetime < datetime.utcnow(),
                    ShippingRouteConsolidation.is_active.is_(True),
                )
            )
        )
        
        count = 0
        for consolidation in expired_consolidations.all():
            await self.update(
                session,
                db_obj=consolidation,
                obj_in={"status_code": "confirmed"}
            )
            count += 1
        
        return count
    
    async def create_auto_consolidation(
        self,
        session: AsyncSession,
        route_id: uuid.UUID,
        departure_planned_at: Optional[datetime] = None,
        name: Optional[str] = None,
    ) -> ShippingRouteConsolidation:
        """Crée automatiquement une nouvelle consolidation"""
        
        # Générer un code unique
        today = datetime.now().strftime("%Y%m%d")
        consolidation_code = f"CONS-{today}-{uuid.uuid4().hex[:6].upper()}"
        
        # Date de départ par défaut (dans 3 jours)
        if not departure_planned_at:
            departure_planned_at = datetime.now() + timedelta(days=3)
        
        # Date limite (6 heures avant départ)
        cutoff_datetime = departure_planned_at - timedelta(hours=6)
        
        # Nom par défaut
        if not name:
            name = f"Consolidation {consolidation_code}"
        
        consolidation_data = ShippingRouteConsolidationCreate(
            route_id=route_id,
            consolidation_code=consolidation_code,
            name=name,
            departure_planned_at=departure_planned_at,
            cutoff_datetime=cutoff_datetime,
            status_code="open",
        )
        
        return await self.create(session, obj_in=consolidation_data)


class ShippingOrderConsolidationCrud(CrudBase[ShippingOrderConsolidation, ShippingOrderConsolidationCreate, ShippingOrderConsolidationUpdate]):
    
    async def get_by_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> list[ShippingOrderConsolidation]:
        """Récupère les liaisons consolidation d'une commande"""
        
        statement = (
            select(ShippingOrderConsolidation)
            .where(
                and_(
                    ShippingOrderConsolidation.order_id == order_id,
                    ShippingOrderConsolidation.is_active.is_(True),
                )
            )
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_by_consolidation(
        self,
        session: AsyncSession,
        consolidation_id: uuid.UUID,
    ) -> list[ShippingOrderConsolidation]:
        """Récupère toutes les commandes d'une consolidation"""
        
        statement = (
            select(ShippingOrderConsolidation)
            .where(
                and_(
                    ShippingOrderConsolidation.consolidation_id == consolidation_id,
                    ShippingOrderConsolidation.is_active.is_(True),
                )
            )
            .order_by(ShippingOrderConsolidation.created_at.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_by_idempotency_key(
        self,
        session: AsyncSession,
        idempotency_key: str,
    ) -> ShippingOrderConsolidation | None:
        """Récupère une liaison par clé d'idempotence"""
        
        statement = (
            select(ShippingOrderConsolidation)
            .where(
                and_(
                    ShippingOrderConsolidation.idempotency_key == idempotency_key,
                    ShippingOrderConsolidation.is_active.is_(True),
                )
            )
        )
        
        result = await session.exec(statement)
        return result.first()
    
    async def confirm_order_consolidation(
        self,
        session: AsyncSession,
        consolidation_link_id: uuid.UUID,
    ) -> ShippingOrderConsolidation | None:
        """Confirme une liaison commande-consolidation"""
        
        link = await self.read(session, id=consolidation_link_id)
        if not link:
            return None
        
        updated_link = await self.update(
            session,
            db_obj=link,
            obj_in={
                "status_code": "confirmed",
                "confirmed_at": datetime.utcnow()
            }
        )
        
        return updated_link


class ShippingOrderStepConsolidationCrud(CrudBase[ShippingOrderStepConsolidation, ShippingOrderStepConsolidationCreate, ShippingOrderStepConsolidationUpdate]):
    
    async def get_by_order_and_consolidation(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        consolidation_id: uuid.UUID,
    ) -> list[ShippingOrderStepConsolidation]:
        """Récupère le suivi d'une commande dans une consolidation"""
        
        statement = (
            select(ShippingOrderStepConsolidation)
            .where(
                and_(
                    ShippingOrderStepConsolidation.order_id == order_id,
                    ShippingOrderStepConsolidation.consolidation_id == consolidation_id,
                    ShippingOrderStepConsolidation.is_active.is_(True),
                )
            )
            .order_by(ShippingOrderStepConsolidation.occurred_at.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_by_order(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
    ) -> list[ShippingOrderStepConsolidation]:
        """Récupère tout le suivi d'une commande"""
        
        statement = (
            select(ShippingOrderStepConsolidation)
            .where(
                and_(
                    ShippingOrderStepConsolidation.order_id == order_id,
                    ShippingOrderStepConsolidation.is_active.is_(True),
                )
            )
            .order_by(ShippingOrderStepConsolidation.occurred_at.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_by_step(
        self,
        session: AsyncSession,
        route_step_id: uuid.UUID,
        consolidation_id: Optional[uuid.UUID] = None,
    ) -> list[ShippingOrderStepConsolidation]:
        """Récupère le suivi pour une étape donnée"""
        
        conditions = [
            ShippingOrderStepConsolidation.route_step_id == route_step_id,
            ShippingOrderStepConsolidation.is_active.is_(True),
        ]
        
        if consolidation_id:
            conditions.append(ShippingOrderStepConsolidation.consolidation_id == consolidation_id)
        
        statement = (
            select(ShippingOrderStepConsolidation)
            .where(and_(*conditions))
            .order_by(ShippingOrderStepConsolidation.occurred_at.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def get_pending_steps(
        self,
        session: AsyncSession,
        consolidation_id: Optional[uuid.UUID] = None,
    ) -> list[ShippingOrderStepConsolidation]:
        """Récupère les étapes en attente"""
        
        conditions = [
            ShippingOrderStepConsolidation.is_done.is_(False),
            ShippingOrderStepConsolidation.is_active.is_(True),
        ]
        
        if consolidation_id:
            conditions.append(ShippingOrderStepConsolidation.consolidation_id == consolidation_id)
        
        statement = (
            select(ShippingOrderStepConsolidation)
            .where(and_(*conditions))
            .order_by(ShippingOrderStepConsolidation.occurred_at.asc())
        )
        
        result = await session.exec(statement)
        return result.all()
    
    async def update_step_status(
        self,
        session: AsyncSession,
        step_consolidation_id: uuid.UUID,
        new_status: str,
        scan_ref: Optional[str] = None,
        actor: Optional[str] = None,
        evidence_url: Optional[str] = None,
    ) -> ShippingOrderStepConsolidation | None:
        """Met à jour le statut d'une étape"""
        
        step = await self.read(session, id=step_consolidation_id)
        if not step:
            return None
        
        update_data = {
            "status_code": new_status,
            "last_event_at": datetime.utcnow(),
        }
        
        if scan_ref:
            update_data["scan_ref"] = scan_ref
        
        if actor:
            update_data["actor"] = actor
        
        if evidence_url:
            update_data["evidence_url"] = evidence_url
        
        # Marquer comme terminé si c'est un statut terminal
        if new_status in ["delivered", "completed", "cancelled"]:
            update_data["is_done"] = True
        
        updated_step = await self.update(
            session,
            db_obj=step,
            obj_in=update_data
        )
        
        return updated_step



crud_shipping_route_consolidation = ShippingRouteConsolidationCrud(
    model=ShippingRouteConsolidation,
    schema_create=ShippingRouteConsolidationCreate,
    schema_update=ShippingRouteConsolidationUpdate,
    default_filter=and_(
        ShippingRouteConsolidation.is_active.is_(True),
    ),
    order_by=ShippingRouteConsolidation.departure_planned_at.desc(),
)

crud_shipping_order_consolidation = ShippingOrderConsolidationCrud(
    model=ShippingOrderConsolidation,
    schema_create=ShippingOrderConsolidationCreate,
    schema_update=ShippingOrderConsolidationUpdate,
    default_filter=and_(
        ShippingOrderConsolidation.is_active.is_(True),
    ),
    order_by=ShippingOrderConsolidation.created_at.desc(),
)


crud_shipping_order_step_consolidation = ShippingOrderStepConsolidationCrud(
    model=ShippingOrderStepConsolidation,
    schema_create=ShippingOrderStepConsolidationCreate,
    schema_update=ShippingOrderStepConsolidationUpdate,
    default_filter=and_(
        ShippingOrderStepConsolidation.is_active.is_(True),
    ),
    order_by=ShippingOrderStepConsolidation.occurred_at.asc(),
)