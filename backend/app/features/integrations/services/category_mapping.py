"""Where a supplier row lands in the shop's categories (R4 / S5).

Resolution of one (category, subcategory) couple, for one supplier:

1. the exact mapping (category | subcategory);
2. the mapping of the category alone (subcategory left empty);
3. the category chosen for the whole file (import option);
4. the supplier's ``unmapped_category_action``: ``auto`` keeps the historical
   rule — a shop category named after the subcategory, **else the category**
   (a file without subcategory used to leave its products uncategorised) —,
   ``draft`` / ``deactivate`` do the same and add their effect, ``skip``
   leaves the row out.

A mapping target is followed through merges (``resolve_merged``). A mapping
without target means « a category named after the source », created if needed.

Loaded once per run (:meth:`CategoryMapper.load`); ``dry`` resolutions (the
import simulation) never create a category.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import String, and_, func, or_
from sqlalchemy import update as sa_update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.integrations.models.supplier import Supplier
from app.features.integrations.models.supplier_category_mapping import (
    CategoryMappingAction,
    CategoryMappingPublic,
    CategoryMappingWrite,
    ObservedCategory,
    SupplierCategoryMapping,
    UnmappedCategoryAction,
    normalize_part,
    source_key,
)
from app.features.product.crud.category import crud_category
from app.features.product.models.category import Category
from app.features.product.models.product import Product


@dataclass(frozen=True, slots=True)
class MappingRule:
    """A mapping row detached from the session (the import commits per row,
    which expires ORM instances)."""

    id: uuid.UUID
    source_category: str | None
    source_subcategory: str | None
    category_id: uuid.UUID | None
    action: str
    updated_at: datetime

    @classmethod
    def of(cls, row: SupplierCategoryMapping) -> MappingRule:
        return cls(
            id=row.id,
            source_category=row.source_category,
            source_subcategory=row.source_subcategory,
            category_id=row.category_id,
            action=CategoryMappingAction(row.action).value,
            updated_at=row.updated_at,
        )


@dataclass(slots=True)
class CategoryDecision:
    """What to do with a row: ``import`` | ``draft`` | ``deactivate`` | ``skip``."""

    action: str
    category_id: uuid.UUID | None = None
    #: Name of the category the row lands in (existing or to be created).
    category_name: str | None = None
    mapping: MappingRule | None = None


def source_name(category: str | None, subcategory: str | None) -> str | None:
    """The shop category a source couple names: its subcategory, else category."""
    for value in (subcategory, category):
        cleaned = " ".join((value or "").split())
        if cleaned:
            return cleaned[:100]
    return None


@dataclass(slots=True)
class CategoryMapper:
    """The mapping rules of one supplier, for one run."""

    supplier_id: uuid.UUID | None = None
    unmapped_action: UnmappedCategoryAction = UnmappedCategoryAction.AUTO
    mappings: dict[str, MappingRule] = field(default_factory=dict)
    default_category_id: uuid.UUID | None = None

    @classmethod
    async def load(
        cls,
        session: AsyncSession,
        supplier_code: str,
        *,
        default_category_id: uuid.UUID | None = None,
    ) -> CategoryMapper:
        supplier = (
            await session.exec(select(Supplier).where(Supplier.code == supplier_code))
        ).first()
        if supplier is None:
            return cls(default_category_id=default_category_id)
        rows = (
            await session.exec(
                select(SupplierCategoryMapping).where(
                    col(SupplierCategoryMapping.supplier_id) == supplier.id
                )
            )
        ).all()
        return cls(
            supplier_id=supplier.id,
            unmapped_action=UnmappedCategoryAction(
                getattr(supplier, "unmapped_category_action", None) or "auto"
            ),
            mappings={row.source_key: MappingRule.of(row) for row in rows},
            default_category_id=default_category_id,
        )

    @property
    def has_rules(self) -> bool:
        """The supplier curates its categories: the global allowlist steps aside."""
        return bool(
            self.mappings
            or self.default_category_id
            or self.unmapped_action != UnmappedCategoryAction.AUTO
        )

    def lookup(
        self, category: str | None, subcategory: str | None
    ) -> MappingRule | None:
        exact = self.mappings.get(source_key(category, subcategory))
        if exact is not None:
            return exact
        if normalize_part(subcategory):
            return self.mappings.get(source_key(category, None))
        return None

    async def _target(
        self,
        session: AsyncSession,
        *,
        category_id: uuid.UUID | None,
        name: str | None,
        dry: bool,
    ) -> tuple[uuid.UUID | None, str | None]:
        if category_id is not None:
            category = await session.get(Category, category_id)
            if category is not None:
                category = await crud_category.resolve_merged(session, category)
                return category.id, category.name
        if not name:
            return None, None
        if dry:
            existing = await crud_category.get_by_name_ilike_any(session, name)
            if existing is None:
                return None, name
            existing = await crud_category.resolve_merged(session, existing)
            return existing.id, existing.name
        created, _ = await crud_category.get_or_create_by_name(session, name=name)
        return created.id, created.name

    async def decide(
        self,
        session: AsyncSession,
        category: str | None,
        subcategory: str | None,
        *,
        dry: bool = False,
    ) -> CategoryDecision:
        name = source_name(category, subcategory)
        mapping = self.lookup(category, subcategory)
        if mapping is not None:
            action = mapping.action
            if action == "skip":
                return CategoryDecision(action="skip", mapping=mapping)
            target_id, target_name = await self._target(
                session, category_id=mapping.category_id, name=name, dry=dry
            )
            return CategoryDecision(
                action=action,
                category_id=target_id,
                category_name=target_name,
                mapping=mapping,
            )
        if self.default_category_id is not None:
            target_id, target_name = await self._target(
                session, category_id=self.default_category_id, name=None, dry=dry
            )
            if target_id is not None:
                return CategoryDecision(
                    action="import", category_id=target_id, category_name=target_name
                )
        unmapped = self.unmapped_action.value
        if unmapped == "skip":
            return CategoryDecision(action="skip")
        target_id, target_name = await self._target(
            session, category_id=None, name=name, dry=dry
        )
        return CategoryDecision(
            action="import" if unmapped == "auto" else unmapped,
            category_id=target_id,
            category_name=target_name,
        )


# -- admin helpers --------------------------------------------------------


async def load_supplier_or_404(session: AsyncSession, code: str) -> Supplier:
    supplier = (
        await session.exec(select(Supplier).where(Supplier.code == code))
    ).first()
    if supplier is None:
        raise AppError(
            code="supplier.not_found",
            status_code=404,
            message=f"Unknown supplier '{code}'",
            details={"supplier_name": code},
        )
    return supplier


async def _category_names(
    session: AsyncSession, ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = (
        await session.exec(select(Category).where(col(Category.id).in_(wanted)))
    ).all()
    return {row.id: row.display_name or row.name for row in rows}


def _public(
    row: SupplierCategoryMapping | MappingRule, names: dict[uuid.UUID, str]
) -> CategoryMappingPublic:
    return CategoryMappingPublic(
        id=row.id,
        source_category=row.source_category,
        source_subcategory=row.source_subcategory,
        category_id=row.category_id,
        category_name=names.get(row.category_id) if row.category_id else None,
        action=CategoryMappingAction(row.action),
        updated_at=row.updated_at,
    )


async def list_mappings(
    session: AsyncSession, supplier: Supplier
) -> list[CategoryMappingPublic]:
    rows = list(
        (
            await session.exec(
                select(SupplierCategoryMapping)
                .where(col(SupplierCategoryMapping.supplier_id) == supplier.id)
                .order_by(
                    col(SupplierCategoryMapping.source_category),
                    col(SupplierCategoryMapping.source_subcategory),
                )
            )
        ).all()
    )
    names = await _category_names(session, (r.category_id for r in rows))
    return [_public(r, names) for r in rows]


async def save_mappings(
    session: AsyncSession, supplier: Supplier, rules: list[CategoryMappingWrite]
) -> list[CategoryMappingPublic]:
    """Create or replace the given rules (keyed by their source couple).

    Rules not listed are left as they are. Flushes, no commit.
    """
    for rule in rules:
        if rule.category_id is not None:
            target = await session.get(Category, rule.category_id)
            if target is None:
                raise AppError(
                    code="category.not_found",
                    status_code=404,
                    message=f"Catégorie inconnue : {rule.category_id}",
                    details={"category_id": str(rule.category_id)},
                )
    existing = {
        row.source_key: row
        for row in (
            await session.exec(
                select(SupplierCategoryMapping).where(
                    col(SupplierCategoryMapping.supplier_id) == supplier.id
                )
            )
        ).all()
    }
    now = datetime.now(UTC)
    for rule in rules:
        key = source_key(rule.source_category, rule.source_subcategory)
        if key == "|":
            raise AppError(
                code="supplier.category_mapping.empty_source",
                status_code=400,
                message="Une règle doit nommer une catégorie ou une sous-catégorie",
                details={},
            )
        row = existing.get(key) or SupplierCategoryMapping(
            supplier_id=supplier.id,
            source_key=key,
            source_category=(rule.source_category or "").strip() or None,
            source_subcategory=(rule.source_subcategory or "").strip() or None,
        )
        row.category_id = rule.category_id
        row.action = rule.action
        row.updated_at = now
        session.add(row)
        existing[key] = row
    await session.flush()
    return await list_mappings(session, supplier)


async def delete_mapping(
    session: AsyncSession, supplier: Supplier, mapping_id: uuid.UUID
) -> None:
    row = await session.get(SupplierCategoryMapping, mapping_id)
    if row is None or row.supplier_id != supplier.id:
        raise AppError(
            code="supplier.category_mapping.not_found",
            status_code=404,
            message="Règle de mappage introuvable",
            details={"mapping_id": str(mapping_id)},
        )
    await session.delete(row)
    await session.flush()


async def describe_pairs(
    session: AsyncSession,
    supplier_code: str,
    pairs: Counter[tuple[str | None, str | None]],
    *,
    global_effect: object | None = None,
    default_category_id: uuid.UUID | None = None,
) -> list[ObservedCategory]:
    """Each couple with its count, its rule and what an import would do.

    ``global_effect`` is a callable ``(category, subcategory) -> "skip" |
    "deactivate" | None`` for the global filter rules (the caller knows them).
    Never creates a category.
    """
    mapper = await CategoryMapper.load(
        session, supplier_code, default_category_id=default_category_id
    )
    names = await _category_names(
        session, (m.category_id for m in mapper.mappings.values())
    )
    out: list[ObservedCategory] = []
    for (category, subcategory), count in sorted(
        pairs.items(),
        key=lambda kv: (normalize_part(kv[0][0]), normalize_part(kv[0][1])),
    ):
        decision = await mapper.decide(session, category, subcategory, dry=True)
        effect = decision.action
        if callable(global_effect) and effect != "skip":
            forced = global_effect(category, subcategory, mapper.has_rules)
            if forced == "skip":
                effect = "filtered"
            elif forced == "deactivate" and effect == "import":
                effect = "deactivate"
        out.append(
            ObservedCategory(
                source_category=category,
                source_subcategory=subcategory,
                count=count,
                mapping=_public(decision.mapping, names) if decision.mapping else None,
                resolved_category_name=decision.category_name,
                effect=effect,
            )
        )
    return out


async def observed_pairs(
    session: AsyncSession, supplier_code: str
) -> Counter[tuple[str | None, str | None]]:
    """The couples of the supplier's products in base, with their counts."""
    rows = await session.exec(
        select(
            col(Product.supplier_category),
            col(Product.supplier_subcategory),
            func.count(),
        )
        .where(col(Product.supplier_name) == supplier_code)
        .group_by(col(Product.supplier_category), col(Product.supplier_subcategory))
    )
    counter: Counter[tuple[str | None, str | None]] = Counter()
    for category, subcategory, count in rows.all():
        counter[(category, subcategory)] += int(count)
    return counter


def _norm(column: Any) -> Any:
    """SQL twin of :func:`normalize_part` (spaces collapsed, lower case)."""
    return func.lower(
        func.btrim(func.regexp_replace(func.coalesce(column, ""), r"\s+", " ", "g"))
    )


def _source_match(category: str | None, subcategory: str | None) -> Any:
    """SQL: the supplier product carries this couple (case / spaces aside)."""
    clauses: list[Any] = [
        _norm(col(Product.supplier_category)) == normalize_part(category)
    ]
    if normalize_part(subcategory):
        clauses.append(
            _norm(col(Product.supplier_subcategory)) == normalize_part(subcategory)
        )
    return and_(*clauses)


async def reapply_mappings(session: AsyncSession, supplier: Supplier) -> dict[str, int]:
    """Apply the rules to the supplier's products already in base.

    Moves products to their target category (unless the admin locked
    ``category_id`` on the product) and takes ``deactivate`` / ``skip``
    couples off the storefront. Exact rules win over category-only rules.
    Flushes, no commit; returns counters.
    """
    mapper = await CategoryMapper.load(session, supplier.code)
    moved = deactivated = 0
    ordered = sorted(
        mapper.mappings.values(),
        # Category-only rules first, exact ones after: the exact rule wins.
        key=lambda m: 1 if normalize_part(m.source_subcategory) else 0,
    )
    for mapping in ordered:
        match = _source_match(mapping.source_category, mapping.source_subcategory)
        base: list[Any] = [col(Product.supplier_name) == supplier.code, match]
        if mapping.action in ("deactivate", "skip"):
            result = await session.exec(
                sa_update(Product)
                .where(*base, col(Product.is_active).is_(True))
                .values(is_active=False)
            )
            deactivated += int(result.rowcount or 0)
            continue
        decision = await mapper.decide(
            session, mapping.source_category, mapping.source_subcategory
        )
        if decision.category_id is None:
            continue
        # A category the admin set by hand on the product (locked) stays.
        not_locked = or_(
            col(Product.overridden_fields).is_(None),
            ~func.coalesce(
                func.cast(col(Product.overridden_fields), String), ""
            ).contains('"category_id"'),
        )
        result = await session.exec(
            sa_update(Product)
            .where(
                *base,
                not_locked,
                or_(
                    col(Product.category_id).is_(None),
                    col(Product.category_id) != decision.category_id,
                ),
            )
            .values(category_id=decision.category_id)
        )
        moved += int(result.rowcount or 0)
    await session.flush()
    return {"moved": moved, "deactivated": deactivated}


async def retarget_after_merge(
    session: AsyncSession, source_id: uuid.UUID, target_id: uuid.UUID
) -> int:
    """A category merged into another: its mappings follow. Flushes."""
    result = await session.exec(
        sa_update(SupplierCategoryMapping)
        .where(col(SupplierCategoryMapping.category_id) == source_id)
        .values(category_id=target_id)
    )
    return int(result.rowcount or 0)


__all__ = [
    "CategoryDecision",
    "CategoryMapper",
    "delete_mapping",
    "describe_pairs",
    "list_mappings",
    "load_supplier_or_404",
    "observed_pairs",
    "reapply_mappings",
    "retarget_after_merge",
    "save_mappings",
    "source_name",
]
