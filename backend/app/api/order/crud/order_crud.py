import uuid
from sqlmodel import and_, select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.base.crud import CrudBase
from app.api.base.models import User
from app.api.order.model.order import (
    Order,
    OrderCreate,
    OrderUpdate,
)
from app.api.order.model.order_line import (
    OrderLine,
    OrderLineCreate,
    OrderLineUpdate,
)
from app.api.order.model.order_status import (
    OrderStatus,
    OrderStatusCreate,
    OrderStatusUpdate,
)


# ========== OrderStatus CRUD (Données de référence) ==========

class OrderStatusCrud(CrudBase[OrderStatus, OrderStatusCreate, OrderStatusUpdate]):
    async def get_by_name(self, session: AsyncSession, name: str) -> OrderStatus | None:
        """Récupérer un statut par son nom"""
        statement = select(OrderStatus).where(OrderStatus.name == name)
        result = await session.exec(statement)
        return result.first()

    async def get_active_statuses(self, session: AsyncSession) -> list[OrderStatus]:
        """Récupérer tous les statuts actifs"""
        statement = (
            select(OrderStatus)
            .where(
                OrderStatus.is_active.is_(True),
                OrderStatus.is_admin_active.is_(True),
            )
            .order_by(OrderStatus.name)
        )
        result = await session.exec(statement)
        return result.all()


# ========== Order CRUD Principal ==========

class OrderCrud(CrudBase[Order, OrderCreate, OrderUpdate]):
    
    # === Gestion des OrderLines (pas de CRUD séparé) ===
    
    async def add_order_line(
        self, 
        session: AsyncSession, 
        order_id: uuid.UUID,
        line_data: OrderLineCreate,
        user: User
    ) -> OrderLine:
        """Ajouter une ligne à une commande"""
        order_line = OrderLine(
            order_id=order_id,
            product_id=line_data.product_id,
            quantity=line_data.quantity,
            description=line_data.description,
            created_by=user.id,
            modified_by=user.id,
        )
        session.add(order_line)
        await session.commit()
        await session.refresh(order_line)
        return order_line
    
    async def update_order_line(
        self,
        session: AsyncSession,
        line_id: uuid.UUID,
        line_data: OrderLineUpdate,
        user: User
    ) -> OrderLine | None:
        """Modifier une ligne de commande"""
        statement = select(OrderLine).where(OrderLine.id == line_id)
        result = await session.exec(statement)
        order_line = result.first()
        
        if not order_line:
            return None
            
        for field, value in line_data.dict(exclude_unset=True).items():
            setattr(order_line, field, value)
        
        order_line.modified_by = user.id
        session.add(order_line)
        await session.commit()
        await session.refresh(order_line)
        return order_line
    
    async def remove_order_line(
        self, 
        session: AsyncSession, 
        line_id: uuid.UUID,
        user: User
    ) -> bool:
        """Supprimer une ligne de commande"""
        statement = select(OrderLine).where(OrderLine.id == line_id)
        result = await session.exec(statement)
        order_line = result.first()
        
        if order_line:
            await session.delete(order_line)
            await session.commit()
            return True
        return False
    
    async def get_order_lines(
        self, 
        session: AsyncSession, 
        order_id: uuid.UUID
    ) -> list[OrderLine]:
        """Récupérer toutes les lignes d'une commande"""
        statement = (
            select(OrderLine)
            .where(OrderLine.order_id == order_id)
            .order_by(OrderLine.created_at)
        )
        result = await session.exec(statement)
        return result.all()
    
    # === Méthodes business spécifiques aux Orders ===
    
    async def get_orders_by_status(
        self, 
        session: AsyncSession, 
        status_name: str,
        limit: int = 100
    ) -> list[Order]:
        """Récupérer les commandes par statut"""
        statement = (
            select(Order)
            .join(OrderStatus)
            .where(OrderStatus.name == status_name)
            .limit(limit)
            .order_by(Order.created_at.desc())
        )
        result = await session.exec(statement)
        return result.all()
    
    async def get_orders_by_user(
        self, 
        session: AsyncSession, 
        user_id: uuid.UUID,
        limit: int = 100
    ) -> list[Order]:
        """Récupérer les commandes d'un utilisateur"""
        statement = (
            select(Order)
            .where(Order.created_by == user_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        result = await session.exec(statement)
        return result.all()
    
    async def change_order_status(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        status_id: uuid.UUID,
        user: User
    ) -> Order | None:
        """Changer le statut d'une commande"""
        order = await self.get(session, order_id)
        if not order:
            return None
            
        order.status_id = status_id
        order.modified_by = user.id
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order
    
    async def change_order_status_by_name(
        self,
        session: AsyncSession,
        order_id: uuid.UUID,
        status_name: str,
        user: User
    ) -> Order | None:
        """Changer le statut d'une commande par nom de statut"""
        # Récupérer le statut par nom
        status = await crud_order_status.get_by_name(session, status_name)
        if not status:
            raise ValueError(f"Status '{status_name}' does not exist")
        
        return await self.change_order_status(session, order_id, status.id, user)
    
    async def get_order_total_quantity(
        self, 
        session: AsyncSession, 
        order_id: uuid.UUID
    ) -> int:
        """Calculer la quantité totale d'une commande"""
        statement = (
            select(func.sum(OrderLine.quantity))
            .where(OrderLine.order_id == order_id)
        )
        result = await session.exec(statement)
        return result.first() or 0
    
    async def get_order_line_count(
        self, 
        session: AsyncSession, 
        order_id: uuid.UUID
    ) -> int:
        """Compter le nombre de lignes dans une commande"""
        statement = (
            select(func.count(OrderLine.id))
            .where(OrderLine.order_id == order_id)
        )
        result = await session.exec(statement)
        return result.first() or 0
    
    async def get_orders_with_details(
        self,
        session: AsyncSession,
        skip: int = 0,
        limit: int = 100
    ) -> list[Order]:
        """Récupérer les commandes avec leurs relations (status, lignes)"""
        statement = (
            select(Order)
            .join(OrderStatus)
            .where(
                Order.is_admin_active.is_(True),
                Order.is_active.is_(True),
            )
            .order_by(Order.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.exec(statement)
        return result.all()


# ========== Instances des CRUDs ==========

# CRUD pour OrderStatus (données de référence)
crud_order_status = OrderStatusCrud(
    model=OrderStatus,
    schema_create=OrderStatusCreate,
    schema_update=OrderStatusUpdate,
    order_by=OrderStatus.name,
)

# CRUD principal pour Order
crud_order = OrderCrud(
    model=Order,
    schema_create=OrderCreate,
    schema_update=OrderUpdate,
    default_filter=and_(
        Order.is_admin_active.is_(True),
    ),
    order_by=Order.created_at.desc(),
)