"""Unit: which products carry storefront content.

A synced row waits for Icecat (``is_enriched``); a manual product is
publishable as the admin entered it. No database.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.features.product.services.publication import has_storefront_content


def test_synced_product_waits_for_enrichment() -> None:
    assert not has_storefront_content(
        SimpleNamespace(is_enriched=False, is_supplier_managed=True)
    )
    assert has_storefront_content(
        SimpleNamespace(is_enriched=True, is_supplier_managed=True)
    )


def test_manual_product_is_publishable_as_entered() -> None:
    assert has_storefront_content(
        SimpleNamespace(is_enriched=False, is_supplier_managed=False)
    )
