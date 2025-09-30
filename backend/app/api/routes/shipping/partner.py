from app.api.base_router import BaseRouter
from app.features.shipping.crud import crud_partner
from app.features.shipping.models.partner import (
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
        type(crud_partner),
    ]
):
    pass


class Auth:
    read = True
    create = True
    update = True
    delete = True


router = PartnerRouter(
    name="partner",
    tags=["shipping", "partner"],
    crud=crud_partner,
    schema_public=PartnerPublic,
    schema_publics=PartnersPublic,
    schema_create=PartnerCreate,
    schema_update=PartnerUpdate,
    auth=Auth(),
    auto=True,
)