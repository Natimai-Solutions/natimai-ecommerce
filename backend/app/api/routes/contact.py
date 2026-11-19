"""Public contact (chantier accueil et messagerie, lot MSG2).

``POST /contact`` takes a visitor's request: anti-robot check when the shop
configured one, a honeypot, limits per address and overall, and **the same
202 whatever happens** (an existing account, the honeypot filled): nothing
tells whether an address has an account, and nothing is e-mailed to the
address typed.

``/contact/continue/{token}`` follows the link of a team reply: signing up
through it, or signing in with an account of that very address, attaches the
visitor's conversations to the account.
"""

from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import CurrentUser, SessionDep, module_required
from app.api.routes.signup import _open_session
from app.core.captcha import require_captcha
from app.core.datetimes import utcnow
from app.core.errors import AppError
from app.core.i18n import request_locale
from app.core.rate_limit import hit_rate_limit, rate_limited
from app.core.security import aget_password_hash
from app.features.messaging import guests, service
from app.features.messaging.models import BODY_MAX, SUBJECT_MAX, MessageSide
from app.features.user.crud.user import crud_user
from app.features.user.models.user import AccessTokenResponse, User
from app.features.user.services.guest import claim_guest_account

router = APIRouter(
    prefix="/contact",
    tags=["contact"],
    dependencies=[Depends(module_required("messaging"))],
)

#: All visitors together: a flood from many addresses stops here.
#: Requests of one address an hour (a visitor writes once or twice).
PER_ADDRESS_LIMIT_PER_HOUR = 3
GLOBAL_LIMIT_PER_HOUR = 200


class ContactRequest(BaseModel):
    topic: str = Field(max_length=30)
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=255)
    subject: str = Field(default="", max_length=SUBJECT_MAX)
    body: str = Field(min_length=1, max_length=BODY_MAX)
    #: Honeypot: a hidden field a person never fills.
    website: str = Field(default="", max_length=200)


class Received(BaseModel):
    status: str = "received"


class ContinueInfo(BaseModel):
    number: str
    email: str
    name: str | None = None
    #: ``none``: sign up; ``account``: sign in first, then attach.
    account: str


class ContinueSignup(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class Attached(BaseModel):
    conversation_id: uuid.UUID


@router.post(
    "",
    response_model=Received,
    status_code=202,
    dependencies=[Depends(rate_limited("contact", limit=5, window_seconds=3600))],
)
async def contact(
    body: ContactRequest, request: Request, session: SessionDep
) -> Received:
    """A visitor writes to the shop. Always 202: the team answers by e-mail."""
    if body.website.strip():
        return Received()  # a robot: dropped, same answer
    # The captcha and the topic first: a request refused there never uses
    # up the shared hourly ceiling (a robot without a captcha emptied it).
    await require_captcha(request, session)
    channel = service.channel_of(body.topic)  # 400 on an unknown topic
    email = str(body.email).strip().lower()
    digest = hashlib.sha256(email.encode()).hexdigest()[:32]
    for key, limit in (
        (f"contact:email:{digest}", PER_ADDRESS_LIMIT_PER_HOUR),
        ("contact:all", GLOBAL_LIMIT_PER_HOUR),
    ):
        if await hit_rate_limit(key, limit=limit, window_seconds=3600):
            raise AppError(
                code="contact.rate_limited",
                status_code=429,
                message="Too many attempts: try again in a few minutes.",
                details={"scope": "contact"},
            )
    phone = (body.phone or "").strip() or None
    company = (body.company or "").strip() or None
    existing = await guests.open_guest_conversation_for(session, email, channel=channel)
    # Nothing proves who writes: a new request joins the open one only when
    # it says the same (name, phone, company); otherwise its own thread, so
    # that nobody writes into a stranger's conversation under their name.
    if existing is not None and not (
        (existing.guest_name or "").strip().casefold() == body.name.strip().casefold()
        and (phone is None or phone == existing.guest_phone)
        and (company is None or company == existing.guest_company)
    ):
        existing = None
    if existing is not None:
        await service.add_message(
            session,
            existing,
            side=MessageSide.CUSTOMER,
            body=body.body,
            author_id=None,
        )
    else:
        await service.open_conversation(
            session,
            topic=body.topic,
            subject=body.subject,
            body=body.body,
            customer=None,
            guest={
                "guest_name": body.name.strip(),
                "guest_email": email,
                "guest_phone": phone,
                "guest_company": company,
                "guest_locale": request_locale(),
            },
        )
    await session.commit()
    return Received()


@router.get(
    "/continue/{token}",
    response_model=ContinueInfo,
    dependencies=[
        Depends(rate_limited("contact_continue", limit=30, window_seconds=600))
    ],
)
async def continue_info(token: str, session: SessionDep) -> ContinueInfo:
    """What the link of a team reply opens: the address it was sent to, and
    whether it already has an account (only the holder of the link sees it)."""
    conversation = await guests.conversation_for_token(session, token)
    email = str(conversation.guest_email)
    user = await crud_user.get_by_email(session, email=email)
    has_account = user is not None and not user.is_guest
    return ContinueInfo(
        number=conversation.number,
        email=email,
        name=conversation.guest_name,
        account="account" if has_account else "none",
    )


@router.post(
    "/continue/{token}/signup",
    response_model=AccessTokenResponse,
    dependencies=[
        Depends(rate_limited("contact_continue", limit=30, window_seconds=600))
    ],
)
async def continue_with_signup(
    token: str, body: ContinueSignup, session: SessionDep, response: Response
) -> AccessTokenResponse:
    """Create the account of the link's address (proven: the link was only
    sent there), attach the visitor's conversations and sign in."""
    conversation = await guests.conversation_for_token(session, token)
    email = str(conversation.guest_email)
    existing = await crud_user.get_by_email(session, email=email)
    if existing is not None and not existing.is_guest:
        raise AppError(
            code="messaging.link_account_exists",
            status_code=409,
            message="An account already exists with this address: sign in to continue.",
            details={},
        )
    password_hash = await aget_password_hash(body.password)
    full_name = (body.full_name or "").strip() or conversation.guest_name
    if existing is not None:
        user = existing
        await claim_guest_account(session, user)
        user.hashed_password = password_hash
        user.has_password = True
        if full_name:
            user.full_name = full_name
    else:
        user = User(
            email=email,
            full_name=full_name,
            phone=conversation.guest_phone,
            is_verified=True,
            hashed_password=password_hash,
            has_password=True,
        )
    session.add(user)
    await session.flush()
    await guests.attach_to_account(session, conversation, user.id)
    return await _open_session(session, response, user)


@router.post(
    "/continue/{token}/claim",
    response_model=Attached,
    dependencies=[
        Depends(rate_limited("contact_continue", limit=30, window_seconds=600))
    ],
)
async def continue_signed_in(
    token: str, session: SessionDep, current_user: CurrentUser
) -> Attached:
    """Signed in with the account of the link's address: attach the visitor's
    conversations. Another account reads the link as invalid."""
    conversation = await guests.conversation_for_token(session, token, now=utcnow())
    if str(current_user.email).lower() != str(conversation.guest_email).lower():
        raise guests.invalid_link()
    conversation_id = conversation.id
    await guests.attach_to_account(session, conversation, current_user.id)
    await session.commit()
    return Attached(conversation_id=conversation_id)


__all__ = ["router"]
