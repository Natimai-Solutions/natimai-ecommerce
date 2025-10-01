import uuid

from fastapi import HTTPException, Query, status
from app.api.base_router import BaseRouter
from app.api.deps import SessionDep, CurrentUser
from app.features.user.crud.review import ReviewCrud, crud_review
from app.features.user.models.review import (
    Review,
    ReviewCreate,
    ReviewPublic,
    ReviewsPublic,
    ReviewUpdate,
)


def _check_permission(current_user_id: uuid.UUID, user_id: uuid.UUID, is_admin: bool = False) -> bool:
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
    pass


class Auth:
    read = True
    create = True
    update = True
    delete = True


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
    limit: int = Query(default=100, le=100, ge=1, description="Number of reviews to return")
) -> ReviewsPublic:
    """Get all reviews for a specific user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
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
        raise HTTPException(status_code=403, detail="Not authorized")
    
    review = await crud_review.get(session=session, id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if review.user_id != user_id:
        raise HTTPException(status_code=404, detail="Review not found")
    
    return ReviewPublic.model_validate(review)


@router.post("/users/{user_id}/reviews", response_model=ReviewPublic, status_code=status.HTTP_201_CREATED)
async def create_user_review(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    review_in: ReviewCreate,
) -> ReviewPublic:
    """Create a new review for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check if user already has a review for this product
    existing_review = await crud_review.get_by_user_and_product(
        session=session, user_id=user_id, product_id=review_in.product_id
    )
    if existing_review:
        raise HTTPException(
            status_code=400, 
            detail="User already has a review for this product"
        )
    
    review = await crud_review.create_for_user(
        session=session, obj_in=review_in, user_id=user_id
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
        raise HTTPException(status_code=403, detail="Not authorized")
    
    review = await crud_review.get(session=session, id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if review.user_id != user_id:
        raise HTTPException(status_code=404, detail="Review not found")
    
    review = await crud_review.update(
        session=session, db_obj=review, obj_in=review_in
    )
    return ReviewPublic.model_validate(review)


@router.delete("/users/{user_id}/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_review(
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    review_id: uuid.UUID,
) -> None:
    """Delete a specific review for a user."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    review = await crud_review.get(session=session, id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if review.user_id != user_id:
        raise HTTPException(status_code=404, detail="Review not found")
    
    await crud_review.remove(session=session, id=review_id)


# Product-specific review routes
@router.get("/products/{product_id}/reviews", response_model=ReviewsPublic)
async def get_product_reviews(
    session: SessionDep,
    product_id: uuid.UUID,
    skip: int = Query(default=0, ge=0, description="Number of reviews to skip"),
    limit: int = Query(default=100, le=100, ge=1, description="Number of reviews to return")
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
) -> dict:
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
        "review_count": review_count
    }


@router.get("/products/{product_id}/reviews/user/{user_id}", response_model=ReviewPublic)
async def get_user_review_for_product(
    session: SessionDep,
    current_user: CurrentUser,
    product_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ReviewPublic:
    """Get a user's review for a specific product."""
    if not _check_permission(current_user.id, user_id, current_user.is_superuser):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    review = await crud_review.get_by_user_and_product(
        session=session, user_id=user_id, product_id=product_id
    )
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    return ReviewPublic.model_validate(review)