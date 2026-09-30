"""Group upgrade request workflow.

POST /users/me/upgrade-group                          — user submits a request
GET  /users/me/upgrade-group                          — list own requests
GET  /admin/group-upgrade-requests                    — admin: list all pending
POST /admin/group-upgrade-requests/{id}/approve       — admin: approve → update User.price_group_id
POST /admin/group-upgrade-requests/{id}/reject        — admin: reject with comment
POST /admin/users/{user_id}/assign-price-group        — admin: direct assignment
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, CurrentUser, SessionDep, module_required
from app.core.errors import AppError
from app.features.base.models import Message
from app.features.product.models.price_group import PriceGroup
from app.features.user.models.group_upgrade_request import (
    GroupUpgradeRequest,
    GroupUpgradeRequestCreate,
    GroupUpgradeRequestPublic,
    GroupUpgradeRequestsPublic,
    UpgradeRequestStatus,
)
from app.features.user.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["user"], dependencies=[Depends(module_required("price_groups"))]
)

EVENT_UPGRADE_APPROVED = "user.group_upgrade.approved"
EVENT_UPGRADE_REJECTED = "user.group_upgrade.rejected"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_request(
    session: SessionDep, request_id: uuid.UUID
) -> GroupUpgradeRequest:
    req = await session.get(GroupUpgradeRequest, request_id)
    if req is None:
        raise AppError(
            code="user.upgrade_request.not_found",
            status_code=404,
            message=f"Upgrade request '{request_id}' not found",
            details={"request_id": str(request_id)},
        )
    return req


async def _load_active_price_group(
    session: SessionDep, price_group_id: uuid.UUID
) -> PriceGroup:
    group = await session.get(PriceGroup, price_group_id)
    if group is None or not group.is_active:
        raise AppError(
            code="resource.not_found",
            status_code=404,
            message=f"Price group '{price_group_id}' not found",
            details={"resource": "price_group", "id": str(price_group_id)},
        )
    return group


# ---------------------------------------------------------------------------
# User: submit / list own requests
# ---------------------------------------------------------------------------


@router.post(
    "/users/me/upgrade-group",
    response_model=GroupUpgradeRequestPublic,
    status_code=status.HTTP_201_CREATED,
)
async def submit_upgrade_request(
    session: SessionDep,
    current_user: CurrentUser,
    payload: GroupUpgradeRequestCreate,
) -> GroupUpgradeRequestPublic:
    """Submit a request to move to a PriceGroup that requires validation.

    Only one pending request per group is allowed at a time.
    """
    group = await _load_active_price_group(session, payload.price_group_id)

    if not group.requires_validation:
        raise AppError(
            code="user.upgrade_request.not_required",
            status_code=400,
            message="This price group does not require validation — contact support",
            details={"price_group_id": str(payload.price_group_id)},
        )

    # Capture before the commit below expires the ORM instance (MissingGreenlet).
    user_id = current_user.id

    # Block duplicate pending request for the same group
    dup_stmt = select(GroupUpgradeRequest).where(
        GroupUpgradeRequest.user_id == user_id,
        GroupUpgradeRequest.price_group_id == payload.price_group_id,
        GroupUpgradeRequest.status == UpgradeRequestStatus.pending,
    )
    dup_result = await session.exec(dup_stmt)
    if dup_result.first() is not None:
        raise AppError(
            code="user.upgrade_request.duplicate",
            status_code=409,
            message="A pending request for this group already exists",
            details={
                "user_id": str(user_id),
                "price_group_id": str(payload.price_group_id),
            },
        )

    req = GroupUpgradeRequest(
        user_id=user_id,
        price_group_id=payload.price_group_id,
        business_registration_number=payload.business_registration_number,
        attestation_notes=payload.attestation_notes,
        created_at=datetime.now(timezone.utc),
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    logger.info(
        "Upgrade request submitted: user_id=%s price_group_id=%s",
        user_id,
        payload.price_group_id,
    )
    return GroupUpgradeRequestPublic.model_validate(req)


@router.get("/users/me/upgrade-group", response_model=GroupUpgradeRequestsPublic)
async def list_my_upgrade_requests(
    session: SessionDep,
    current_user: CurrentUser,
) -> GroupUpgradeRequestsPublic:
    """List all upgrade requests submitted by the current user."""
    stmt = (
        select(GroupUpgradeRequest)
        .where(GroupUpgradeRequest.user_id == current_user.id)
        .order_by(col(GroupUpgradeRequest.created_at).desc())
    )
    result = await session.exec(stmt)
    requests = list(result.all())
    return GroupUpgradeRequestsPublic(
        data=[GroupUpgradeRequestPublic.model_validate(r) for r in requests],
        count=len(requests),
    )


class PriceGroupOption(BaseModel):
    """Customer-safe view of a price group (omits the internal margin rate)."""

    id: uuid.UUID
    code: str
    label: str


class UpgradeGroupOptions(BaseModel):
    """Context for the storefront group-upgrade form."""

    current_group: PriceGroupOption | None = None
    available_groups: list[PriceGroupOption] = []


def _as_option(group: PriceGroup) -> PriceGroupOption:
    return PriceGroupOption(id=group.id, code=group.code, label=group.label)


@router.get("/users/me/upgrade-group/options", response_model=UpgradeGroupOptions)
async def get_upgrade_group_options(
    session: SessionDep,
    current_user: CurrentUser,
) -> UpgradeGroupOptions:
    """Return the user's current price group and the groups they may request.

    Requestable groups are active groups flagged ``requires_validation`` (minus
    the current one). Margin rates are intentionally not exposed.
    """
    current: PriceGroup | None = None
    if current_user.price_group_id is not None:
        current = await session.get(PriceGroup, current_user.price_group_id)
    if current is None:
        # Fall back to the default group so the user always sees an effective one.
        default_stmt = select(PriceGroup).where(
            col(PriceGroup.default).is_(True),
            col(PriceGroup.is_active).is_(True),
        )
        current = (await session.exec(default_stmt)).first()

    current_id = current.id if current is not None else None

    avail_stmt = (
        select(PriceGroup)
        .where(
            col(PriceGroup.requires_validation).is_(True),
            col(PriceGroup.is_active).is_(True),
        )
        .order_by(col(PriceGroup.label))
    )
    available = [
        _as_option(g)
        for g in (await session.exec(avail_stmt)).all()
        if g.id != current_id
    ]

    return UpgradeGroupOptions(
        current_group=_as_option(current) if current is not None else None,
        available_groups=available,
    )


# ---------------------------------------------------------------------------
# Admin: list / approve / reject
# ---------------------------------------------------------------------------


@router.get("/admin/group-upgrade-requests", response_model=GroupUpgradeRequestsPublic)
async def list_upgrade_requests_admin(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    pending_only: bool = Query(
        default=True, description="Filter to PENDING requests only"
    ),
    user_id: uuid.UUID | None = Query(default=None),
) -> GroupUpgradeRequestsPublic:
    """List group upgrade requests (admin view)."""
    stmt = select(GroupUpgradeRequest).order_by(
        col(GroupUpgradeRequest.created_at).desc()
    )
    if pending_only:
        stmt = stmt.where(GroupUpgradeRequest.status == UpgradeRequestStatus.pending)
    if user_id:
        stmt = stmt.where(GroupUpgradeRequest.user_id == user_id)

    result = await session.exec(stmt)
    requests = list(result.all())
    return GroupUpgradeRequestsPublic(
        data=[GroupUpgradeRequestPublic.model_validate(r) for r in requests],
        count=len(requests),
    )


class AdminReviewBody(BaseModel):
    """Optional comment when approving or rejecting."""

    comment: str | None = None


@router.post(
    "/admin/group-upgrade-requests/{request_id}/approve",
    response_model=GroupUpgradeRequestPublic,
)
async def approve_upgrade_request(
    request_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentSuperUser,
    payload: AdminReviewBody,
) -> GroupUpgradeRequestPublic:
    """Approve a pending upgrade request and update User.price_group_id."""
    req = await _load_request(session, request_id)

    if req.status != UpgradeRequestStatus.pending:
        raise AppError(
            code="user.upgrade_request.wrong_status",
            status_code=400,
            message="Request is not in PENDING status",
            details={"request_id": str(request_id), "status": req.status},
        )

    # Update the user's price group
    user = await session.get(User, req.user_id)
    if user is None:
        raise AppError(
            code="auth.user.not_found",
            status_code=404,
            message=f"User '{req.user_id}' not found",
            details={"user_id": str(req.user_id)},
        )
    admin_id = current_user.id  # capture before commit (MissingGreenlet)
    user.price_group_id = req.price_group_id
    session.add(user)

    req.status = UpgradeRequestStatus.approved
    req.reviewed_by_id = admin_id
    req.reviewed_at = datetime.now(timezone.utc)
    req.admin_comment = payload.comment
    session.add(req)

    await session.commit()
    await session.refresh(req)
    logger.info(
        "Upgrade request approved: request_id=%s user_id=%s price_group_id=%s admin=%s",
        request_id,
        req.user_id,
        req.price_group_id,
        admin_id,
    )
    return GroupUpgradeRequestPublic.model_validate(req)


@router.post(
    "/admin/group-upgrade-requests/{request_id}/reject",
    response_model=GroupUpgradeRequestPublic,
)
async def reject_upgrade_request(
    request_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentSuperUser,
    payload: AdminReviewBody,
) -> GroupUpgradeRequestPublic:
    """Reject a pending upgrade request."""
    req = await _load_request(session, request_id)

    if req.status != UpgradeRequestStatus.pending:
        raise AppError(
            code="user.upgrade_request.wrong_status",
            status_code=400,
            message="Request is not in PENDING status",
            details={"request_id": str(request_id), "status": req.status},
        )

    admin_id = current_user.id  # capture before commit (MissingGreenlet)
    req.status = UpgradeRequestStatus.rejected
    req.reviewed_by_id = admin_id
    req.reviewed_at = datetime.now(timezone.utc)
    req.admin_comment = payload.comment
    session.add(req)

    await session.commit()
    await session.refresh(req)
    logger.info(
        "Upgrade request rejected: request_id=%s user_id=%s admin=%s",
        request_id,
        req.user_id,
        admin_id,
    )
    return GroupUpgradeRequestPublic.model_validate(req)


# ---------------------------------------------------------------------------
# Admin: direct price-group assignment (bypass workflow)
# ---------------------------------------------------------------------------


class AssignPriceGroupBody(BaseModel):
    """Assign a price group directly to a user."""

    price_group_id: uuid.UUID


@router.post(
    "/admin/users/{user_id}/assign-price-group",
    response_model=Message,
    status_code=status.HTTP_200_OK,
)
async def assign_price_group_to_user(
    user_id: uuid.UUID,
    payload: AssignPriceGroupBody,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> Message:
    """Directly assign a price group to a user (admin bypass, no request created)."""
    await _load_active_price_group(session, payload.price_group_id)

    user = await session.get(User, user_id)
    if user is None:
        raise AppError(
            code="auth.user.not_found",
            status_code=404,
            message=f"User '{user_id}' not found",
            details={"user_id": str(user_id)},
        )

    admin_id = current_user.id  # capture before commit (MissingGreenlet)
    user.price_group_id = payload.price_group_id
    session.add(user)
    await session.commit()
    logger.info(
        "Price group directly assigned: user_id=%s price_group_id=%s admin=%s",
        user_id,
        payload.price_group_id,
        admin_id,
    )
    return Message(message="Price group assigned")
