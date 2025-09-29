import uuid
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.user.models.review import Review, ReviewCreate, ReviewUpdate


class ReviewCrud(CrudBase[Review, ReviewCreate, ReviewUpdate]):
    
    async def get_by_user_id(
        self, 
        session: AsyncSession, 
        *, 
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100
    ) -> list[Review]:
        """Get reviews for a specific user."""
        statement = (
            select(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.is_admin_active.is_(True),
                self.model.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        exec_result = await session.exec(statement)
        return exec_result.all()
    
    async def get_by_product_id(
        self,
        session: AsyncSession,
        *,
        product_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100
    ) -> list[Review]:
        """Get reviews for a specific product."""
        statement = (
            select(self.model)
            .where(
                self.model.product_id == product_id,
                self.model.is_admin_active.is_(True),
                self.model.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        exec_result = await session.exec(statement)
        return exec_result.all()
    
    async def get_by_user_and_product(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        product_id: uuid.UUID
    ) -> Review | None:
        """Get a review by user and product (should be unique)."""
        statement = select(self.model).where(
            self.model.user_id == user_id,
            self.model.product_id == product_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()
    
    async def create_for_user(
        self,
        session: AsyncSession,
        *,
        obj_in: ReviewCreate,
        user_id: uuid.UUID,
        current_user: Optional[uuid.UUID] = None
    ) -> Review:
        """Create a review for a specific user."""
        obj_data = obj_in.model_dump()
        obj_data["user_id"] = user_id  # Override user_id to ensure it matches the URL parameter
        if current_user:
            obj_data["created_by_id"] = current_user
        db_obj = self.model(**obj_data)
        session.add(db_obj)
        await session.commit()
        await session.refresh(db_obj)
        return db_obj
    
    async def count_by_user(
        self, 
        session: AsyncSession, 
        *, 
        user_id: uuid.UUID
    ) -> int:
        """Count reviews for a user."""
        statement = select(self.model).where(
            self.model.user_id == user_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return len(exec_result.all())
    
    async def count_by_product(
        self, 
        session: AsyncSession, 
        *, 
        product_id: uuid.UUID
    ) -> int:
        """Count reviews for a product."""
        statement = select(self.model).where(
            self.model.product_id == product_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return len(exec_result.all())
    
    async def get_average_rating_by_product(
        self, 
        session: AsyncSession, 
        *, 
        product_id: uuid.UUID
    ) -> float | None:
        """Get average rating for a product."""
        statement = select(self.model.rating).where(
            self.model.product_id == product_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        ratings = exec_result.all()
        
        if not ratings:
            return None
            
        return sum(ratings) / len(ratings)


crud_review = ReviewCrud(
    model=Review,
    schema_create=ReviewCreate,
    schema_update=ReviewUpdate,
    order_by=Review.created_at,
)