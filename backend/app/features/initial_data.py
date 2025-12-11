from sqlalchemy.ext.asyncio import AsyncSession

from app.features.order.initial_data import init_order_statuses


async def initial_data(session: AsyncSession) -> None:
    await init_order_statuses(session)
