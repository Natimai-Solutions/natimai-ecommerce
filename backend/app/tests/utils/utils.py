from fastapi.testclient import TestClient

from app.core.config import settings


def get_superuser_token_headers(client: TestClient) -> dict[str, str]:
    """Return auth headers for the configured superuser test account."""
    login_data = {
        "username": settings.FIRST_SUPERUSER,
        "password": settings.FIRST_SUPERUSER_PASSWORD,
    }
    response = client.post(
        f"{settings.API_V1_STR}/login/access-token",
        data=login_data,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Superuser login failed ({response.status_code}): {response.text}"
        )

    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}
