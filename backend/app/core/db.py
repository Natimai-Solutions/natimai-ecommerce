import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlmodel import QueuePool, Session, create_engine, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.core.user import crud as user_crud

# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28
from backend.app.api.models import *  # noqa
from backend.app.api.models import User, UserCreate  # explicit import for User model
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_async_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    echo=False,
    poolclass=AsyncAdaptedQueuePool,
    connect_args={
        "sslmode": settings.POSTGRES_SSL_MODE,
    },
)

sync_engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    echo=False,
    poolclass=QueuePool,
    connect_args={
        "sslmode": settings.POSTGRES_SSL_MODE,
    },
)


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    with Session(sync_engine) as session:
        yield session


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


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
        await user_crud.create_user(session=session, user_create=user_in)
        logger.info("User initial data: Superuser created")
    else:
        logger.info("User initial data: Nothing to do")
