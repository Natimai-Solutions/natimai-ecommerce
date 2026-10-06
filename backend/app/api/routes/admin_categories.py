"""Back-office des catégories (A17 + A12).

GET   /admin/categories               — toutes les catégories, fusionnées comprises,
                                        avec le nombre de produits
POST  /admin/categories               — créer une catégorie
PATCH /admin/categories/{id}          — titre vitrine, description, image, activation
POST  /admin/categories/{id}/merge    — fusionner dans une autre catégorie

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
    #: Marge par défaut des articles de la catégorie (None = celle du groupe
    #: tarifaire du client). Un article peut la surcharger.
    default_margin_rate_pct: Decimal | None = Field(default=None, ge=0)
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


def _to_item(
    category: Category,
    *,
    product_count: int,
    merged_into_name: str | None,
    suggested: list[uuid.UUID] | None = None,
    supplier_sources: list[str] | None = None,
) -> AdminCategoryItem:
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
    )


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
    return _to_item(
        category,
        product_count=await _product_count(session, category.id),
        merged_into_name=merged_name,
        suggested=suggested.get(category.id),
        supplier_sources=sources.get(category.id),
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

    data = [
        _to_item(
            c,
            product_count=counts.get(c.id, 0),
            merged_into_name=names.get(c.merged_into_id) if c.merged_into_id else None,
            suggested=suggested.get(c.id),
            supplier_sources=sources.get(c.id),
        )
        for c in categories
    ]
    return AdminCategoriesPublic(data=data, count=len(data))


class AdminCategoryCreate(BaseModel):
    """Une catégorie créée à la main (le nom devient sa clé de rapprochement)."""

    name: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)


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
    display = (payload.display_name or "").strip()
    category = Category(
        name=name,
        display_name=display if display and display != name else None,
        description=payload.description,
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
    if PRICING_FIELDS & set(fields):
        # Margin, customs or tax default changed: the list prices of the
        # category's products are stale until refreshed.
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

    admin_id = current_user.id
    source_id, target_id = source.id, target.id

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
        "Category merged: source=%s target=%s products=%s discounts=%s admin=%s",
        source_id,
        target_id,
        moved_products,
        moved_discounts,
        admin_id,
    )
    return MergeResult(
        source=await _item_for(session, source),
        target=await _item_for(session, target),
        moved_products=int(moved_products),
        moved_discounts=int(moved_discounts),
    )
