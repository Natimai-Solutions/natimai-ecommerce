import uuid
from typing import Any

from fastapi import Depends, Query

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep, get_current_user_optional
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.place.crud import PostalCodeConflictError, crud_place
from app.features.place.models import (
    Place,
    PlaceCreate,
    PlacePostalCodesUpdate,
    PlacePublic,
    PlaceResolveResponse,
    PlacesPublic,
    PlaceTreeResponse,
    PlaceUpdate,
    PostalCodeDirectoryEntry,
    PostalCodeDirectoryResponse,
)


class PlaceRouter(
    BaseRouter[
        Place,
        PlaceCreate,
        PlaceUpdate,
        PlacePublic,
        PlacesPublic,
        Any,
    ]
):
    """Place CRUD plus geographic-zone endpoints (tree, postal resolution)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the place router instance."""
        super().__init__(*args, **kwargs)
        self.add_geo_endpoints()

    def add_geo_endpoints(self) -> None:
        """Register the geographic-zone endpoints.

        Paths are shaped to avoid colliding with the auto-generated ``/{id}``
        CRUD routes (Starlette matches in registration order).
        """

        @self.get(
            "/geo/tree",
            response_model=PlaceTreeResponse,
            summary="Geographic zone tree",
            description=(
                "Arbre des zones géographiques (pays → région/archipel → île "
                "→ commune) pour les sélecteurs en cascade. Les nœuds "
                "opérationnels (entrepôts, boutiques...) sont exclus."
            ),
        )
        async def get_geo_tree(
            session: SessionDep,
            country: str | None = Query(
                None, min_length=2, max_length=2, description="Filtre pays ISO"
            ),
            _current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> PlaceTreeResponse:
            """Return the nested geographic zone tree."""
            roots = await crud_place.get_geo_tree(
                session,
                country=country.upper() if country else None,
            )
            return PlaceTreeResponse(roots=roots)

        @self.get(
            "/geo/postal-codes",
            response_model=PostalCodeDirectoryResponse,
            summary="Postal code directory of a country",
            description=(
                "Tous les codes postaux enregistrés d'un pays avec leur zone "
                "(île, commune...). Alimente l'autocomplete du formulaire "
                "d'adresse — sélectionner un code = sélectionner sa zone."
            ),
        )
        async def list_postal_codes(
            session: SessionDep,
            country: str = Query(..., min_length=2, max_length=2),
            _current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> PostalCodeDirectoryResponse:
            """List every registered postal code of a country with its zone."""
            normalized = country.upper()
            rows = await crud_place.list_postal_codes_by_country(
                session, country=normalized
            )
            return PostalCodeDirectoryResponse(
                country=normalized,
                entries=[
                    PostalCodeDirectoryEntry(
                        postal_code=code.postal_code,
                        place_id=place.id,
                        place_name=place.name,
                        place_type=place.type,
                    )
                    for code, place in rows
                ],
            )

        @self.get(
            "/geo/resolve-postal",
            response_model=PlaceResolveResponse,
            summary="Resolve a postal code to its zone",
            description=(
                "Déduit la zone (île, commune...) d'un code postal exact. "
                "Renvoie place=null si le code postal est inconnu."
            ),
        )
        async def resolve_postal_code(
            session: SessionDep,
            country: str = Query(..., min_length=2, max_length=2),
            postal_code: str = Query(..., min_length=1, max_length=20),
            _current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> PlaceResolveResponse:
            """Resolve a postal code to its geographic zone."""
            place = await crud_place.resolve_by_postal_code(
                session, country=country, postal_code=postal_code
            )
            if place is None:
                return PlaceResolveResponse(place=None, ancestors=[])
            ancestors = await crud_place.get_ancestor_chain(
                session, place_id=place.id, include_self=False
            )
            return PlaceResolveResponse(
                place=PlacePublic.model_validate(place),
                ancestors=[PlacePublic.model_validate(item) for item in ancestors],
            )

        @self.get(
            "/{id}/postal-codes",
            response_model=list[str],
            summary="Postal codes of a place",
        )
        async def get_place_postal_codes(
            session: SessionDep,
            id: uuid.UUID,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> list[str]:
            """List the postal codes attached to a place."""
            await self._check_auth(session, "read", current_user)
            rows = await crud_place.get_postal_codes(session, place_id=id)
            return [row.postal_code for row in rows]

        @self.put(
            "/{id}/postal-codes",
            response_model=list[str],
            summary="Replace the postal codes of a place",
        )
        async def set_place_postal_codes(
            session: SessionDep,
            id: uuid.UUID,
            payload: PlacePostalCodesUpdate,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> list[str]:
            """Replace the full set of postal codes attached to a place."""
            await self._check_auth(session, "update", current_user)
            try:
                await crud_place.read(session, id=id)
            except RecordNotFoundError as exc:
                raise AppError(
                    code="resource.not_found",
                    status_code=404,
                    message="Place not found",
                    details={"id": str(id)},
                ) from exc
            try:
                rows = await crud_place.set_postal_codes(
                    session,
                    place_id=id,
                    country=payload.country,
                    postal_codes=payload.postal_codes,
                )
            except PostalCodeConflictError as exc:
                raise AppError(
                    code="place.postal_code.conflict",
                    status_code=409,
                    message=(
                        "Postal code(s) already mapped to another place: "
                        + ", ".join(exc.postal_codes)
                    ),
                    details={"postal_codes": exc.postal_codes},
                ) from exc
            # Capture before commit: committing expires the ORM instances and a
            # later attribute read would sync-lazy-load → MissingGreenlet.
            codes = [row.postal_code for row in rows]
            await session.commit()
            return codes


class Auth:
    """Represents auth."""

    read = True
    create = True
    update = True
    delete = True


router = PlaceRouter(
    name="place",
    tags=["place"],
    crud=crud_place,
    schema_public=PlacePublic,
    schema_publics=PlacesPublic,
    schema_create=PlaceCreate,
    schema_update=PlaceUpdate,
    auth=Auth(),
    auto=True,
)
