import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.backend_pre_start import init, logger


def test_init_successful_connection() -> None:
    engine_mock = MagicMock()

    session_mock = AsyncMock()
    session_mock.exec = AsyncMock(return_value=True)

    session_context_manager = AsyncMock()
    session_context_manager.__aenter__.return_value = session_mock
    session_context_manager.__aexit__.return_value = None

    with (
        patch(
            "app.backend_pre_start.AsyncSession",
            return_value=session_context_manager,
        ),
        patch.object(logger, "info"),
        patch.object(logger, "error"),
        patch.object(logger, "warn"),
    ):
        asyncio.run(init(engine_mock))

        session_mock.exec.assert_awaited_once()
