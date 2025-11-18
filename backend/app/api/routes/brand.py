from app.api.base_router import BaseRouter
from app.features.product.crud.brand import BrandCrud, crud_brand
from app.features.product.models.brand import (
    Brand,
    BrandCreate,
    BrandPublic,
    BrandsPublic,
    BrandUpdate,
)


class BrandRouter(
    BaseRouter[
        Brand,
        BrandCreate,
        BrandUpdate,
        BrandPublic,
        BrandsPublic,
        BrandCrud,
    ]
):
    pass


class Auth:
    read = False  # Lecture publique des marques
    create = True  # Création réservée aux admins
    update = True  # Modification réservée aux admins
    delete = True  # Suppression réservée aux admins


router = BrandRouter(
    name="brand",
    tags=["brand"],
    crud=crud_brand,
    schema_public=BrandPublic,
    schema_publics=BrandsPublic,
    schema_create=BrandCreate,
    schema_update=BrandUpdate,
    auth=Auth(),
    auto=True,
)
