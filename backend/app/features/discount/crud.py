import datetime
import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.discount.models import (
    Discount,
    DiscountCreate,
    DiscountType,
    DiscountUpdate,
)


class DiscountCrud(CrudBase[Discount, DiscountCreate, DiscountUpdate]):
    async def get_by_code(
        self, session: AsyncSession, code: str
    ) -> Discount | None:
        """Récupère un coupon par son code"""
        statement = select(Discount).where(
            Discount.code == code,
            Discount.discount_type == DiscountType.COUPON,
            Discount.is_active.is_(True),
        )
        result = await session.exec(statement)
        return result.first()

    async def get_active_promotions(
        self,
        session: AsyncSession,
        product_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
    ) -> list[Discount]:
        """Récupère les promotions actives pour un produit ou une catégorie"""
        now = datetime.datetime.now()
        conditions = [
            Discount.discount_type == DiscountType.PROMOTION,
            Discount.is_active.is_(True),
        ]

        # Vérifier les dates de validité
        conditions.append(
            (Discount.start_date.is_(None)) | (Discount.start_date <= now)
        )
        conditions.append((Discount.end_date.is_(None)) | (Discount.end_date >= now))

        # Vérifier le nombre d'utilisations
        conditions.append(
            (Discount.max_uses.is_(None)) | (Discount.current_uses < Discount.max_uses)
        )

        # Filtrer par produit ou catégorie
        if product_id:
            conditions.append(Discount.product_id == product_id)
        if category_id:
            conditions.append(Discount.category_id == category_id)

        statement = select(Discount).where(*conditions)
        result = await session.exec(statement)
        return list(result.all())

    async def validate_coupon(
        self, session: AsyncSession, code: str
    ) -> tuple[bool, str, Discount | None]:
        """
        Valide un code coupon.
        Retourne (is_valid, message, discount)
        """
        discount = await self.get_by_code(session, code)

        if not discount:
            return False, "Code coupon invalide", None

        if not discount.is_active:
            return False, "Ce coupon est désactivé", None

        # Vérifier les dates
        now = datetime.datetime.now()
        if discount.start_date and discount.start_date > now:
            return False, "Ce coupon n'est pas encore valide", None

        if discount.end_date and discount.end_date < now:
            return False, "Ce coupon a expiré", None

        # Vérifier le nombre d'utilisations
        if discount.max_uses and discount.current_uses >= discount.max_uses:
            return False, "Ce coupon a atteint sa limite d'utilisation", None

        return True, "Coupon valide", discount

    async def increment_usage(
        self, session: AsyncSession, discount_id: uuid.UUID
    ) -> Discount:
        """Incrémente le compteur d'utilisation d'une réduction"""
        discount = await session.get(Discount, discount_id)
        if discount:
            discount.current_uses += 1
            discount.modify_at = datetime.datetime.now()
            await session.commit()
            await session.refresh(discount)
        return discount


crud_discount = DiscountCrud(
    model=Discount,
    schema_create=DiscountCreate,
    schema_update=DiscountUpdate,
    order_by=Discount.created_at.desc(),
    outbox_events={
        "create": "create.discount",
        "update": "update.discount",
        "delete": "delete.discount",
    },
)
