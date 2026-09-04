from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.security import get_password_hash
from app.features.user.crud.user import crud_user
from app.features.user.models.user import User

TEST_USER_PASSWORD = "testpassword123"


async def authentication_token_from_email(
    client: TestClient,
    email: str,
    db: AsyncSession,
) -> dict[str, str]:
    """Get auth headers for a user; create a basic test user if needed."""
    password = settings.FIRST_SUPERUSER_PASSWORD

    if email != settings.FIRST_SUPERUSER:
        password = TEST_USER_PASSWORD
        user = await crud_user.get_by_email(db, email=email)
        if not user:
            # Ligne construite directement : le model_validator de UserCreate
            # pose hashed_password, mais le champ est exclu du model_dump que
            # le CRUD utilise — l'insert partait donc sans empreinte (NOT NULL).
            db.add(
                User(
                    email=email,
                    hashed_password=get_password_hash(TEST_USER_PASSWORD),
                    full_name="Test User",
                    is_verified=True,
                )
            )
            await db.commit()

    login_data = {"username": email, "password": password}
    response = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data=login_data,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"User login failed ({response.status_code}): {response.text}"
        )

    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}
