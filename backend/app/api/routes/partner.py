from typing import Any

from app.api.base_router import BaseRouter
from app.features.partner.crud import crud_partner
from app.features.partner.models import (
    Partner,
    PartnerCreate,
    PartnerPublic,
    PartnersPublic,
    PartnerUpdate,
)


class PartnerRouter(
    BaseRouter[
        Partner,
        PartnerCreate,
        PartnerUpdate,
        PartnerPublic,
        PartnersPublic,
        Any,
    ]
):
    """Represents partner router."""

    pass


class Auth:
    """Represents auth."""

    read = True
    create = True
    update = True
    delete = True


router = PartnerRouter(
    name="partner",
    tags=["partner"],
    crud=crud_partner,
    schema_public=PartnerPublic,
    schema_publics=PartnersPublic,
    schema_create=PartnerCreate,
    schema_update=PartnerUpdate,
    auth=Auth(),
    auto=True,
)
