"""Integration tests (real DB): the messaging between a customer and the shop
(chantier accueil et messagerie, lot MSG1) — who reads what, who holds a
conversation, and the e-mails about unread messages."""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import admin_messaging as staff_routes
from app.api.routes import messaging as routes
from app.core.config import settings
from app.core.datetimes import utcnow
from app.core.errors import AppError
from app.features.messaging import notify
from app.features.messaging.info import Hours, business_hours_between, step_of
from app.features.messaging.models import Conversation
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.user.models.user import User
from app.features.user.models.user_preference import UserPreference

pytestmark = pytest.mark.asyncio


async def _user(session: AsyncSession, key: str, *, staff: bool = False) -> User:
    user = User(
        email=f"{key}+{uuid.uuid4().hex[:6]}@t.local",
        full_name=key.capitalize(),
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=staff,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _fresh(session: AsyncSession, *users: User) -> None:
    for user in users:
        await session.refresh(user)


async def _open(session: AsyncSession, customer: User, **fields: Any) -> uuid.UUID:
    await session.refresh(customer)
    body = routes.ConversationCreate.model_validate(
        {"topic": "delivery", "subject": "Mon colis", "body": "Où est-il ?", **fields}
    )
    created = await routes.open_my_conversation(body, session, customer)
    return created.id


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def never(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(routes, "hit_rate_limit", never)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    outbox: list[dict[str, Any]] = []

    async def queue_email(_session: Any, **kwargs: Any) -> uuid.UUID:
        outbox.append(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(notify, "queue_email", queue_email)
    return outbox


async def test_a_customer_reaches_only_their_conversations(
    db_session: AsyncSession,
) -> None:
    alice = await _user(db_session, "alice")
    bob = await _user(db_session, "bob")
    conversation_id = await _open(db_session, alice)
    await _fresh(db_session, alice, bob)

    mine = await routes.get_my_conversation(conversation_id, db_session, alice)
    assert mine.channel == "customer_service" and mine.topic == "delivery"
    assert [m.body for m in mine.messages] == ["Où est-il ?"]
    assert mine.number.startswith("C-")

    for call in (
        lambda: routes.get_my_conversation(conversation_id, db_session, bob),
        lambda: routes.post_my_message(
            conversation_id, routes.MessageCreate(body="x"), db_session, bob
        ),
        lambda: routes.read_my_conversation(conversation_id, db_session, bob),
        lambda: routes.resolve_my_conversation(conversation_id, db_session, bob),
    ):
        with pytest.raises(AppError) as refused:
            await call()
        assert refused.value.status_code == 404
    assert await routes.list_my_conversations(db_session, bob) == []


async def test_a_customer_attaches_only_their_own_order(
    db_session: AsyncSession,
) -> None:
    alice = await _user(db_session, "alice")
    bob = await _user(db_session, "bob")
    status = OrderStatus(name=f"Pending {uuid.uuid4().hex[:6]}")
    db_session.add(status)
    await db_session.flush()
    order = Order(user_id=bob.id, order_status_id=status.id)
    db_session.add(order)
    order_id = order.id
    await db_session.commit()
    await _fresh(db_session, alice)
    with pytest.raises(AppError) as refused:
        await _open(db_session, alice, context_type="order", context_id=str(order_id))
    assert refused.value.code == "messaging.context_not_found"
    with pytest.raises(AppError):
        await _open(db_session, alice, topic="no_such_topic")
    await _fresh(db_session, bob)
    opened = await _open(
        db_session, bob, context_type="order", context_id=str(order_id)
    )
    await _fresh(db_session, bob)
    detail = await routes.get_my_conversation(opened, db_session, bob)
    assert detail.context_id == order_id


async def test_notes_stay_internal_and_move_nothing(
    db_session: AsyncSession, sent: list[dict[str, Any]]
) -> None:
    alice = await _user(db_session, "alice")
    agent = await _user(db_session, "agent", staff=True)
    conversation_id = await _open(db_session, alice)
    await _fresh(db_session, agent)
    before = await db_session.get(Conversation, conversation_id)
    assert before is not None
    status, staff_at = before.status, before.last_staff_message_at

    await staff_routes.post_staff_message(
        conversation_id,
        staff_routes.StaffMessageCreate(
            body="Client pressé, voir le transporteur", kind="note"
        ),
        db_session,
        agent,
    )
    await _fresh(db_session, alice, agent)
    after = await db_session.get(Conversation, conversation_id)
    assert after is not None
    await db_session.refresh(after)
    assert (after.status, after.last_staff_message_at) == (status, staff_at)
    assert after.assigned_to_id is None  # a note does not take the conversation

    seen = await routes.get_my_conversation(conversation_id, db_session, alice)
    assert [m.body for m in seen.messages] == ["Où est-il ?"]
    assert (await routes.my_unread_count(db_session, alice)).count == 0
    await notify.notify_unread(db_session, now=utcnow() + datetime.timedelta(hours=1))
    assert [m for m in sent if m["event_type"] == "messaging.reply"] == []

    await _fresh(db_session, agent)
    staff_view = await staff_routes.get_conversation(conversation_id, db_session, agent)
    assert [m.kind for m in staff_view.messages] == ["message", "note"]


async def test_taking_answering_resolving_and_reopening(
    db_session: AsyncSession,
) -> None:
    alice = await _user(db_session, "alice")
    first = await _user(db_session, "first", staff=True)
    second = await _user(db_session, "second", staff=True)
    conversation_id = await _open(db_session, alice)
    await _fresh(db_session, first, second)

    answered = await staff_routes.post_staff_message(
        conversation_id,
        staff_routes.StaffMessageCreate(body="Il part demain."),
        db_session,
        first,
    )
    assert answered.assigned_to_id == first.id and answered.status == "pending"
    await _fresh(db_session, alice, first, second)
    assert (await routes.my_unread_count(db_session, alice)).count == 1

    # A second member cannot take it, nor resolve it, without forcing.
    with pytest.raises(AppError) as taken:
        await staff_routes.claim_conversation(conversation_id, db_session, second)
    assert taken.value.code == "messaging.already_claimed"
    await _fresh(db_session, second)
    with pytest.raises(AppError) as held:
        await staff_routes.resolve_conversation(conversation_id, db_session, second)
    assert held.value.code == "messaging.held_by_other"
    # A reply of the second member does not take it over either.
    await _fresh(db_session, second)
    replied = await staff_routes.post_staff_message(
        conversation_id,
        staff_routes.StaffMessageCreate(body="Je confirme."),
        db_session,
        second,
    )
    assert replied.assigned_to_id == first.id

    # The customer writes back: open again; then settles it: the holder stays.
    await _fresh(db_session, alice)
    await routes.post_my_message(
        conversation_id, routes.MessageCreate(body="Merci !"), db_session, alice
    )
    await _fresh(db_session, alice)
    resolved = await routes.resolve_my_conversation(conversation_id, db_session, alice)
    assert resolved.status == "resolved"
    await _fresh(db_session, first)
    conversation = await db_session.get(Conversation, conversation_id)
    assert conversation is not None and conversation.assigned_to_id == first.id

    # Writing on a resolved conversation reopens it, back in the shared queue.
    await _fresh(db_session, alice)
    reopened = await routes.post_my_message(
        conversation_id, routes.MessageCreate(body="En fait non"), db_session, alice
    )
    assert reopened.status == "open"
    await _fresh(db_session, first)
    todo = await staff_routes.list_conversations(db_session, first, tab="todo")
    assert [c.id for c in todo.data] == [conversation_id]
    assert todo.data[0].assigned_to_id is None

    # Forced take, transfer to someone who cannot handle it: refused.
    await _fresh(db_session, second)
    await staff_routes.claim_conversation(conversation_id, db_session, second)
    customer_as_target = staff_routes.TransferBody(user_id=alice.id)
    await _fresh(db_session, second)
    with pytest.raises(AppError) as invalid:
        await staff_routes.transfer_conversation(
            conversation_id, customer_as_target, db_session, second
        )
    assert invalid.value.code == "messaging.invalid_assignee"


async def test_resolving_a_free_conversation_gives_it_a_holder(
    db_session: AsyncSession,
) -> None:
    alice = await _user(db_session, "alice")
    agent = await _user(db_session, "agent", staff=True)
    conversation_id = await _open(db_session, alice)
    await _fresh(db_session, agent)
    resolved = await staff_routes.resolve_conversation(
        conversation_id, db_session, agent
    )
    assert resolved.status == "resolved" and resolved.assigned_to_id == agent.id
    events = [m.data.get("action") for m in resolved.messages if m.kind == "event"]
    assert events == ["resolved"]


async def test_unread_notices_once_per_wave(
    db_session: AsyncSession,
    sent: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMAIL_SUPPORT", "support@shop.pf")
    alice = await _user(db_session, "alice")
    quiet = await _user(db_session, "quiet")
    db_session.add(UserPreference(user_id=quiet.id, notification_messages=False))
    agent = await _user(db_session, "agent", staff=True)
    talking = await _open(db_session, alice)
    await _fresh(db_session, quiet)
    silent = await _open(db_session, quiet)

    # The team is told about both (no holder: the support address).
    later = utcnow() + datetime.timedelta(minutes=15)
    await notify.notify_unread(db_session, now=later)
    staff = [m for m in sent if m["event_type"] == "messaging.staff_waiting"]
    assert len(staff) == 2 and {m["recipient"] for m in staff} == {"support@shop.pf"}
    sent.clear()
    await notify.notify_unread(db_session, now=later)
    assert sent == []  # same wave: nothing again

    for conversation_id in (talking, silent):
        await _fresh(db_session, agent)
        await staff_routes.post_staff_message(
            conversation_id,
            staff_routes.StaffMessageCreate(body="Réponse"),
            db_session,
            agent,
        )
    await _fresh(db_session, alice)
    alice_email = alice.email
    later = utcnow() + datetime.timedelta(minutes=15)
    await notify.notify_unread(db_session, now=later)
    replies = [m for m in sent if m["event_type"] == "messaging.reply"]
    assert [m["recipient"] for m in replies] == [alice_email]
    assert "Réponse" not in replies[0]["text"]  # never the content
    assert str(talking) in replies[0]["text"]


async def test_a_failure_after_the_marker_does_not_send_twice(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = await _user(db_session, "alice")
    agent = await _user(db_session, "agent", staff=True)
    conversation_id = await _open(db_session, alice)
    await _fresh(db_session, agent)
    await staff_routes.post_staff_message(
        conversation_id,
        staff_routes.StaffMessageCreate(body="Réponse"),
        db_session,
        agent,
    )
    calls: list[str] = []

    async def failing(_session: Any, **kwargs: Any) -> uuid.UUID:
        calls.append(kwargs["event_type"])
        raise RuntimeError("queue down")

    monkeypatch.setattr(notify, "queue_email", failing)
    later = utcnow() + datetime.timedelta(minutes=15)
    with pytest.raises(RuntimeError):
        await notify.notify_unread(db_session, now=later)
    calls.clear()
    await notify.notify_unread(db_session, now=later)
    assert calls == []


async def test_stale_conversations_go_back_to_the_queue(
    db_session: AsyncSession,
) -> None:
    alice = await _user(db_session, "alice")
    agent = await _user(db_session, "agent", staff=True)
    conversation_id = await _open(db_session, alice)
    await _fresh(db_session, agent)
    await staff_routes.claim_conversation(conversation_id, db_session, agent)
    assert await notify.release_stale(db_session) == 0
    released = await notify.release_stale(
        db_session, now=utcnow() + datetime.timedelta(days=4)
    )
    assert released == 1
    conversation = await db_session.get(Conversation, conversation_id)
    assert conversation is not None
    await db_session.refresh(conversation)
    assert (
        conversation.assigned_to_id is None and conversation.staff_notified_at is None
    )


async def test_business_hours_and_response_steps() -> None:
    tahiti = ZoneInfo("Pacific/Tahiti")
    hours = Hours(
        start=datetime.time(8), end=datetime.time(17), days=frozenset({1, 2, 3, 4, 5})
    )
    friday_16h = datetime.datetime(2026, 11, 20, 16, tzinfo=tahiti)
    monday_9h = datetime.datetime(2026, 11, 23, 9, tzinfo=tahiti)
    assert business_hours_between(friday_16h, monday_9h, hours, tahiti) == 2.0
    assert step_of(1.5, hours.per_day) == ("hours", 2)
    assert step_of(7.9, hours.per_day) == ("hours", 8)
    assert step_of(9, hours.per_day) == ("business_days", 1)
    assert step_of(12, hours.per_day) == ("business_days", 2)


async def test_export_holds_messages_never_notes_and_erasure_removes_all(
    db_session: AsyncSession,
) -> None:
    from app.features.messaging.retention import (
        erase_conversations,
        export_conversations,
    )

    alice = await _user(db_session, "alice")
    agent = await _user(db_session, "agent", staff=True)
    conversation_id = await _open(db_session, alice)
    await _fresh(db_session, agent)
    await staff_routes.post_staff_message(
        conversation_id,
        staff_routes.StaffMessageCreate(body="Note secrète", kind="note"),
        db_session,
        agent,
    )
    await _fresh(db_session, alice)
    alice_id = alice.id
    exported = await export_conversations(db_session, alice_id)
    assert [m["body"] for m in exported[0]["messages"]] == ["Où est-il ?"]
    assert "Note secrète" not in str(exported)

    await erase_conversations(db_session, alice_id)
    await db_session.commit()
    assert await export_conversations(db_session, alice_id) == []


async def test_retention_notice_then_deletion_and_keeping_longer(
    db_session: AsyncSession,
    sent: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.features.messaging import retention

    async def queue_email(_session: Any, **kwargs: Any) -> uuid.UUID:
        sent.append(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(retention, "queue_email", queue_email)
    alice = await _user(db_session, "alice")
    kept_id = await _open(db_session, alice)
    gone_id = await _open(db_session, alice)
    for conversation_id in (kept_id, gone_id):
        await _fresh(db_session, alice)
        await routes.resolve_my_conversation(conversation_id, db_session, alice)
    guest = Conversation(
        number=f"C-T-{uuid.uuid4().hex[:6]}",
        channel="sales",
        topic="pre_sale",
        subject="Visiteur",
        guest_email="visiteur@example.com",
        last_message_at=utcnow(),
    )
    db_session.add(guest)
    guest_id = guest.id
    await db_session.commit()

    five_years = utcnow() + datetime.timedelta(days=1826)
    # A month before the date: a notice (no content), nothing deleted.
    result = await retention.retention_sweep(
        db_session, now=five_years - datetime.timedelta(days=20)
    )
    assert result == {"guests": 1, "notices": 2, "deleted": 0}
    notices = [m for m in sent if m["event_type"] == "messaging.deletion_notice"]
    assert len(notices) == 2 and "Où est-il" not in notices[0]["text"]
    assert await db_session.get(Conversation, guest_id) is None

    # The customer keeps one: a year more, the notice cancelled.
    await _fresh(db_session, alice)
    kept = await routes.keep_my_conversation(kept_id, db_session, alice)
    assert kept.retain_until > five_years

    result = await retention.retention_sweep(
        db_session, now=five_years + datetime.timedelta(days=15)
    )
    assert result["deleted"] == 1
    db_session.expire_all()
    assert await db_session.get(Conversation, gone_id) is None
    assert await db_session.get(Conversation, kept_id) is not None


async def test_the_customer_downloads_messages_only(db_session: AsyncSession) -> None:
    alice = await _user(db_session, "alice")
    agent = await _user(db_session, "agent", staff=True)
    conversation_id = await _open(db_session, alice)
    await _fresh(db_session, agent)
    await staff_routes.post_staff_message(
        conversation_id,
        staff_routes.StaffMessageCreate(body="Interne", kind="note"),
        db_session,
        agent,
    )
    await _fresh(db_session, alice)
    exported = await routes.export_my_conversation(conversation_id, db_session, alice)
    text = bytes(exported.body).decode()
    assert "Où est-il ?" in text and "Interne" not in text


def _photo(fmt: str = "JPEG", *, gps: bool = True) -> bytes:
    import io

    from PIL import Image

    image = Image.new("RGB", (4000, 3000), (120, 30, 30))
    buffer = io.BytesIO()
    if fmt == "HEIF":
        from pillow_heif import register_heif_opener

        register_heif_opener()
        image.resize((400, 300)).save(buffer, format="HEIF")
        return buffer.getvalue()
    exif = Image.Exif()
    if gps:
        exif[0x8825] = {1: "S", 2: (17.0, 32.0, 0.0), 3: "W", 4: (149.0, 34.0, 0.0)}
        exif[0x010F] = "Apple"
    image.save(buffer, format=fmt, exif=exif.tobytes())
    return buffer.getvalue()


def _upload(data: bytes, name: str) -> Any:
    import io

    from fastapi import UploadFile

    return UploadFile(file=io.BytesIO(data), filename=name)


@pytest.fixture
def local_files(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    from app.features.attachment.storage.factory import reset_file_storage_cache

    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))
    reset_file_storage_cache()
    yield tmp_path
    reset_file_storage_cache()


@pytest.mark.usefixtures("local_files")
async def test_photos_lose_their_metadata_and_notes_keep_their_files(
    db_session: AsyncSession,
) -> None:
    import io

    from PIL import Image

    alice = await _user(db_session, "alice")
    agent = await _user(db_session, "agent", staff=True)
    conversation_id = await _open(db_session, alice)

    await _fresh(db_session, alice)
    detail = await routes.post_my_file(
        conversation_id,
        db_session,
        alice,
        file=_upload(_photo(), "../../colis abîmé.jpg"),
        body="",
    )
    sent_file = detail.messages[-1].attachments[0]
    assert sent_file.mime == "image/jpeg" and sent_file.filename == "colis abîmé.jpg"
    await _fresh(db_session, alice)
    response = await routes.get_my_file(
        conversation_id, sent_file.id, db_session, alice
    )
    stored = Image.open(io.BytesIO(bytes(response.body)))
    assert max(stored.size) == 2560  # re-encoded, reduced
    assert not stored.getexif()  # no GPS, no camera
    assert (
        "filename*=UTF-8''colis%20ab%C3%AEm%C3%A9.jpg"
        in response.headers["content-disposition"]
    )

    # An iPhone photo becomes a JPEG.
    await _fresh(db_session, alice)
    detail = await routes.post_my_file(
        conversation_id, db_session, alice, file=_upload(_photo("HEIF"), "IMG_1.HEIC")
    )
    assert detail.messages[-1].attachments[0].mime == "image/jpeg"
    assert detail.messages[-1].attachments[0].filename == "IMG_1.jpg"

    # Anything else is refused on its bytes, whatever its name.
    await _fresh(db_session, alice)
    with pytest.raises(AppError) as refused:
        await routes.post_my_file(
            conversation_id, db_session, alice, file=_upload(b"MZ\x90\x00", "photo.jpg")
        )
    assert refused.value.status_code == 415

    # A file joined to an internal note never reaches the customer.
    await _fresh(db_session, agent)
    staff_view = await staff_routes.post_staff_file(
        conversation_id,
        db_session,
        agent,
        file=_upload(b"%PDF-1.4 bon de livraison", "bl.pdf"),
        body="BL du transporteur",
        kind="note",
    )
    note_file = staff_view.messages[-1].attachments[0]
    assert staff_view.assigned_to_id is None  # a note does not take it
    await _fresh(db_session, alice)
    with pytest.raises(AppError) as hidden:
        await routes.get_my_file(conversation_id, note_file.id, db_session, alice)
    assert hidden.value.status_code == 404
    await _fresh(db_session, alice)
    seen = await routes.get_my_conversation(conversation_id, db_session, alice)
    assert all(a.id != note_file.id for m in seen.messages for a in m.attachments)


async def test_erasing_an_account_removes_its_files(
    db_session: AsyncSession, local_files: Any
) -> None:
    from app.features.messaging.retention import erase_conversations

    alice = await _user(db_session, "alice")
    conversation_id = await _open(db_session, alice)
    await _fresh(db_session, alice)
    await routes.post_my_file(
        conversation_id,
        db_session,
        alice,
        file=_upload(_photo("PNG", gps=False), "a.png"),
    )
    stored = [p for p in local_files.rglob("*") if p.is_file()]
    assert len(stored) == 1
    await _fresh(db_session, alice)
    await erase_conversations(db_session, alice.id)
    await db_session.commit()
    assert [p for p in local_files.rglob("*") if p.is_file()] == []


async def test_the_team_sees_the_customer_beside_the_thread(
    db_session: AsyncSession,
) -> None:
    bob = await _user(db_session, "bob")
    agent = await _user(db_session, "agent", staff=True)
    await _fresh(db_session, bob)
    status = OrderStatus(name=f"Paid {uuid.uuid4().hex[:6]}")
    db_session.add(status)
    await db_session.flush()
    order = Order(
        user_id=bob.id, order_status_id=status.id, order_number="CMD-2026-00042"
    )
    db_session.add(order)
    order_id = order.id
    await db_session.commit()
    conversation_id = await _open(
        db_session, bob, context_type="order", context_id=str(order_id)
    )
    await _fresh(db_session, agent)
    detail = await staff_routes.get_conversation(conversation_id, db_session, agent)
    assert detail.context_label == "CMD-2026-00042"
    assert detail.customer_panel is not None
    assert [o.number for o in detail.customer_panel.orders] == ["CMD-2026-00042"]
