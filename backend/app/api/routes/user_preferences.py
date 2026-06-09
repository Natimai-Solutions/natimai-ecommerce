from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.core.errors import AppError
from app.features.user.crud.user_preference import (
    get_preference_for_user,
    upsert_preference_for_user,
)
from app.features.user.models.user_preference import (
    _VALID_LOCALES,
    _VALID_SHIPPING_MODES,
    _VALID_SHIPPING_PREFERENCES,
    UserPreferencePublic,
    UserPreferenceUpdate,
)

router = APIRouter(prefix="/users/me/preferences", tags=["user"])

_VALID_CURRENCIES = {"XPF", "USD", "EUR"}


def _validate_update(data: UserPreferenceUpdate) -> None:
    """Raise AppError on invalid enum-like string fields."""
    if (
        data.default_shipping_preference is not None
        and data.default_shipping_preference not in _VALID_SHIPPING_PREFERENCES
    ):
        raise AppError(
            code="user.preference.invalid",
            status_code=400,
            message="Invalid default_shipping_preference",
            details={
                "field": "default_shipping_preference",
                "value": data.default_shipping_preference,
                "allowed": sorted(_VALID_SHIPPING_PREFERENCES),
            },
        )
    if (
        data.preferred_shipping_mode is not None
        and data.preferred_shipping_mode not in _VALID_SHIPPING_MODES
    ):
        raise AppError(
            code="user.preference.invalid",
            status_code=400,
            message="Invalid preferred_shipping_mode",
            details={
                "field": "preferred_shipping_mode",
                "value": data.preferred_shipping_mode,
                "allowed": sorted(_VALID_SHIPPING_MODES),
            },
        )
    if data.locale is not None and data.locale not in _VALID_LOCALES:
        raise AppError(
            code="user.preference.invalid",
            status_code=400,
            message="Invalid locale",
            details={
                "field": "locale",
                "value": data.locale,
                "allowed": sorted(_VALID_LOCALES),
            },
        )
    if data.currency_pref is not None and data.currency_pref not in _VALID_CURRENCIES:
        raise AppError(
            code="user.preference.invalid",
            status_code=400,
            message="Invalid currency_pref",
            details={
                "field": "currency_pref",
                "value": data.currency_pref,
                "allowed": sorted(_VALID_CURRENCIES),
            },
        )


@router.get("", response_model=UserPreferencePublic)
async def get_my_preferences(
    session: SessionDep,
    current_user: CurrentUser,
) -> UserPreferencePublic:
    """Return the current user's preferences (defaults if none saved yet)."""
    pref = await get_preference_for_user(session, user_id=current_user.id)
    if pref is None:
        return UserPreferencePublic(user_id=current_user.id)
    return UserPreferencePublic.model_validate(pref)


@router.put("", response_model=UserPreferencePublic)
async def update_my_preferences(
    session: SessionDep,
    current_user: CurrentUser,
    data: UserPreferenceUpdate,
) -> UserPreferencePublic:
    """Create or partially update the current user's preferences."""
    _validate_update(data)
    pref = await upsert_preference_for_user(session, user_id=current_user.id, data=data)
    await session.commit()
    await session.refresh(pref)
    return UserPreferencePublic.model_validate(pref)
