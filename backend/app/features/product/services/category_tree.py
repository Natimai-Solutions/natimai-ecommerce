"""Category hierarchy: « Réseau > WiFi > Point d'accès WiFi ».

A category may have a parent (``Category.parent_id``). Two things follow:

* **inheritance** — a default the child leaves unset (tax rate, customs
  rate, margin; later an accounting account…) is its nearest ancestor's.
  :func:`inherited_defaults` resolves it in memory for the pricing context
  and the admin screen; :func:`inherited_customs_rate_subquery` is the SQL
  twin the publication gate reads;
* **navigation** — the storefront lists a category with its descendants'
  products. :func:`descendant_ids` (Python) and
  :func:`subtree_ids_select` (SQL) give the ids a listing must cover.

The whole tree is a few dozen rows: it is loaded in one query and walked
in memory wherever a session is at hand. Depth is bounded (``MAX_DEPTH``)
so a cycle a bug could have written never hangs a request; the admin route
refuses to create one.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import literal
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.category import Category
from app.features.product.models.product import Product

#: Deepest chain followed, parent after parent (a guard, not a design limit).
MAX_DEPTH = 32


class CategoryCycle(ValueError):
    """Setting this parent would make the category its own ancestor."""


@dataclass(frozen=True)
class CategoryNode:
    """What the tree helpers read of a category, detached from the ORM."""

    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    title: str
    is_active: bool
    merged_into_id: uuid.UUID | None
    default_tax_rate_id: uuid.UUID | None
    default_customs_rate_pct: Decimal | None
    default_margin_rate_pct: Decimal | None


@dataclass(frozen=True)
class InheritedDefaults:
    """The defaults in force for a category: its own, else an ancestor's.

    ``*_from`` names the category the value comes from (``None`` when
    nothing in the chain sets it).
    """

    tax_rate_id: uuid.UUID | None = None
    tax_rate_from: uuid.UUID | None = None
    customs_rate_pct: Decimal | None = None
    customs_rate_from: uuid.UUID | None = None
    margin_rate_pct: Decimal | None = None
    margin_rate_from: uuid.UUID | None = None


Tree = dict[uuid.UUID, CategoryNode]


def _node(row: Any) -> CategoryNode:
    return CategoryNode(
        id=row.id,
        parent_id=getattr(row, "parent_id", None),
        name=str(getattr(row, "name", "") or ""),
        title=str(getattr(row, "display_name", None) or getattr(row, "name", "")),
        is_active=bool(getattr(row, "is_active", True)),
        merged_into_id=getattr(row, "merged_into_id", None),
        default_tax_rate_id=getattr(row, "default_tax_rate_id", None),
        default_customs_rate_pct=(
            Decimal(str(row.default_customs_rate_pct))
            if getattr(row, "default_customs_rate_pct", None) is not None
            else None
        ),
        default_margin_rate_pct=(
            Decimal(str(row.default_margin_rate_pct))
            if getattr(row, "default_margin_rate_pct", None) is not None
            else None
        ),
    )


def build_tree(rows: Iterable[Any]) -> Tree:
    """The tree from category rows (ORM rows or look-alikes)."""
    return {row.id: _node(row) for row in rows}


async def load_tree(session: AsyncSession) -> Tree:
    """Every category, merged and inactive ones included (they may still be
    the parent an active child inherits from)."""
    rows = (await session.exec(select(Category))).all()
    return build_tree(rows)


def ancestor_ids(tree: Tree, category_id: uuid.UUID | None) -> list[uuid.UUID]:
    """The parents of a category, nearest first (empty for a root)."""
    out: list[uuid.UUID] = []
    seen = {category_id}
    node = tree.get(category_id) if category_id is not None else None
    while node is not None and node.parent_id is not None:
        if node.parent_id in seen or len(out) >= MAX_DEPTH:
            break
        out.append(node.parent_id)
        seen.add(node.parent_id)
        node = tree.get(node.parent_id)
    return out


def lineage_ids(tree: Tree, category_id: uuid.UUID | None) -> list[uuid.UUID]:
    """The category itself, then its ancestors nearest first."""
    if category_id is None:
        return []
    return [category_id, *ancestor_ids(tree, category_id)]


def descendant_ids(tree: Tree, category_id: uuid.UUID) -> set[uuid.UUID]:
    """Every category below ``category_id`` (itself excluded), any depth."""
    children: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for node in tree.values():
        children.setdefault(node.parent_id, []).append(node.id)
    out: set[uuid.UUID] = set()
    frontier = [category_id]
    while frontier:
        current = frontier.pop()
        for child in children.get(current, []):
            if child not in out and child != category_id:
                out.add(child)
                frontier.append(child)
    return out


def subtree_ids(tree: Tree, category_id: uuid.UUID) -> set[uuid.UUID]:
    """``category_id`` and every category below it."""
    return {category_id, *descendant_ids(tree, category_id)}


def path_titles(tree: Tree, category_id: uuid.UUID) -> list[str]:
    """Titles from the root down to the category: ``["Réseau", "WiFi"]``."""
    titles = [
        tree[c].title for c in reversed(ancestor_ids(tree, category_id)) if c in tree
    ]
    node = tree.get(category_id)
    if node is not None:
        titles.append(node.title)
    return titles


def depth_of(tree: Tree, category_id: uuid.UUID) -> int:
    """0 for a root, 1 for its children…"""
    return len(ancestor_ids(tree, category_id))


def inherited_defaults(tree: Tree, category_id: uuid.UUID | None) -> InheritedDefaults:
    """The defaults in force for a category: own value first, else the
    nearest ancestor's. A merged or inactive ancestor still counts: the
    admin set the value on the branch, not on the row's status."""
    tax: tuple[uuid.UUID, uuid.UUID] | None = None
    customs: tuple[Decimal, uuid.UUID] | None = None
    margin: tuple[Decimal, uuid.UUID] | None = None
    for node_id in lineage_ids(tree, category_id):
        node = tree.get(node_id)
        if node is None:
            continue
        if tax is None and node.default_tax_rate_id is not None:
            tax = (node.default_tax_rate_id, node.id)
        if customs is None and node.default_customs_rate_pct is not None:
            customs = (node.default_customs_rate_pct, node.id)
        if margin is None and node.default_margin_rate_pct is not None:
            margin = (node.default_margin_rate_pct, node.id)
        if tax and customs and margin:
            break
    return InheritedDefaults(
        tax_rate_id=tax[0] if tax else None,
        tax_rate_from=tax[1] if tax else None,
        customs_rate_pct=customs[0] if customs else None,
        customs_rate_from=customs[1] if customs else None,
        margin_rate_pct=margin[0] if margin else None,
        margin_rate_from=margin[1] if margin else None,
    )


def check_parent(
    tree: Tree, category_id: uuid.UUID, parent_id: uuid.UUID | None
) -> None:
    """Refuse a parent that is the category itself or one of its descendants
    (``CategoryCycle``)."""
    if parent_id is None:
        return
    if parent_id == category_id or parent_id in descendant_ids(tree, category_id):
        raise CategoryCycle(str(parent_id))


# -- async conveniences -------------------------------------------------------


async def category_lineage(
    session: AsyncSession, category_id: uuid.UUID | None
) -> list[uuid.UUID]:
    """The category and its ancestors, nearest first; ``[]`` without one."""
    if category_id is None:
        return []
    return lineage_ids(await load_tree(session), category_id)


def ancestors_map(tree: Tree) -> dict[uuid.UUID, tuple[uuid.UUID, ...]]:
    """Every category → its ancestors, nearest first (roots: empty)."""
    return {
        node_id: tuple(ancestor_ids(tree, node_id))
        for node_id in tree
        if tree[node_id].parent_id is not None
    }


async def category_ancestors_map(
    session: AsyncSession,
) -> dict[uuid.UUID, tuple[uuid.UUID, ...]]:
    """:func:`ancestors_map` of the live tree."""
    return ancestors_map(await load_tree(session))


async def category_subtree(
    session: AsyncSession, category_id: uuid.UUID
) -> set[uuid.UUID]:
    """The category and every one below it."""
    return subtree_ids(await load_tree(session), category_id)


async def category_chain(
    session: AsyncSession, category_id: uuid.UUID | None
) -> list[Any]:
    """The category then its ancestors, read one ``session.get`` at a time
    (the pricing resolvers run against stand-in sessions in tests; the
    context loads the whole tree instead). Stops at an unknown parent, a
    cycle or ``MAX_DEPTH``."""
    chain: list[Any] = []
    seen: set[uuid.UUID] = set()
    next_id = category_id
    while next_id is not None and next_id not in seen and len(chain) < MAX_DEPTH:
        seen.add(next_id)
        try:
            category = await session.get(Category, next_id)
        except Exception:  # noqa: BLE001 — a stand-in session, a lost row
            break
        if category is None:
            break
        chain.append(category)
        parent_id = getattr(category, "parent_id", None)
        next_id = parent_id if isinstance(parent_id, uuid.UUID) else None
    return chain


def first_default(chain: Iterable[Any], field: str) -> Any:
    """The first non-``None`` ``field`` along a chain (own value, else the
    nearest ancestor's)."""
    for category in chain:
        value = getattr(category, field, None)
        if value is not None:
            return value
    return None


# -- SQL twins ------------------------------------------------------------------


def subtree_ids_select(category_id: uuid.UUID) -> Any:
    """SQL: the ids of ``category_id`` and its descendants (recursive CTE),
    for an ``IN`` on ``products.category_id``."""
    anchor: Any = select(col(Category.id).label("id"), literal(0).label("depth")).where(
        col(Category.id) == category_id
    )
    tree = anchor.cte("category_subtree", recursive=True)
    child = Category.__table__.alias("subtree_child")  # type: ignore[attr-defined]
    tree = tree.union_all(
        select(child.c.id, tree.c.depth + 1).where(
            child.c.parent_id == tree.c.id, tree.c.depth < MAX_DEPTH
        )
    )
    return select(tree.c.id)


def product_in_category_condition(category_id: uuid.UUID) -> Any:
    """SQL: the enclosing product belongs to the category or one below it."""
    return col(Product.category_id).in_(subtree_ids_select(category_id))


def inherited_customs_rate_subquery() -> Any:
    """SQL: the customs rate in force for the enclosing ``Product`` row's
    category — its own, else the nearest ancestor's (``NULL`` when none).
    A nested recursive CTE correlated on ``products.category_id``."""
    start = Category.__table__.alias("chain_start")  # type: ignore[attr-defined]
    anchor: Any = select(
        start.c.id.label("id"),
        start.c.parent_id.label("parent_id"),
        start.c.default_customs_rate_pct.label("rate"),
        literal(0).label("depth"),
    ).where(start.c.id == col(Product.category_id))
    # The anchor reads the enclosing product row: never a FROM of its own.
    anchor = anchor.correlate(Product)
    chain = anchor.cte("category_chain", recursive=True, nesting=True)
    parent = Category.__table__.alias("chain_parent")  # type: ignore[attr-defined]
    chain = chain.union_all(
        select(
            parent.c.id,
            parent.c.parent_id,
            parent.c.default_customs_rate_pct,
            chain.c.depth + 1,
        ).where(parent.c.id == chain.c.parent_id, chain.c.depth < MAX_DEPTH)
    )
    return (
        select(chain.c.rate)
        .where(chain.c.rate.is_not(None))
        .order_by(chain.c.depth)
        .limit(1)
        .correlate(Product)
        .scalar_subquery()
    )


__all__ = [
    "MAX_DEPTH",
    "CategoryCycle",
    "CategoryNode",
    "InheritedDefaults",
    "Tree",
    "ancestor_ids",
    "ancestors_map",
    "category_ancestors_map",
    "build_tree",
    "category_chain",
    "category_lineage",
    "category_subtree",
    "check_parent",
    "depth_of",
    "descendant_ids",
    "first_default",
    "inherited_customs_rate_subquery",
    "inherited_defaults",
    "lineage_ids",
    "load_tree",
    "path_titles",
    "product_in_category_condition",
    "subtree_ids",
    "subtree_ids_select",
]
