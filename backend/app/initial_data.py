import asyncio
import logging

from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import engine
from app.features.initial_data import initial_data as api_initial_data
from app.features.user.models.user import User, UserCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_db(session: AsyncSession) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # from app.core.engine import engine
    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)
    """
    User
    """
    logger.info("User initial data: Begin")
    users = (await session.exec(select(func.count()).select_from(User))).one()

    if users == 0:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
            is_verified=True,
        )
        session.add(User.model_validate(user_in))
        logger.info("User initial data: Superuser created")
    else:
        logger.info("User initial data: Nothing to do")


async def init() -> None:
    async with AsyncSession(engine) as session:
        await init_db(session)
        await api_initial_data(session)
        await session.commit()


async def main() -> None:
    logger.info("Creating initial data")
    await init()
    logger.info("Initial data created")


if __name__ == "__main__":
    asyncio.run(main())
