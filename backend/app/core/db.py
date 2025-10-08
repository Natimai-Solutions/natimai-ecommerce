from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28
from app.features.models import *  # noqa

engine = create_async_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    echo=False,
    poolclass=AsyncAdaptedQueuePool,
    connect_args={
        "sslmode": settings.POSTGRES_SSL_MODE,
    },
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session


async def test_connection() -> bool:
    """
    Test database connection.

    Returns:
        True if connection is successful, raises exception otherwise
    """
    try:
        async with AsyncSession(engine) as session:
            # Simple query to test connection
            await session.exec(text("SELECT 1"))
            return True
    except Exception as e:
        raise Exception(f"Database connection failed: {e}")
