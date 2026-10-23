"""No secret reaches a log line: a record carrying a sensitive ``extra``
field is dropped (and reported on stderr), e-mails are masked."""

from __future__ import annotations

import logging

import pytest

from app.core.logging_config import (
    FORBIDDEN_EXTRA_KEYS,
    SensitiveFieldFilter,
    mask_email,
)


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "msg", (), None)
    record.__dict__.update(extra)
    return record


@pytest.mark.parametrize("key", sorted(FORBIDDEN_EXTRA_KEYS))
def test_a_sensitive_extra_drops_the_record(
    key: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert SensitiveFieldFilter().filter(_record(**{key: "x"})) is False
    assert key in capsys.readouterr().err


def test_an_ordinary_record_goes_through() -> None:
    assert SensitiveFieldFilter().filter(_record(order_id="abc", unit="%")) is True


def test_configured_handlers_carry_the_filter() -> None:
    from app.core.logging_config import configure_logging

    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    try:
        configure_logging(service="test", fmt="json")
        assert root.handlers
        assert all(
            any(isinstance(f, SensitiveFieldFilter) for f in handler.filters)
            for handler in root.handlers
        )
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])


def test_mask_email() -> None:
    assert mask_email("tea.vahine@example.pf") == "t***@example.pf"
    assert mask_email(None) == "***"
    assert mask_email("not-an-email") == "***"
