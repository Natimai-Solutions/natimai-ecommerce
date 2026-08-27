from unittest.mock import MagicMock, patch

from app.tests_pre_start import init, logger


def test_init_successful_connection() -> None:
    engine_mock = MagicMock()

    session_in_context = MagicMock()
    session_in_context.exec.return_value = True
    session_context_manager = MagicMock()
    session_context_manager.__enter__.return_value = session_in_context
    session_context_manager.__exit__.return_value = None

    with (
        patch("app.tests_pre_start.Session", return_value=session_context_manager),
        patch.object(logger, "info"),
        patch.object(logger, "error"),
        patch.object(logger, "warn"),
    ):
        init(engine_mock)

        session_in_context.exec.assert_called_once()
