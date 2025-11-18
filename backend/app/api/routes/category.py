from app.api.base_router import BaseRouter
from app.features.product.crud.category import CategoryCrud, crud_category
from app.features.product.models.category import (
    CategoriesPublic,
    Category,
    CategoryCreate,
    CategoryPublic,
    CategoryUpdate,
)


class CategoryRouter(
    BaseRouter[
        Category,
        CategoryCreate,
        CategoryUpdate,
        CategoryPublic,
        CategoriesPublic,
        CategoryCrud,
    ]
):
    pass


class Auth:
    read = False  # Lecture publique des catégories
    create = True  # Création réservée aux admins
    update = True  # Modification réservée aux admins
    delete = True  # Suppression réservée aux admins


router = CategoryRouter(
    name="category",
    tags=["category"],
    crud=crud_category,
    schema_public=CategoryPublic,
    schema_publics=CategoriesPublic,
    schema_create=CategoryCreate,
    schema_update=CategoryUpdate,
    auth=Auth(),
    auto=True,
)
