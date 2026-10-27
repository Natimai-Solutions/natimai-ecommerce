"""Category hierarchy helpers (in memory): ancestors, descendants, paths,
inherited defaults, the cycle guard, and the places that read a lineage."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.features.discount.models import DiscountTarget
from app.features.discount.services.checkout_discount import eligible_lines
from app.features.product.services.category_tree import (
    CategoryCycle,
    ancestor_ids,
    ancestors_map,
    build_tree,
    check_parent,
    depth_of,
    descendant_ids,
    inherited_defaults,
    lineage_ids,
    path_titles,
    subtree_ids,
)
from app.features.product.services.group_pricing import ActivePromotion
from app.features.product.services.spec_projection import _spec_applies_to_category

RESEAU, WIFI, AP, ECRANS = (uuid.uuid4() for _ in range(4))
TAX = uuid.uuid4()


def _row(
    id: uuid.UUID,
    name: str,
    parent: uuid.UUID | None = None,
    **defaults: Any,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        name=name,
        display_name=None,
        parent_id=parent,
        is_active=True,
        merged_into_id=None,
        default_tax_rate_id=defaults.get("tax"),
        default_customs_rate_pct=defaults.get("customs"),
        default_margin_rate_pct=defaults.get("margin"),
    )


def _tree() -> Any:
    return build_tree(
        [
            _row(
                RESEAU, "Réseau", customs=Decimal("12.5"), margin=Decimal("40"), tax=TAX
            ),
            _row(WIFI, "WiFi", RESEAU, margin=Decimal("35")),
            _row(AP, "Point d'accès WiFi", WIFI),
            _row(ECRANS, "Écrans"),
        ]
    )


def test_ancestors_descendants_and_paths() -> None:
    tree = _tree()
    assert ancestor_ids(tree, AP) == [WIFI, RESEAU]
    assert ancestor_ids(tree, RESEAU) == []
    assert lineage_ids(tree, AP) == [AP, WIFI, RESEAU]
    assert descendant_ids(tree, RESEAU) == {WIFI, AP}
    assert subtree_ids(tree, WIFI) == {WIFI, AP}
    assert descendant_ids(tree, ECRANS) == set()
    assert path_titles(tree, AP) == ["Réseau", "WiFi", "Point d'accès WiFi"]
    assert (depth_of(tree, RESEAU), depth_of(tree, WIFI), depth_of(tree, AP)) == (
        0,
        1,
        2,
    )
    assert ancestors_map(tree) == {WIFI: (RESEAU,), AP: (WIFI, RESEAU)}


def test_a_child_inherits_what_its_branch_leaves_unset() -> None:
    tree = _tree()
    leaf = inherited_defaults(tree, AP)
    # Customs and tax come from the root, the margin from the nearest parent.
    assert (leaf.customs_rate_pct, leaf.customs_rate_from) == (Decimal("12.5"), RESEAU)
    assert (leaf.tax_rate_id, leaf.tax_rate_from) == (TAX, RESEAU)
    assert (leaf.margin_rate_pct, leaf.margin_rate_from) == (Decimal("35"), WIFI)
    own = inherited_defaults(tree, RESEAU)
    assert (own.margin_rate_pct, own.margin_rate_from) == (Decimal("40"), RESEAU)
    nothing = inherited_defaults(tree, ECRANS)
    assert nothing.customs_rate_pct is None and nothing.customs_rate_from is None
    assert inherited_defaults(tree, None).customs_rate_pct is None


def test_the_parent_guard_refuses_itself_and_its_descendants() -> None:
    tree = _tree()
    with pytest.raises(CategoryCycle):
        check_parent(tree, RESEAU, RESEAU)
    with pytest.raises(CategoryCycle):
        check_parent(tree, RESEAU, AP)
    check_parent(tree, AP, ECRANS)  # moving a leaf elsewhere is fine
    check_parent(tree, AP, None)


def test_a_cycle_already_in_base_never_hangs() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    tree = build_tree([_row(a, "A", b), _row(b, "B", a)])
    assert ancestor_ids(tree, a) == [b]
    assert descendant_ids(tree, a) == {b}


def test_spec_definitions_scoped_to_an_ancestor_apply_below() -> None:
    scoped = {"category_ids": [str(RESEAU)], "categories": []}
    assert _spec_applies_to_category(scoped, "", [AP, WIFI, RESEAU]) is True
    assert _spec_applies_to_category(scoped, "", AP) is False
    assert _spec_applies_to_category(scoped, "", [ECRANS]) is False
    assert _spec_applies_to_category({"category_ids": [], "categories": []}, "", None)


def test_promotions_and_codes_on_a_category_cover_its_descendants() -> None:
    promotion = ActivePromotion(
        id=uuid.uuid4(),
        name="Réseau -10 %",
        product_id=None,
        category_id=RESEAU,
        percentage=Decimal("10"),
        amount=None,
        end_date=None,
    )
    assert promotion.matches(product_id=uuid.uuid4(), category_id=AP) is False
    assert promotion.matches(
        product_id=uuid.uuid4(), category_id=AP, category_lineage=(AP, WIFI, RESEAU)
    )

    ap_product = SimpleNamespace(id=uuid.uuid4(), category_id=AP)
    screen = SimpleNamespace(id=uuid.uuid4(), category_id=ECRANS)
    items = [
        SimpleNamespace(product_id=ap_product.id),
        SimpleNamespace(product_id=screen.id),
    ]
    products = {ap_product.id: ap_product, screen.id: screen}
    code = SimpleNamespace(
        target=DiscountTarget.CATEGORY, category_id=RESEAU, product_id=None
    )
    assert eligible_lines(code, items, products) == []
    covered = eligible_lines(code, items, products, ancestors_map(_tree()))
    assert [line.product_id for line in covered] == [ap_product.id]
