"""Customer reviews: written by buyers, published once the shop approves them.

* Only a customer who **bought** the product (an order of theirs that holds
  it, or one of its variants, and that money settled) may write a review; it
  carries ``verified_purchase``.
* One review per customer and product: writing again edits it, and an edited
  review goes back to moderation.
* Nothing is shown before the shop approves it (``status``); the storefront
  reads the approved ones and their summary (average, count, distribution).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.product.models.product import Product
from app.features.user.models.review import Review, ReviewStatus
from app.features.user.models.user import User

#: Order statuses in which the customer has paid for what they ordered.
PURCHASED_ORDER_STATUSES: frozenset[str] = frozenset(
    {
        "Paid",
        "DepositPaid",
        "PartiallyRefunded",
        "OrderedFromSupplier",
        "InTransit",
        "AtCustoms",
        "Received",
        "ReadyForPickup",
        "Delivered",
    }
)


def author_label(user: User) -> str:
    """« Hina T. »: first name and initial, never the e-mail."""
    parts = (user.full_name or "").split()
    if not parts:
        return "Client"
    if len(parts) == 1:
        return parts[0][:40]
    return f"{parts[0][:40]} {parts[-1][0].upper()}."


async def has_bought(
    session: AsyncSession, *, user_id: uuid.UUID, product_id: uuid.UUID
) -> bool:
    """The customer has a paid order holding the product or one of its variants."""
    bought = (
        select(OrderLine.id)
        .join(Order, col(Order.id) == col(OrderLine.order_id))
        .join(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
        .join(Product, col(Product.id) == col(OrderLine.product_id))
        .where(
            col(Order.user_id) == user_id,
            col(OrderStatus.name).in_(PURCHASED_ORDER_STATUSES),
            col(OrderLine.is_active).is_(True),
            or_(
                col(OrderLine.product_id) == product_id,
                col(Product.parent_product_id) == product_id,
            ),
        )
        .limit(1)
    )
    return (await session.exec(bought)).first() is not None


async def my_review(
    session: AsyncSession, *, user_id: uuid.UUID, product_id: uuid.UUID
) -> Review | None:
    return (
        await session.exec(
            select(Review).where(
                col(Review.user_id) == user_id,
                col(Review.product_id) == product_id,
                col(Review.is_active).is_(True),
            )
        )
    ).first()


async def submit_review(
    session: AsyncSession,
    *,
    user: User,
    product_id: uuid.UUID,
    rating: int,
    comment: str | None,
) -> Review:
    """Write or edit the customer's review of a product they bought; commits.

    The review (new or edited) waits for the shop's moderation.
    """
    user_id = user.id
    if not await has_bought(session, user_id=user_id, product_id=product_id):
        raise AppError(
            code="review.not_purchased",
            status_code=403,
            message="Only a customer who bought this product can review it",
            details={"product_id": str(product_id)},
        )
    text = (comment or "").strip() or None
    review = await my_review(session, user_id=user_id, product_id=product_id)
    if review is None:
        review = Review(
            product_id=product_id,
            user_id=user_id,
            rating=rating,
            comment=text,
            created_by_id=user_id,
            created_at=datetime.now(UTC),
        )
    else:
        review.rating = rating
        review.comment = text
        review.modify_by_id = user_id
        review.modify_at = datetime.now(UTC)
    review.status = ReviewStatus.PENDING.value
    review.verified_purchase = True
    review.author_name = author_label(user)
    review.moderated_at = None
    review.moderated_by_id = None
    review.moderation_note = None
    session.add(review)
    await session.commit()
    await session.refresh(review)
    return review


async def withdraw_review(
    session: AsyncSession, *, user_id: uuid.UUID, product_id: uuid.UUID
) -> bool:
    """The customer removes their review; commits. False when there was none."""
    review = await my_review(session, user_id=user_id, product_id=product_id)
    if review is None:
        return False
    review.is_active = False
    session.add(review)
    await session.commit()
    return True


@dataclass
class ReviewSummary:
    """Approved reviews of a product at a glance."""

    count: int = 0
    average: float | None = None
    #: How many reviews gave 1, 2, 3, 4 and 5 stars.
    distribution: dict[int, int] = field(
        default_factory=lambda: dict.fromkeys(range(1, 6), 0)
    )


def _published(product_id: uuid.UUID) -> list[Any]:
    return [
        col(Review.product_id) == product_id,
        col(Review.status) == ReviewStatus.APPROVED.value,
        col(Review.is_active).is_(True),
        col(Review.is_admin_active).is_(True),
    ]


async def review_summary(session: AsyncSession, product_id: uuid.UUID) -> ReviewSummary:
    rows = (
        await session.exec(
            select(Review.rating, func.count())
            .where(*_published(product_id))
            .group_by(col(Review.rating))
        )
    ).all()
    summary = ReviewSummary()
    total = 0
    for rating, count in rows:
        summary.distribution[int(rating)] = int(count)
        summary.count += int(count)
        total += int(rating) * int(count)
    if summary.count:
        summary.average = round(total / summary.count, 1)
    return summary


async def published_reviews(
    session: AsyncSession, product_id: uuid.UUID, *, skip: int = 0, limit: int = 10
) -> list[Review]:
    return list(
        (
            await session.exec(
                select(Review)
                .where(*_published(product_id))
                .order_by(col(Review.created_at).desc().nulls_last())
                .offset(skip)
                .limit(limit)
            )
        ).all()
    )


async def moderate_review(
    session: AsyncSession,
    *,
    review_id: uuid.UUID,
    approve: bool,
    moderator_id: uuid.UUID,
    note: str | None = None,
) -> Review:
    """The shop publishes or rejects a review; commits."""
    review = await session.get(Review, review_id)
    if review is None or not review.is_active:
        raise AppError(
            code="review.not_found",
            status_code=404,
            message=f"Review '{review_id}' not found",
            details={"review_id": str(review_id)},
        )
    review.status = (ReviewStatus.APPROVED if approve else ReviewStatus.REJECTED).value
    review.moderated_at = datetime.now(UTC)
    review.moderated_by_id = moderator_id
    review.moderation_note = None if approve else ((note or "").strip() or None)
    session.add(review)
    await session.commit()
    await session.refresh(review)
    return review
