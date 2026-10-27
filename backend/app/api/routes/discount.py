import uuid

from fastapi import Depends

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep
from app.core.errors import AppError
from app.core.rate_limit import rate_limited
from app.features.discount.crud import DiscountCrud, crud_discount
from app.features.discount.models import (
    Discount,
    DiscountCreate,
    DiscountPublic,
    DiscountsPublic,
    DiscountUpdate,
)


class DiscountRouter(
    BaseRouter[
        Discount,
        DiscountCreate,
        DiscountUpdate,
        DiscountPublic,
        DiscountsPublic,
        DiscountCrud,
    ]
):
    """Represents discount router."""

    pass


class Auth:
    """Superuser-only CRUD: public read allowed enumerating every coupon code.
    Public flows use the dedicated endpoints (/validate-coupon, /promotions/…)
    which only reveal an already-known code or active promotions."""

    read = True
    create = True
    update = True
    delete = True
    read_superuser = True
    create_superuser = True
    update_superuser = True
    delete_superuser = True


router = DiscountRouter(
    name="discount",
    tags=["discount"],
    crud=crud_discount,
    schema_public=DiscountPublic,
    schema_publics=DiscountsPublic,
    schema_create=DiscountCreate,
    schema_update=DiscountUpdate,
    auth=Auth(),
    auto=True,
)


@router.post(
    "/validate-coupon",
    response_model=dict,
    # Signed-in and rate-limited: anonymous and unlimited, it let anyone
    # enumerate the shop's promo codes.
    dependencies=[Depends(rate_limited("coupon", limit=10, window_seconds=60))],
)
async def validate_coupon(
    session: SessionDep,
    _user: CurrentUser,
    code: str,
) -> dict[str, object]:
    """
    Valider un code coupon.
    Retourne les informations du coupon si valide.
    """
    is_valid, message, discount = await crud_discount.validate_coupon(session, code)

    if not is_valid:
        raise AppError(
            code="discount.coupon.invalid",
            status_code=400,
            message=message,
            details={
                "coupon_code": code,
                "reason": message,
            },
        )

    return {
        "valid": True,
        "message": message,
        "discount": DiscountPublic.model_validate(discount),
    }


@router.get("/promotions/product/{product_id}", response_model=list[DiscountPublic])
async def get_product_promotions(
    session: SessionDep,
    product_id: uuid.UUID,
) -> list[DiscountPublic]:
    """Get product promotions."""
    promotions = await crud_discount.get_active_promotions(
        session=session, product_id=product_id
    )
    return [DiscountPublic.model_validate(promo) for promo in promotions]


@router.get("/promotions/category/{category_id}", response_model=list[DiscountPublic])
async def get_category_promotions(
    session: SessionDep,
    category_id: uuid.UUID,
) -> list[DiscountPublic]:
    """Get category promotions."""
    promotions = await crud_discount.get_active_promotions(
        session=session, category_id=category_id
    )
    return [DiscountPublic.model_validate(promo) for promo in promotions]


@router.post("/{discount_id}/use", response_model=DiscountPublic)
async def use_discount(
    session: SessionDep,
    discount_id: uuid.UUID,
    current_user: CurrentUser,
) -> DiscountPublic:
    """Increment a discount's usage counter (admin/server flows only).

    Left open, any customer could exhaust a coupon's max_uses on purpose.
    """
    if not current_user.is_superuser:
        raise AppError(
            code="discount.admin_required",
            status_code=403,
            message="Admin privileges required to consume a discount usage",
            details={"discount_id": str(discount_id)},
        )
    discount = await crud_discount.increment_usage(session, discount_id)
    if not discount:
        raise AppError(
            code="discount.not_found",
            status_code=404,
            message="Réduction non trouvée",
            details={"discount_id": str(discount_id)},
        )
    return DiscountPublic.model_validate(discount)
