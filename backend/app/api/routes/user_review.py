import uuid

from fastapi import Query, status

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.user.crud.review import ReviewCrud, crud_review
from app.features.user.models.review import (
    Review,
    ReviewCreate,
    ReviewPublic,
    ReviewsPublic,
    ReviewUpdate,
)


def _check_permission(
    current_user_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False
) -> bool:
    """Check if current user can access resource for given user_id."""
    return current_user_id == user_id or is_admin


class ReviewRouter(
    BaseRouter[
        Review,
        ReviewCreate,
        ReviewUpdate,
        ReviewPublic,
        ReviewsPublic,
        ReviewCrud,
    ]
):
    """Represents review router."""

    pass


class Auth:
    """Generic CRUD writes are superuser-only (no ownership check on /{id}).
    Customers create/edit their reviews via the ownership-checked
    /users/{user_id}/reviews endpoints; product reviews are read publicly via
    /products/{product_id}/reviews."""

    read = True
    create = True
    update = True
    delete = True
    create_superuser = True
    update_superuser = True
    delete_superuser = True


router = ReviewRouter(
    name="review",
    tags=["review"],
    crud=crud_review,
    schema_public=ReviewPublic,
    schema_publics=ReviewsPublic,
    schema_create=ReviewCreate,
    schema_update=ReviewUpdate,
    auth=Auth(),
    auto=True,
)


# User-specific review routes
@router.get("/users/{user_id}/reviews", response_model=ReviewsPublic)
async def get_user_reviews(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    skip: int = Query(default=0, ge=0, description="Number of reviews to skip"),
    limit: int = Query(
        default=100, le=100, ge=1, description="Number of reviews to return"
    ),
) -> ReviewsPublic:
    """Get all reviews for a specific user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise AppError(
            code="review.not_owned",
            status_code=403,
            message="You cannot access another user's reviews",
            details={"user_id": str(user_id)},
        )

    reviews = await crud_review.get_by_user_id(
        session=session, user_id=user_id, skip=skip, limit=limit
    )
    count = await crud_review.count_by_user(session=session, user_id=user_id)

    return ReviewsPublic(data=reviews, count=count)


@router.get("/users/{user_id}/reviews/{review_id}", response_model=ReviewPublic)
async def get_user_review(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    review_id: uuid.UUID,
) -> ReviewPublic:
    """Get a specific review for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise AppError(
            code="review.not_owned",
            status_code=403,
            message="You cannot access another user's reviews",
            details={"user_id": str(user_id)},
        )

    try:
        review = await crud_review.read(session=session, id=review_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="review.not_found",
            status_code=404,
            message=f"Review '{review_id}' not found",
            details={"review_id": str(review_id)},
        ) from exc

    if review.user_id != user_id:
        raise AppError(
            code="review.not_found",
            status_code=404,
            message=f"Review '{review_id}' not found",
            details={"review_id": str(review_id)},
        )

    return ReviewPublic.model_validate(review)


@router.post(
    "/users/{user_id}/reviews",
    response_model=ReviewPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_review(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    review_in: ReviewCreate,
) -> ReviewPublic:
    """Create a new review for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise AppError(
            code="review.not_owned",
            status_code=403,
            message="You cannot access another user's reviews",
            details={"user_id": str(user_id)},
        )

    # Check if user already has a review for this product
    existing_review = await crud_review.get_by_user_and_product(
        session=session, user_id=user_id, product_id=review_in.product_id
    )
    if existing_review:
        raise AppError(
            code="review.already_exists",
            status_code=400,
            message="User already has a review for this product",
            details={
                "user_id": str(user_id),
                "product_id": str(review_in.product_id),
            },
        )

    review = await crud_review.create_for_user(
        session=session, data=review_in, user_id=user_id
    )
    return ReviewPublic.model_validate(review)


@router.patch("/users/{user_id}/reviews/{review_id}", response_model=ReviewPublic)
async def update_user_review(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    review_id: uuid.UUID,
    review_in: ReviewUpdate,
) -> ReviewPublic:
    """Update a specific review for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise AppError(
            code="review.not_owned",
            status_code=403,
            message="You cannot access another user's reviews",
            details={"user_id": str(user_id)},
        )

    try:
        review = await crud_review.read(session=session, id=review_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="review.not_found",
            status_code=404,
            message=f"Review '{review_id}' not found",
            details={"review_id": str(review_id)},
        ) from exc

    if review.user_id != user_id:
        raise AppError(
            code="review.not_found",
            status_code=404,
            message=f"Review '{review_id}' not found",
            details={"review_id": str(review_id)},
        )

    review = await crud_review.update(
        session=session,
        id=review_id,
        record=review,
        data=review_in,
    )
    return ReviewPublic.model_validate(review)


@router.delete(
    "/users/{user_id}/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_user_review(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    review_id: uuid.UUID,
) -> None:
    """Delete a specific review for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise AppError(
            code="review.not_owned",
            status_code=403,
            message="You cannot access another user's reviews",
            details={"user_id": str(user_id)},
        )

    try:
        review = await crud_review.read(session=session, id=review_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="review.not_found",
            status_code=404,
            message=f"Review '{review_id}' not found",
            details={"review_id": str(review_id)},
        ) from exc

    if review.user_id != user_id:
        raise AppError(
            code="review.not_found",
            status_code=404,
            message=f"Review '{review_id}' not found",
            details={"review_id": str(review_id)},
        )

    await crud_review.delete(session=session, id=review_id, record=review)


# Product-specific review routes
@router.get("/products/{product_id}/reviews", response_model=ReviewsPublic)
async def get_product_reviews(
    session: SessionDep,
    product_id: uuid.UUID,
    skip: int = Query(default=0, ge=0, description="Number of reviews to skip"),
    limit: int = Query(
        default=100, le=100, ge=1, description="Number of reviews to return"
    ),
) -> ReviewsPublic:
    """Get all reviews for a specific product."""
    reviews = await crud_review.get_by_product_id(
        session=session, product_id=product_id, skip=skip, limit=limit
    )
    count = await crud_review.count_by_product(session=session, product_id=product_id)

    return ReviewsPublic(data=reviews, count=count)


@router.get("/products/{product_id}/reviews/average")
async def get_product_review_average(
    session: SessionDep,
    product_id: uuid.UUID,
) -> dict[str, object]:
    """Get average rating for a specific product."""
    average_rating = await crud_review.get_average_rating_by_product(
        session=session, product_id=product_id
    )
    review_count = await crud_review.count_by_product(
        session=session, product_id=product_id
    )

    return {
        "product_id": product_id,
        "average_rating": average_rating,
        "review_count": review_count,
    }


@router.get(
    "/products/{product_id}/reviews/user/{user_id}", response_model=ReviewPublic
)
async def get_user_review_for_product(
    session: SessionDep,
    current_user: CurrentUser,
    product_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ReviewPublic:
    """Get a user's review for a specific product."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise AppError(
            code="review.not_owned",
            status_code=403,
            message="You cannot access another user's reviews",
            details={"user_id": str(user_id)},
        )

    review = await crud_review.get_by_user_and_product(
        session=session, user_id=user_id, product_id=product_id
    )
    if not review:
        raise AppError(
            code="review.not_found",
            status_code=404,
            message="Review not found for this user and product",
            details={
                "user_id": str(user_id),
                "product_id": str(product_id),
            },
        )

    return ReviewPublic.model_validate(review)
