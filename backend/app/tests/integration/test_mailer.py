"""Integration (real DB): every e-mail is journaled — sent now or by the
worker — a secret never stays in the journal once sent, and a queue outage
does not lose the message."""

from __future__ import annotations

from typing import Any

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.notification import mailer
from app.features.notification.models.email_log import EmailLog
from app.features.notification.providers.base import NotificationResult


class _Provider:
    def __init__(self, delivered: bool = True) -> None:
        self.delivered = delivered
        self.sent: list[Any] = []

    async def send(self, message: Any) -> NotificationResult:
        self.sent.append(message)
        return NotificationResult(
            provider_code="fake",
            delivered=self.delivered,
            error=None if self.delivered else "down",
        )


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> _Provider:
    fake = _Provider()
    monkeypatch.setattr(mailer, "get_notification_provider", lambda _code: fake)
    return fake


async def _logs(session: AsyncSession) -> list[EmailLog]:
    return list(
        (await session.exec(select(EmailLog).order_by(col(EmailLog.created_at)))).all()
    )


@pytest.mark.asyncio
async def test_a_sent_email_is_journaled_even_if_the_caller_never_commits(
    db_session: AsyncSession, provider: _Provider
) -> None:
    result = await mailer.send_email(
        db_session,
        recipient="tea@example.pf",
        subject="Votre commande",
        text="Bonjour",
        html="<p>Bonjour</p>",
        event_type="order.created",
    )
    await db_session.rollback()  # the caller's work is not the journal's

    assert result.delivered and len(provider.sent) == 1
    [log] = await _logs(db_session)
    assert (log.status, log.attempts, log.event_type) == ("sent", 1, "order.created")
    assert log.body_html == "<p>Bonjour</p>" and log.resendable


@pytest.mark.asyncio
async def test_a_secret_is_dropped_from_the_journal_once_sent(
    db_session: AsyncSession,
    provider: _Provider,
    arq_queue: Any,
) -> None:
    log_id = await mailer.queue_email(
        db_session,
        recipient="tea@example.pf",
        subject="Réinitialisation",
        text="https://boutique/reinitialiser?token=SECRET",
        html=None,
        event_type="password.reset_requested",
        resendable=False,
    )
    # Queued for the worker, not sent in the request.
    assert [job["function"] for job in arq_queue.jobs] == ["send_queued_email_task"]
    assert provider.sent == []

    sent = await mailer.send_queued(db_session, log_id)

    assert sent is not None and sent.status == "sent"
    assert sent.body_text is None and sent.body_html is None
    assert "SECRET" in provider.sent[0].text


@pytest.mark.asyncio
async def test_without_a_queue_the_message_is_sent_inline(
    db_session: AsyncSession, provider: _Provider, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _down() -> Any:
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.core.arq_worker.get_redis_pool", _down)

    await mailer.queue_email(
        db_session,
        recipient="tea@example.pf",
        subject="Code",
        text="123456",
        html=None,
        event_type="signup.otp",
        resendable=False,
    )

    assert len(provider.sent) == 1
    [log] = await _logs(db_session)
    assert log.status == "sent"


@pytest.mark.asyncio
async def test_a_failed_send_is_journaled_as_failed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    down = _Provider(delivered=False)
    monkeypatch.setattr(mailer, "get_notification_provider", lambda _code: down)

    result = await mailer.send_email(
        db_session,
        recipient="tea@example.pf",
        subject="Facture",
        text="…",
        html=None,
        event_type="invoice.issued",
    )

    assert not result.delivered
    [log] = await _logs(db_session)
    assert log.status == "failed" and log.last_error
