"""Public lists never carry an account id (audit 2026-11)."""

from app.api.routes.user_review import get_product_reviews
from app.api.routes.user_wishlist import get_public_wishlists
from app.features.user.models.review import ReviewAnonymousPublic
from app.features.user.models.wishlist import WishlistAnonymousPublic

_ACCOUNT_FIELDS = {"user_id", "created_by_id", "modify_by_id"}


def test_public_reviews_and_wishlists_hide_who_wrote_them() -> None:
    assert not _ACCOUNT_FIELDS & set(ReviewAnonymousPublic.model_fields)
    assert not _ACCOUNT_FIELDS & set(WishlistAnonymousPublic.model_fields)
    for route in (get_product_reviews, get_public_wishlists):
        returned = route.__annotations__["return"]
        assert "Anonymous" in str(returned)
