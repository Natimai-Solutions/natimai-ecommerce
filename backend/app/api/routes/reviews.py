"""Customer reviews on the storefront, and their moderation in the admin."""

from __future__ import annotations

import datetime
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from sqlmodel import Field, SQLModel, col, func, select

from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.features.product.models.product import Product
from app.features.user.models.review import Review, ReviewStatus
from app.features.user.models.user import User
from app.features.user.services.reviews import (
    has_bought,
    moderate_review,
    my_review,
    published_reviews,
    review_summary,
    submit_review,
    withdraw_review,
)

router = APIRouter(prefix="/reviews", tags=["review"])


class PublishedReview(SQLModel):
    """A review as the storefront shows it: no e-mail, no account id."""

    id: uuid.UUID
    rating: int
    comment: str | None = None
    author_name: str | None = None
    verified_purchase: bool = False
    created_at: datetime.datetime | None = None


class ReviewSummaryPublic(SQLModel):
    count: int = 0
    average: float | None = None
    #: Number of reviews per star, "1" to "5".
    distribution: dict[str, int] = Field(default_factory=dict)


class ProductReviewsResponse(SQLModel):
    summary: ReviewSummaryPublic
    data: list[PublishedReview] = Field(default_factory=list)


class MyReview(SQLModel):
    """The signed-in customer's own review, whatever its moderation."""

    rating: int
    comment: str | None = None
    status: str
    created_at: datetime.datetime | None = None


class MyReviewState(SQLModel):
    """Whether the signed-in customer may review the product, and their review."""

    can_review: bool = False
    review: MyReview | None = None


class ReviewWrite(SQLModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


def _summary_public(summary: object) -> ReviewSummaryPublic:
    return ReviewSummaryPublic(
        count=getattr(summary, "count", 0),
        average=getattr(summary, "average", None),
        distribution={
            str(star): n for star, n in getattr(summary, "distribution", {}).items()
        },
    )


def _mine(review: Review | None) -> MyReview | None:
    if review is None:
        return None
    return MyReview(
        rating=review.rating,
        comment=review.comment,
        status=review.status,
        created_at=review.created_at,
    )


@router.get("/product/{product_id}", response_model=ProductReviewsResponse)
async def list_published_product_reviews(
    product_id: uuid.UUID,
    session: SessionDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ProductReviewsResponse:
    """The approved reviews of a product, newest first, with their summary."""
    summary = await review_summary(session, product_id)
    reviews = await published_reviews(session, product_id, skip=skip, limit=limit)
    return ProductReviewsResponse(
        summary=_summary_public(summary),
        data=[PublishedReview.model_validate(r, from_attributes=True) for r in reviews],
    )


@router.get("/product/{product_id}/mine", response_model=MyReviewState)
async def get_my_review(
    product_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> MyReviewState:
    user_id = current_user.id
    return MyReviewState(
        can_review=await has_bought(session, user_id=user_id, product_id=product_id),
        review=_mine(await my_review(session, user_id=user_id, product_id=product_id)),
    )


@router.put("/product/{product_id}/mine", response_model=MyReviewState)
async def put_my_review(
    product_id: uuid.UUID,
    payload: ReviewWrite,
    session: SessionDep,
    current_user: CurrentUser,
) -> MyReviewState:
    """Write or edit the review of a product the customer bought (403
    ``review.not_purchased`` otherwise). It waits for moderation."""
    review = await submit_review(
        session,
        user=current_user,
        product_id=product_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    return MyReviewState(can_review=True, review=_mine(review))


@router.delete(
    "/product/{product_id}/mine", status_code=http_status.HTTP_204_NO_CONTENT
)
async def delete_my_review(
    product_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> None:
    await withdraw_review(session, user_id=current_user.id, product_id=product_id)


# -- moderation (admin) -------------------------------------------------------


class ReviewToModerate(SQLModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str | None = None
    author_name: str | None = None
    author_email: str | None = None
    rating: int
    comment: str | None = None
    status: str
    verified_purchase: bool = False
    created_at: datetime.datetime | None = None
    modify_at: datetime.datetime | None = None
    moderated_at: datetime.datetime | None = None
    moderation_note: str | None = None


class ReviewsToModerate(SQLModel):
    data: list[ReviewToModerate] = Field(default_factory=list)
    count: int = 0


class ModerationDecision(SQLModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=300)


@router.get(
    "/admin",
    response_model=ReviewsToModerate,
    dependencies=[Depends(get_current_active_superuser)],
)
async def list_reviews_to_moderate(
    session: SessionDep,
    status: Annotated[ReviewStatus | None, Query()] = ReviewStatus.PENDING,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ReviewsToModerate:
    """Reviews by moderation status (pending by default), oldest first for
    the pending ones, newest first otherwise."""
    conditions: list[Any] = [col(Review.is_active).is_(True)]
    if status is not None:
        conditions.append(col(Review.status) == status.value)
    order = (
        col(Review.created_at).asc().nulls_last()
        if status == ReviewStatus.PENDING
        else col(Review.created_at).desc().nulls_last()
    )
    total = (
        await session.exec(select(func.count()).select_from(Review).where(*conditions))
    ).one()
    rows = (
        await session.exec(
            select(Review, Product.name, User.email)
            .join(Product, col(Product.id) == col(Review.product_id))
            .join(User, col(User.id) == col(Review.user_id))
            .where(*conditions)
            .order_by(order)
            .offset(skip)
            .limit(limit)
        )
    ).all()
    return ReviewsToModerate(
        count=int(total),
        data=[
            ReviewToModerate(
                **review.model_dump(
                    include={
                        "id",
                        "product_id",
                        "author_name",
                        "rating",
                        "comment",
                        "status",
                        "verified_purchase",
                        "created_at",
                        "modify_at",
                        "moderated_at",
                        "moderation_note",
                    }
                ),
                product_name=product_name,
                author_email=email,
            )
            for review, product_name, email in rows
        ],
    )


@router.post("/admin/{review_id}/moderate", response_model=ReviewToModerate)
async def moderate(
    review_id: uuid.UUID,
    payload: ModerationDecision,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_superuser)],
) -> ReviewToModerate:
    """Publish (approve) or reject a review."""
    review = await moderate_review(
        session,
        review_id=review_id,
        approve=payload.decision == "approve",
        moderator_id=current_user.id,
        note=payload.note,
    )
    product = await session.get(Product, review.product_id)
    author = await session.get(User, review.user_id)
    return ReviewToModerate(
        **review.model_dump(
            include={
                "id",
                "product_id",
                "author_name",
                "rating",
                "comment",
                "status",
                "verified_purchase",
                "created_at",
                "modify_at",
                "moderated_at",
                "moderation_note",
            }
        ),
        product_name=product.name if product else None,
        author_email=author.email if author else None,
    )
