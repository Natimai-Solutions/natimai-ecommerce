"""Regression: category_id must be carried by the product create/update schemas.

The field is declared on the table model and ProductPublic, but used to be
missing from ProductCreate / ProductUpdate — so the supplier sync's
``ProductUpdate(category_id=...)`` was silently dropped and products kept
``category_id = None`` (breaking the storefront category filter).
"""

import uuid

from app.features.product.models.product import ProductCreate, ProductUpdate


def test_product_update_carries_category_id() -> None:
    cid = uuid.uuid4()
    dumped = ProductUpdate(category_id=cid).model_dump(exclude_unset=True)
    assert dumped.get("category_id") == cid


def test_product_update_without_category_id_does_not_emit_it() -> None:
    # When the supplier item has no subcategory, category_id must not be set
    # (exclude_unset) so an existing value is never wiped on re-sync.
    dumped = ProductUpdate(name="Foo").model_dump(exclude_unset=True)
    assert "category_id" not in dumped


def test_product_create_carries_category_id() -> None:
    cid = uuid.uuid4()
    dumped = ProductCreate(name="Test", category_id=cid).model_dump()
    assert dumped.get("category_id") == cid
