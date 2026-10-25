"""Back-office des catégories (A17 + A12).

GET   /admin/categories               — toutes les catégories, fusionnées comprises,
                                        avec le nombre de produits, dans l'ordre
                                        de l'arbre (parents puis enfants)
POST  /admin/categories               — créer une catégorie (sous un parent ou non)
PATCH /admin/categories/{id}          — titre vitrine, description, image, activation,
                                        parent, marge par défaut
POST  /admin/categories/{id}/merge    — fusionner dans une autre catégorie

Hiérarchie (« Réseau > WiFi > Point d'accès WiFi ») : ``parent_id``. Une
sous-catégorie hérite des valeurs par défaut que sa branche ne fixe pas (TVA,
douane, marge) — ``inherited_*`` les donne telles qu'en vigueur, avec la
catégorie d'où elles viennent — et la vitrine liste une catégorie avec les
produits de ses descendantes.

Les catégories naissent de la synchronisation fournisseur (``get_or_create_by_name``
sur la sous-catégorie Ingram) : leur ``name`` est la clé de rapprochement et ne se
renomme pas. Ce que l'admin personnalise vit à côté — ``display_name`` pour le
titre vitrine (résolu par ``CategoryPublic.title``), ``description`` et
``image_url`` que la sync ne touche jamais. Le taux de TVA et le taux de douane
par défaut ont déjà leurs endpoints dans ``admin_tax_rates.py``.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy import update as sa_update
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.content_i18n import (
    CATEGORY_FIELDS,
    InvalidTranslations,
    clean_translations,
    translation_status,
)
from app.core.errors import AppError
from app.features.discount.models import Discount
from app.features.integrations.models.supplier import Supplier
from app.features.integrations.models.supplier_category_mapping import (
    SupplierCategoryMapping,
)
from app.features.integrations.services.category_mapping import retarget_after_merge
from app.features.product.crud.category import crud_category
from app.features.product.models.category import Category
from app.features.product.models.product import Product
from app.features.product.services.category_tree import (
    CategoryCycle,
    Tree,
    build_tree,
    check_parent,
    depth_of,
    descendant_ids,
    inherited_defaults,
    load_tree,
    path_titles,
)
from app.features.product.services.related import (
    replace_category_links,
    suggested_categories_map,
)
from app.features.product.services.spec_projection import retarget_spec_definitions
from app.tasks.pricing_tasks import schedule_price_refresh

logger = logging.getLogger(__name__)

#: Category fields that feed the price formula (see ``PricingContext``).
PRICING_FIELDS = frozenset(
    {"default_margin_rate_pct", "default_customs_rate_pct", "default_tax_rate_id"}
)

router = APIRouter(prefix="/admin/categories", tags=["admin-categories"])


class AdminCategoryItem(BaseModel):
    """Une catégorie vue du back-office."""

    id: uuid.UUID
    name: str
    display_name: str | None
    title: str
    description: str | None
    image_url: str | None
    is_active: bool
    default_tax_rate_id: uuid.UUID | None
    default_customs_rate_pct: Decimal | None
    default_margin_rate_pct: Decimal | None = None
    merged_into_id: uuid.UUID | None
    merged_into_name: str | None = None
    product_count: int = 0
    #: Hierarchy: the parent, the titles from the root down to this one
    #: (« Réseau › WiFi › Point d'accès »), the level (0 = root) and how
    #: many categories sit directly below.
    parent_id: uuid.UUID | None = None
    parent_name: str | None = None
    path: list[str] = Field(default_factory=list)
    depth: int = 0
    children_count: int = 0
    #: Defaults in force (own value, else the nearest ancestor's), and the
    #: title of the ancestor they come from (None = own value or nothing).
    inherited_tax_rate_id: uuid.UUID | None = None
    inherited_tax_rate_from: str | None = None
    inherited_customs_rate_pct: Decimal | None = None
    inherited_customs_rate_from: str | None = None
    inherited_margin_rate_pct: Decimal | None = None
    inherited_margin_rate_from: str | None = None
    #: Translated display_name / description per language (R9 / T3).
    translations: dict[str, dict[str, Any]] = Field(default_factory=dict)
    translation_status: dict[str, str] = Field(default_factory=dict)
    #: Categories suggested from this one's products (R9 / T7), in order.
    suggested_category_ids: list[uuid.UUID] = Field(default_factory=list)
    #: Supplier categories mapped to this one (« Ingram : Computers / Notebooks »),
    #: from the per-supplier mapping rules (Suppliers → Categories).
    supplier_sources: list[str] = Field(default_factory=list)


class AdminCategoriesPublic(BaseModel):
    """Liste complète (pas de pagination : quelques dizaines de lignes)."""

    data: list[AdminCategoryItem]
    count: int


class AdminCategoryUpdate(BaseModel):
    """Champs personnalisables. ``name`` n'en fait pas partie : c'est la clé
    de rapprochement de la sync. Pour renommer côté vitrine, ``display_name``."""

    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    #: Marge par défaut des articles de la catégorie (None = celle de la
    #: catégorie parente, sinon du groupe tarifaire). Un article peut la surcharger.
    default_margin_rate_pct: Decimal | None = Field(default=None, ge=0)
    #: Catégorie parente (None = catégorie de premier niveau).
    parent_id: uuid.UUID | None = None
    #: Traductions du titre vitrine et de la description (R9 / T3).
    translations: dict[str, dict[str, Any]] | None = None
    #: Catégories à proposer depuis les articles de celle-ci (R9 / T7).
    suggested_category_ids: list[uuid.UUID] | None = None


class MergeBody(BaseModel):
    """Cible d'une fusion."""

    target_id: uuid.UUID


class MergeResult(BaseModel):
    """Bilan d'une fusion."""

    source: AdminCategoryItem
    target: AdminCategoryItem
    moved_products: int
    moved_discounts: int


def _origin_title(tree: Tree, origin: uuid.UUID | None, own: uuid.UUID) -> str | None:
    """Title of the ancestor a default comes from (None when it is the
    category's own or nothing is set)."""
    if origin is None or origin == own or origin not in tree:
        return None
    return tree[origin].title


def _to_item(
    category: Category,
    *,
    product_count: int,
    merged_into_name: str | None,
    suggested: list[uuid.UUID] | None = None,
    supplier_sources: list[str] | None = None,
    tree: Tree | None = None,
    children_count: int = 0,
) -> AdminCategoryItem:
    tree = tree if tree is not None else build_tree([category])
    effective = inherited_defaults(tree, category.id)
    parent = tree.get(category.parent_id) if category.parent_id else None
    return AdminCategoryItem(
        id=category.id,
        name=category.name,
        display_name=category.display_name,
        title=category.display_name or category.name,
        description=category.description,
        image_url=category.image_url,
        is_active=category.is_active,
        default_tax_rate_id=category.default_tax_rate_id,
        default_customs_rate_pct=category.default_customs_rate_pct,
        default_margin_rate_pct=category.default_margin_rate_pct,
        merged_into_id=category.merged_into_id,
        merged_into_name=merged_into_name,
        product_count=product_count,
        translations=dict(category.translations or {}),
        translation_status=translation_status(
            category.translations,
            {f: getattr(category, f, None) for f in CATEGORY_FIELDS},
            CATEGORY_FIELDS,
        ),
        suggested_category_ids=list(suggested or []),
        supplier_sources=list(supplier_sources or []),
        parent_id=category.parent_id,
        parent_name=parent.title if parent else None,
        path=path_titles(tree, category.id),
        depth=depth_of(tree, category.id),
        children_count=children_count,
        inherited_tax_rate_id=effective.tax_rate_id,
        inherited_tax_rate_from=_origin_title(
            tree, effective.tax_rate_from, category.id
        ),
        inherited_customs_rate_pct=effective.customs_rate_pct,
        inherited_customs_rate_from=_origin_title(
            tree, effective.customs_rate_from, category.id
        ),
        inherited_margin_rate_pct=effective.margin_rate_pct,
        inherited_margin_rate_from=_origin_title(
            tree, effective.margin_rate_from, category.id
        ),
    )


def _children_counts(tree: Tree) -> dict[uuid.UUID, int]:
    counts: dict[uuid.UUID, int] = {}
    for node in tree.values():
        if node.parent_id is not None and not node.merged_into_id:
            counts[node.parent_id] = counts.get(node.parent_id, 0) + 1
    return counts


def _check_parent(
    tree: Tree,
    category_id: uuid.UUID | None,
    parent_id: uuid.UUID | None,
) -> None:
    """A parent must exist, be neither merged nor the category itself nor
    one of its descendants."""
    if parent_id is None:
        return
    parent = tree.get(parent_id)
    if parent is None:
        raise AppError(
            code="category.parent.not_found",
            status_code=400,
            message=f"Catégorie parente introuvable : {parent_id}",
            details={"field": "parent_id"},
        )
    if parent.merged_into_id is not None:
        raise AppError(
            code="category.parent.merged",
            status_code=409,
            message="La catégorie parente a été fusionnée dans une autre",
            details={"field": "parent_id", "parent_id": str(parent_id)},
        )
    if category_id is not None:
        try:
            check_parent(tree, category_id, parent_id)
        except CategoryCycle as exc:
            raise AppError(
                code="category.parent.cycle",
                status_code=409,
                message=(
                    "Une catégorie ne peut pas être rangée sous elle-même ni "
                    "sous une de ses sous-catégories"
                ),
                details={"field": "parent_id", "parent_id": str(parent_id)},
            ) from exc


async def supplier_sources_map(
    session: SessionDep, category_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """Per category, the supplier couples whose mapping rule targets it."""
    if not category_ids:
        return {}
    rows = (
        await session.exec(
            select(
                col(SupplierCategoryMapping.category_id),
                col(Supplier.name),
                col(SupplierCategoryMapping.source_category),
                col(SupplierCategoryMapping.source_subcategory),
            )
            .join(
                Supplier, col(Supplier.id) == col(SupplierCategoryMapping.supplier_id)
            )
            .where(col(SupplierCategoryMapping.category_id).in_(category_ids))
            .order_by(
                col(Supplier.name),
                col(SupplierCategoryMapping.source_category),
                col(SupplierCategoryMapping.source_subcategory),
            )
        )
    ).all()
    out: dict[uuid.UUID, list[str]] = {}
    for category_id, supplier_name, source_category, source_subcategory in rows:
        if category_id is None:
            continue
        couple = " / ".join(p for p in (source_category, source_subcategory) if p)
        out.setdefault(category_id, []).append(f"{supplier_name} : {couple}")
    return out


async def _load(session: SessionDep, category_id: uuid.UUID) -> Category:
    category = await session.get(Category, category_id)
    if category is None:
        raise AppError(
            code="category.not_found",
            status_code=404,
            message=f"Category '{category_id}' not found",
            details={"category_id": str(category_id)},
        )
    return category


async def _product_count(session: SessionDep, category_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Product)
        .where(Product.category_id == category_id)
    )
    return int((await session.exec(stmt)).one())


async def _item_for(session: SessionDep, category: Category) -> AdminCategoryItem:
    merged_name: str | None = None
    if category.merged_into_id is not None:
        target = await session.get(Category, category.merged_into_id)
        merged_name = target.name if target is not None else None
    suggested = await suggested_categories_map(session, [category.id])
    sources = await supplier_sources_map(session, [category.id])
    tree = await load_tree(session)
    return _to_item(
        category,
        product_count=await _product_count(session, category.id),
        merged_into_name=merged_name,
        suggested=suggested.get(category.id),
        supplier_sources=sources.get(category.id),
        tree=tree,
        children_count=_children_counts(tree).get(category.id, 0),
    )


@router.get("", response_model=AdminCategoriesPublic)
async def list_categories(
    session: SessionDep, _current_user: CurrentSuperUser
) -> AdminCategoriesPublic:
    """Toutes les catégories, y compris inactives et fusionnées."""
    categories = list(
        (await session.exec(select(Category).order_by(col(Category.name)))).all()
    )
    counts_stmt = select(col(Product.category_id), func.count()).group_by(
        col(Product.category_id)
    )
    counts = {row[0]: int(row[1]) for row in await session.exec(counts_stmt)}
    names = {c.id: c.name for c in categories}
    suggested = await suggested_categories_map(session, [c.id for c in categories])
    sources = await supplier_sources_map(session, [c.id for c in categories])
    tree = build_tree(categories)
    children = _children_counts(tree)

    data = [
        _to_item(
            c,
            product_count=counts.get(c.id, 0),
            merged_into_name=names.get(c.merged_into_id) if c.merged_into_id else None,
            suggested=suggested.get(c.id),
            supplier_sources=sources.get(c.id),
            tree=tree,
            children_count=children.get(c.id, 0),
        )
        for c in categories
    ]
    # Tree order: a parent, then its children (« Réseau », « Réseau › WiFi »…).
    data.sort(key=lambda item: [p.casefold() for p in item.path])
    return AdminCategoriesPublic(data=data, count=len(data))


class AdminCategoryCreate(BaseModel):
    """Une catégorie créée à la main (le nom devient sa clé de rapprochement)."""

    name: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    #: Catégorie parente (« Réseau » pour « WiFi »), None = premier niveau.
    parent_id: uuid.UUID | None = None


@router.post("", response_model=AdminCategoryItem, status_code=201)
async def create_category(
    payload: AdminCategoryCreate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> AdminCategoryItem:
    """Créer une catégorie (cible d'un mappage fournisseur, rayon manuel…).

    Le nom est unique sans tenir compte de la casse, catégories fusionnées ou
    inactives comprises : la synchronisation les résout par leur nom.
    """
    name = " ".join(payload.name.split())
    existing = await crud_category.get_by_name_ilike_any(session, name)
    if existing is not None:
        raise AppError(
            code="category.name.conflict",
            status_code=409,
            message=f"Une catégorie « {existing.name} » existe déjà",
            details={"category_id": str(existing.id)},
        )
    if payload.parent_id is not None:
        _check_parent(await load_tree(session), None, payload.parent_id)
    display = (payload.display_name or "").strip()
    category = Category(
        name=name,
        display_name=display if display and display != name else None,
        description=payload.description,
        parent_id=payload.parent_id,
        is_active=True,
        is_admin_active=True,
    )
    category.created_by_id = current_user.id
    session.add(category)
    await session.commit()
    await session.refresh(category)
    logger.info("Admin created category %s (%s)", category.id, name)
    return await _item_for(session, category)


@router.patch("/{category_id}", response_model=AdminCategoryItem)
async def update_category(
    category_id: uuid.UUID,
    payload: AdminCategoryUpdate,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> AdminCategoryItem:
    """Personnaliser une catégorie sans toucher à sa clé de rapprochement."""
    category = await _load(session, category_id)
    fields = payload.model_dump(exclude_unset=True)

    if fields.get("is_active") is True and category.merged_into_id is not None:
        raise AppError(
            code="category.merged",
            status_code=409,
            message="Cette catégorie a été fusionnée : elle ne peut pas être réactivée",
            details={
                "category_id": str(category_id),
                "merged_into_id": str(category.merged_into_id),
            },
        )

    if "display_name" in fields and fields["display_name"] is not None:
        # Un titre vide ou égal au nom n'est pas une personnalisation.
        cleaned = fields["display_name"].strip()
        fields["display_name"] = (
            cleaned if cleaned and cleaned != category.name else None
        )

    if "translations" in fields:
        source = {f: fields.get(f, getattr(category, f, None)) for f in CATEGORY_FIELDS}
        try:
            fields["translations"] = clean_translations(
                fields["translations"],
                previous=category.translations,
                source_values=source,
                fields=CATEGORY_FIELDS,
            )
        except InvalidTranslations as exc:
            raise AppError(
                code="category.translations.invalid",
                status_code=400,
                message=f"Traductions invalides : {exc}",
                details={"field": "translations"},
            ) from exc

    if "parent_id" in fields and fields["parent_id"] != category.parent_id:
        _check_parent(await load_tree(session), category.id, fields["parent_id"])

    suggested = fields.pop("suggested_category_ids", None)
    if suggested is not None:
        known = set(
            (
                await session.exec(
                    select(Category.id).where(col(Category.id).in_(list(suggested)))
                )
            ).all()
        )
        unknown = [str(s) for s in suggested if s not in known]
        if unknown:
            raise AppError(
                code="category.suggested.unknown",
                status_code=400,
                message=f"Catégorie introuvable : {unknown[0]}",
                details={"field": "suggested_category_ids"},
            )
        await replace_category_links(session, category.id, list(suggested))

    for name, value in fields.items():
        setattr(category, name, value)
    category.modify_by_id = current_user.id
    session.add(category)
    await session.commit()
    await session.refresh(category)
    logger.info(
        "Admin updated category: category_id=%s fields=%s", category_id, sorted(fields)
    )
    if (PRICING_FIELDS | {"parent_id"}) & set(fields):
        # Margin, customs or tax default changed — or the parent they are
        # inherited from: the list prices of the category's products (the
        # sub-categories' included) are stale until refreshed.
        await schedule_price_refresh(
            reason="category_pricing_defaults", category_id=category_id
        )
    return await _item_for(session, category)


@router.post("/{category_id}/merge", response_model=MergeResult)
async def merge_category(
    category_id: uuid.UUID,
    payload: MergeBody,
    session: SessionDep,
    current_user: CurrentSuperUser,
) -> MergeResult:
    """Fusionner ``category_id`` dans ``target_id``.

    Les produits et les remises ciblant la source passent sur la cible ; la
    source reste en base, inactive, avec ``merged_into_id`` posé, pour que la
    prochaine synchronisation continue de résoudre son nom vers la cible au
    lieu de la recréer. Les produits sans taux de douane propre héritent dès
    lors de celui de la cible.
    """
    if payload.target_id == category_id:
        raise AppError(
            code="category.merge.self",
            status_code=400,
            message="Une catégorie ne peut pas être fusionnée dans elle-même",
            details={"category_id": str(category_id)},
        )
    source = await _load(session, category_id)
    target = await _load(session, payload.target_id)

    if source.merged_into_id is not None:
        raise AppError(
            code="category.merged",
            status_code=409,
            message="Cette catégorie a déjà été fusionnée",
            details={
                "category_id": str(category_id),
                "merged_into_id": str(source.merged_into_id),
            },
        )
    if target.merged_into_id is not None or not target.is_active:
        raise AppError(
            code="category.merge.target_unavailable",
            status_code=409,
            message="La catégorie cible est inactive ou a elle-même été fusionnée",
            details={"target_id": str(payload.target_id)},
        )
    tree = await load_tree(session)
    if payload.target_id in descendant_ids(tree, category_id):
        raise AppError(
            code="category.merge.target_below_source",
            status_code=409,
            message=(
                "La catégorie cible est une sous-catégorie de la source : "
                "déplacez-la d'abord ailleurs"
            ),
            details={"target_id": str(payload.target_id)},
        )

    admin_id = current_user.id
    source_id, target_id = source.id, target.id

    # The source's sub-categories move under the target.
    moved_children = (
        await session.exec(
            sa_update(Category)
            .where(col(Category.parent_id) == source_id)
            .values(parent_id=target_id)
        )
    ).rowcount

    moved_products = (
        await session.exec(
            sa_update(Product)
            .where(col(Product.category_id) == source_id)
            .values(category_id=target_id)
        )
    ).rowcount
    moved_discounts = (
        await session.exec(
            sa_update(Discount)
            .where(col(Discount.category_id) == source_id)
            .values(category_id=target_id)
        )
    ).rowcount

    # Supplier category rules aiming at the source now aim at the target,
    # and so do the characteristics scoped to it.
    await retarget_after_merge(session, source_id, target_id)
    await retarget_spec_definitions(session, source_id, target_id)
    source.is_active = False
    source.merged_into_id = target_id
    source.modify_by_id = admin_id
    session.add(source)
    await session.commit()
    await session.refresh(source)
    await session.refresh(target)
    if moved_products:
        # Moved products now inherit the target's margin / customs / tax.
        await schedule_price_refresh(reason="category_merge", category_id=target_id)

    logger.info(
        "Category merged: source=%s target=%s products=%s discounts=%s "
        "children=%s admin=%s",
        source_id,
        target_id,
        moved_products,
        moved_discounts,
        moved_children,
        admin_id,
    )
    return MergeResult(
        source=await _item_for(session, source),
        target=await _item_for(session, target),
        moved_products=int(moved_products),
        moved_discounts=int(moved_discounts),
    )
