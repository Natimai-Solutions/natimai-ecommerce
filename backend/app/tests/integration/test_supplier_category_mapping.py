"""Supplier categories mapped onto the shop's (R4 / S5)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_categories import (
    AdminCategoryCreate,
    MergeBody,
    create_category,
    merge_category,
)
from app.api.routes.admin_suppliers import (
    get_category_mappings,
    get_observed_categories,
    put_category_mappings,
    reapply_category_mappings,
    update_supplier,
)
from app.api.routes.suppliers import import_catalog_file
from app.core.config import settings
from app.core.errors import AppError
from app.features.integrations.models.supplier import (
    Supplier,
    SupplierCreate,
    SupplierKind,
    SupplierUpdate,
)
from app.features.integrations.models.supplier_category_mapping import (
    CategoryMappingAction,
    CategoryMappingWrite,
    UnmappedCategoryAction,
)
from app.features.product.models.category import Category
from app.features.product.models.product import Product
from app.features.user.models.user import User
from app.tests.integration.test_suppliers_admin_and_file_import import (
    _fresh,
    _seed_admin,
    _upload,
)

HEADER = "Ref;Désignation;Prix HT;Stock;Catégorie;Sous-catégorie\n"
#: Stand-in for the current user: a real row's id (audit FKs), never expired.
ADMIN = cast(User, SimpleNamespace(id=uuid.uuid4(), is_superuser=True))


@pytest.fixture(autouse=True)
def _no_global_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST", [])


@pytest_asyncio.fixture(autouse=True)
async def _admin_row(db_session: AsyncSession) -> None:
    admin = await _seed_admin(db_session)
    ADMIN.id = admin.id
    await db_session.commit()


async def _supplier(session: AsyncSession, code: str = "grossiste") -> Supplier:
    from app.api.routes.admin_suppliers import create_supplier

    await create_supplier(
        payload=SupplierCreate(
            code=code,
            name=code,
            kind=SupplierKind.FILE,
            is_domestic=True,
            price_currency="XPF",
            column_mapping={
                "supplier_sku": "Ref",
                "name": "Désignation",
                "price": "Prix HT",
                "quantity": "Stock",
                "category": "Catégorie",
                "subcategory": "Sous-catégorie",
            },
        ),
        session=session,
        current_user=ADMIN,
    )
    return (await session.exec(select(Supplier).where(Supplier.code == code))).one()


async def _category(session: AsyncSession, name: str) -> uuid.UUID:
    created = await create_category(AdminCategoryCreate(name=name), session, ADMIN)
    return created.id


async def _import(
    session: AsyncSession,
    row: Supplier,
    content: bytes,
    *,
    dry_run: bool = False,
    default_category_id: uuid.UUID | None = None,
) -> Any:
    admin = await _seed_admin(session)
    await session.commit()
    await session.refresh(row)
    return await import_catalog_file(
        supplier=row,
        session=session,
        current_user=await _fresh(session, admin),
        file=_upload(content),
        mapping=None,
        dry_run=dry_run,
        default_category_id=default_category_id,
    )


async def _by_sku(session: AsyncSession, code: str) -> dict[str, Product]:
    rows = (
        await session.exec(select(Product).where(Product.supplier_name == code))
    ).all()
    return {p.supplier_sku or "": p for p in rows}


async def _category_name(
    session: AsyncSession, category_id: uuid.UUID | None
) -> str | None:
    if category_id is None:
        return None
    category = await session.get(Category, category_id)
    return category.name if category else None


@pytest.mark.asyncio
async def test_without_rules_the_category_is_used_when_no_subcategory(
    db_session: AsyncSession,
) -> None:
    row = await _supplier(db_session)
    content = (
        HEADER
        + "A-1;Portable 14;90000;5;Informatique;Portables\n"
        + "A-2;Souris;2000;5;Accessoires;\n"
    ).encode()
    await _import(db_session, row, content)
    products = await _by_sku(db_session, "grossiste")
    assert await _category_name(db_session, products["A-1"].category_id) == "Portables"
    assert (
        await _category_name(db_session, products["A-2"].category_id) == "Accessoires"
    )


@pytest.mark.asyncio
async def test_rules_place_draft_hide_and_skip(db_session: AsyncSession) -> None:
    row = await _supplier(db_session)
    code = row.code
    laptops = await _category(db_session, "Ordinateurs portables")
    await put_category_mappings(
        code,
        [
            # Exact couple → an existing shop category.
            CategoryMappingWrite(
                source_category="Informatique",
                source_subcategory="Portables",
                category_id=laptops,
            ),
            # Category alone: every subcategory without its own rule.
            CategoryMappingWrite(
                source_category="Téléphonie", action=CategoryMappingAction.DRAFT
            ),
            CategoryMappingWrite(
                source_category="Câbles", action=CategoryMappingAction.DEACTIVATE
            ),
            CategoryMappingWrite(
                source_category="Consommables", action=CategoryMappingAction.SKIP
            ),
        ],
        db_session,
        ADMIN,
    )
    content = (
        HEADER
        + "B-1;Portable 15;95000;5;informatique ;PORTABLES\n"
        + "B-2;Smartphone;60000;5;Téléphonie;Android\n"
        + "B-3;Câble USB;500;5;Câbles;USB\n"
        + "B-4;Encre;900;5;Consommables;Encre\n"
    ).encode()

    preview = await _import(db_session, row, content, dry_run=True)
    effects = {
        (p.source_category, p.source_subcategory): p.effect
        for p in preview.category_pairs
    }
    assert effects[("Téléphonie", "Android")] == "draft"
    assert effects[("Consommables", "Encre")] == "skip"
    assert effects[("informatique", "PORTABLES")] == "import"
    laptop_pair = next(
        p for p in preview.category_pairs if p.source_subcategory == "PORTABLES"
    )
    assert laptop_pair.resolved_category_name == "Ordinateurs portables"
    assert preview.resolution["filtered"] == 1

    response = await _import(db_session, row, content)
    assert response.statistics["filtered_products"] == 1
    products = await _by_sku(db_session, code)
    assert set(products) == {"B-1", "B-2", "B-3"}
    assert products["B-1"].category_id == laptops
    assert products["B-2"].is_draft is True
    assert await _category_name(db_session, products["B-2"].category_id) == "Android"
    assert products["B-3"].is_active is False


@pytest.mark.asyncio
async def test_unmapped_skip_and_global_allowlist_steps_aside(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The global allowlist would deactivate anything but « Portables »…
    monkeypatch.setattr(settings, "SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST", ["Portables"])
    row = await _supplier(db_session)
    code = row.code
    await update_supplier(
        code,
        SupplierUpdate(unmapped_category_action=UnmappedCategoryAction.SKIP),
        db_session,
        ADMIN,
    )
    await put_category_mappings(
        code,
        [CategoryMappingWrite(source_category="Écrans")],
        db_session,
        ADMIN,
    )
    content = (
        HEADER
        + "C-1;Écran 27;30000;5;Écrans;27 pouces\n"
        + "C-2;Imprimante;25000;5;Impression;Laser\n"
    ).encode()
    await _import(db_session, row, content)
    products = await _by_sku(db_session, code)
    # …but this supplier curates its categories: its rules win.
    assert set(products) == {"C-1"}
    assert products["C-1"].is_active is True
    assert await _category_name(db_session, products["C-1"].category_id) == "27 pouces"


@pytest.mark.asyncio
async def test_whole_file_category(db_session: AsyncSession) -> None:
    row = await _supplier(db_session)
    phones = await _category(db_session, "Téléphones reconditionnés")
    content = (HEADER + "D-1;iPhone 12;40000;5;;\n").encode()
    await _import(db_session, row, content, default_category_id=phones)
    products = await _by_sku(db_session, "grossiste")
    assert products["D-1"].category_id == phones


@pytest.mark.asyncio
async def test_reapply_moves_products_except_locked_ones(
    db_session: AsyncSession,
) -> None:
    row = await _supplier(db_session)
    code = row.code
    content = (
        HEADER
        + "E-1;Portable A;90000;5;Informatique;Portables\n"
        + "E-2;Portable B;91000;5;Informatique;Portables\n"
        + "E-3;Câble;500;5;Câbles;HDMI\n"
    ).encode()
    await _import(db_session, row, content)
    products = await _by_sku(db_session, code)
    locked = products["E-2"]
    locked.overridden_fields = ["category_id"]
    db_session.add(locked)
    await db_session.commit()

    laptops = await _category(db_session, "PC portables")
    await put_category_mappings(
        code,
        [
            CategoryMappingWrite(
                source_category="Informatique",
                source_subcategory="Portables",
                category_id=laptops,
            ),
            CategoryMappingWrite(
                source_category="Câbles", action=CategoryMappingAction.DEACTIVATE
            ),
        ],
        db_session,
        ADMIN,
    )
    result = await reapply_category_mappings(code, db_session, ADMIN)
    assert result.moved == 1
    assert result.deactivated == 1

    db_session.expunge_all()
    products = await _by_sku(db_session, code)
    assert products["E-1"].category_id == laptops
    assert products["E-2"].category_id != laptops
    assert products["E-3"].is_active is False

    observed = await get_observed_categories(code, db_session, ADMIN)
    portables = next(o for o in observed if o.source_subcategory == "Portables")
    assert portables.count == 2
    assert portables.resolved_category_name == "PC portables"


@pytest.mark.asyncio
async def test_merge_retargets_rules_and_category_names_are_unique(
    db_session: AsyncSession,
) -> None:
    row = await _supplier(db_session)
    code = row.code
    old = await _category(db_session, "Portables pro")
    new = await _category(db_session, "Portables")
    await put_category_mappings(
        code,
        [CategoryMappingWrite(source_category="Pro", category_id=old)],
        db_session,
        ADMIN,
    )
    await merge_category(old, MergeBody(target_id=new), db_session, ADMIN)
    (rule,) = await get_category_mappings(code, db_session, ADMIN)
    assert rule.category_id == new
    assert rule.category_name == "Portables"

    with pytest.raises(AppError) as refused:
        await create_category(
            AdminCategoryCreate(name="  portables "), db_session, ADMIN
        )
    assert refused.value.status_code == 409
