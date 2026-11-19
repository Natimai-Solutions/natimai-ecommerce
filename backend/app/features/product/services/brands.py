"""Brand sheets (chantier accueil et messagerie, lot BR).

Suppliers and Icecat give a free-text manufacturer name (« HP », « HP Inc. »,
« hp »). Each product is linked to a **brand sheet** through it:

- a name is reduced to a **key** (case, accents, punctuation and company
  suffixes dropped: « Hewlett-Packard Inc. » → ``hewlett packard``);
- a key matches a brand by its own name or by one of its **aliases**
  (« HP Inc. », « Hewlett-Packard » → HP);
- an unknown name creates a brand **to validate**: products are linked at
  once, but the brand only shows (facet, brand page) once the admin checked
  it, merged it into another or added it as an alias.

``manufacturer`` stays as the supplier gave it (identity of the item, search
text): the brand is a layer above it.
"""

from __future__ import annotations

import re
import unicodedata
import uuid

from sqlalchemy import func, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.brand import Brand, BrandAlias
from app.features.product.models.product import Product

#: Company forms that do not tell brands apart.
_SUFFIXES = (
    "incorporated",
    "corporation",
    "company",
    "limited",
    "gmbh",
    "inc",
    "corp",
    "ltd",
    "llc",
    "co",
    "sa",
    "sas",
    "sarl",
    "ag",
    "bv",
    "plc",
    "srl",
    "spa",
)


def brand_key(name: str | None) -> str:
    """The comparable form of a brand name ('' for nothing usable)."""
    text = (
        unicodedata.normalize("NFKD", (name or "").strip())
        .encode("ascii", "ignore")
        .decode()
    )
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)[:100]


def slugify(name: str) -> str:
    return brand_key(name).replace(" ", "-")[:120] or "marque"


async def _unique_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name)
    slug, n = base, 2
    while (
        await session.exec(select(Brand.id).where(col(Brand.slug) == slug))
    ).first() is not None:
        slug, n = f"{base}-{n}", n + 1
    return slug


async def find_brand(session: AsyncSession, name: str | None) -> Brand | None:
    """The brand a name resolves to, by alias or by its own name."""
    key = brand_key(name)
    if not key:
        return None
    alias = (
        await session.exec(select(BrandAlias).where(col(BrandAlias.key) == key))
    ).first()
    if alias is not None:
        return await session.get(Brand, alias.brand_id)
    for brand in (
        await session.exec(select(Brand).where(col(Brand.is_active).is_(True)))
    ).all():
        if brand_key(brand.name) == key:
            return brand
    return None


async def resolve_brand(session: AsyncSession, name: str | None) -> Brand | None:
    """The brand of a manufacturer name; an unknown one creates a brand to
    validate (no commit)."""
    found = await find_brand(session, name)
    if found is not None or not brand_key(name):
        return found
    clean = re.sub(r"\s+", " ", (name or "").strip())[:100]
    brand = Brand(
        name=clean, slug=await _unique_slug(session, clean), is_validated=False
    )
    session.add(brand)
    await session.flush()
    return brand


async def _key_map(session: AsyncSession) -> dict[str, uuid.UUID]:
    keys: dict[str, uuid.UUID] = {}
    for brand_id, name in (
        await session.exec(
            select(Brand.id, Brand.name).where(col(Brand.is_active).is_(True))
        )
    ).all():
        keys.setdefault(brand_key(name), brand_id)
    for brand_id, key in (
        await session.exec(select(BrandAlias.brand_id, BrandAlias.key))
    ).all():
        keys[key] = brand_id
    return keys


async def link_unbranded_products(session: AsyncSession, *, limit: int = 5000) -> int:
    """Link every product to the sheet of its manufacturer name (commits):
    the products without a brand, and those whose name changed since (an
    import, an edit). One lookup per distinct (name, brand) pair."""
    pairs = (
        await session.exec(
            select(Product.manufacturer, Product.brand_id)
            .where(
                col(Product.manufacturer).is_not(None),
                func.btrim(col(Product.manufacturer)) != "",
            )
            .distinct()
            .limit(limit)
        )
    ).all()
    keys = await _key_map(session)
    linked = 0
    for manufacturer, current in pairs:
        key = brand_key(manufacturer)
        if not key:
            continue
        brand_id = keys.get(key)
        if brand_id is None:
            brand = await resolve_brand(session, manufacturer)
            if brand is None:
                continue
            brand_id = keys[key] = brand.id
        if brand_id == current:
            continue
        condition = (
            col(Product.brand_id).is_(None)
            if current is None
            else col(Product.brand_id) == current
        )
        result = await session.execute(
            update(Product)
            .where(condition, col(Product.manufacturer) == manufacturer)
            .values(brand_id=brand_id)
        )
        linked += int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return linked


async def set_aliases(
    session: AsyncSession, brand: Brand, aliases: list[str]
) -> list[str]:
    """Replace the aliases of a brand; an alias another brand holds is moved
    here, and the products named so follow (no commit)."""
    existing = (
        await session.exec(
            select(BrandAlias).where(col(BrandAlias.brand_id) == brand.id)
        )
    ).all()
    wanted: dict[str, str] = {}
    for alias in aliases:
        key = brand_key(alias)
        if key and key != brand_key(brand.name):
            wanted.setdefault(key, alias.strip()[:100])
    for row in existing:
        if row.key not in wanted:
            await session.delete(row)
    kept = {row.key for row in existing if row.key in wanted}
    for key, alias in wanted.items():
        if key in kept:
            continue
        taken = (
            await session.exec(select(BrandAlias).where(col(BrandAlias.key) == key))
        ).first()
        if taken is not None:
            await session.delete(taken)
            await session.flush()
        session.add(BrandAlias(brand_id=brand.id, alias=alias, key=key))
    await session.flush()
    await _relink_names(session, brand, list(wanted) + [brand_key(brand.name)])
    return list(wanted.values())


async def _relink_names(session: AsyncSession, brand: Brand, keys: list[str]) -> None:
    names = (
        await session.exec(
            select(Product.manufacturer)
            .where(col(Product.manufacturer).is_not(None))
            .distinct()
        )
    ).all()
    matching = [n for n in names if n and brand_key(n) in keys]
    if matching:
        await session.execute(
            update(Product)
            .where(col(Product.manufacturer).in_(matching))
            .values(brand_id=brand.id)
        )


async def merge_brands(session: AsyncSession, source: Brand, target: Brand) -> int:
    """``source`` becomes an alias of ``target``: its products, aliases and
    name move over, then it goes (no commit). Returns the products moved."""
    result = await session.execute(
        update(Product)
        .where(col(Product.brand_id) == source.id)
        .values(brand_id=target.id)
    )
    moved = int(getattr(result, "rowcount", 0) or 0)
    await session.execute(
        update(BrandAlias)
        .where(col(BrandAlias.brand_id) == source.id)
        .values(brand_id=target.id)
    )
    key = brand_key(source.name)
    source_name = source.name
    await session.delete(source)
    await session.flush()
    if key and key != brand_key(target.name):
        taken = (
            await session.exec(select(BrandAlias).where(col(BrandAlias.key) == key))
        ).first()
        if taken is None:
            session.add(BrandAlias(brand_id=target.id, alias=source_name, key=key))
    return moved


__all__ = [
    "brand_key",
    "find_brand",
    "link_unbranded_products",
    "merge_brands",
    "resolve_brand",
    "set_aliases",
    "slugify",
]
