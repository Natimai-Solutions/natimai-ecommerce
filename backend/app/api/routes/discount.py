import uuid

from fastapi import HTTPException, status

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep
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
    """Represents auth."""

    read = False  # Lecture publique pour valider les coupons
    create = True  # Création réservée aux admins
    update = True  # Modification réservée aux admins
    delete = True  # Suppression réservée aux admins


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


@router.post("/validate-coupon", response_model=dict)
async def validate_coupon(
    session: SessionDep,
    code: str,
) -> dict[str, object]:
    """
    Valider un code coupon.
    Retourne les informations du coupon si valide.
    """
    is_valid, message, discount = await crud_discount.validate_coupon(session, code)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
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
    _current_user: CurrentUser,
) -> DiscountPublic:
    """Execute use discount."""
    discount = await crud_discount.increment_usage(session, discount_id)
    if not discount:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Réduction non trouvée",
        )
    return DiscountPublic.model_validate(discount)
