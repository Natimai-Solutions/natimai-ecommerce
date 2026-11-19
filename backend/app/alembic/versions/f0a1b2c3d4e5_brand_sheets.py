"""Fiches marque : lien produit → marque, alias, marques à valider

Revision ID: f0a1b2c3d4e5
Revises: e9a0b1c2d3e4
Create Date: 2026-11-19 09:00:00.000000

Chaque produit est rattaché à une fiche marque (``products.brand_id``) à
partir du nom de fabricant donné par le fournisseur ; les graphies voisines
(« HP Inc. », « hp ») se regroupent par une clé normalisée et des alias
(lot BR). Les fabricants existants sont rattachés ici : un nom sans fiche
crée une marque « à valider ».
"""

import re
import unicodedata
import uuid

import sqlalchemy as sa
from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "e9a0b1c2d3e4"
branch_labels = None
depends_on = None

_SUFFIXES = {
    "incorporated", "corporation", "company", "limited", "gmbh", "inc", "corp",
    "ltd", "llc", "co", "sa", "sas", "sarl", "ag", "bv", "plc", "srl", "spa",
}  # fmt: skip


def _key(name: str | None) -> str:
    # Frozen copy of app.features.product.services.brands.brand_key.
    text = (
        unicodedata.normalize("NFKD", (name or "").strip())
        .encode("ascii", "ignore")
        .decode()
    )
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)[:100]


def upgrade() -> None:
    op.add_column("brands", sa.Column("slug", sa.String(length=120), nullable=True))
    op.create_index(op.f("ix_brands_slug"), "brands", ["slug"], unique=True)
    op.add_column("brands", sa.Column("media_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "brands_media_id_fkey",
        "brands",
        "media_assets",
        ["media_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "brands",
        sa.Column(
            "is_validated", sa.Boolean(), server_default="true", nullable=False
        ),
    )
    op.create_table(
        "brand_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=100), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_brand_aliases_brand_id"), "brand_aliases", ["brand_id"], unique=False
    )
    op.create_index(op.f("ix_brand_aliases_key"), "brand_aliases", ["key"], unique=True)
    op.add_column("products", sa.Column("brand_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_products_brand_id"), "products", ["brand_id"], unique=False
    )
    op.create_foreign_key(
        "products_brand_id_fkey",
        "products",
        "brands",
        ["brand_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Backfill: slugs for the existing sheets, then one sheet per manufacturer.
    bind = op.get_bind()
    by_key: dict[str, uuid.UUID] = {}
    used: set[str] = set()

    def slug_for(name: str) -> str:
        base = _key(name).replace(" ", "-")[:120] or "marque"
        slug, n = base, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        return slug

    for brand_id, name in bind.execute(
        sa.text("SELECT id, name FROM brands ORDER BY created_at NULLS LAST, name")
    ).all():
        bind.execute(
            sa.text("UPDATE brands SET slug = :s WHERE id = :i"),
            {"s": slug_for(name), "i": brand_id},
        )
        by_key.setdefault(_key(name), brand_id)

    names = bind.execute(
        sa.text(
            "SELECT DISTINCT manufacturer FROM products "
            "WHERE manufacturer IS NOT NULL AND btrim(manufacturer) <> ''"
        )
    ).scalars()
    for manufacturer in list(names):
        key = _key(manufacturer)
        if not key:
            continue
        brand_id = by_key.get(key)
        if brand_id is None:
            brand_id = uuid.uuid4()
            clean = re.sub(r"\s+", " ", manufacturer.strip())[:100]
            bind.execute(
                sa.text(
                    "INSERT INTO brands (id, name, slug, is_validated, is_active, "
                    "is_admin_active, "
                    "created_at) VALUES (:i, :n, :s, false, true, true, "
                    "now())"
                ),
                {"i": brand_id, "n": clean, "s": slug_for(clean)},
            )
            by_key[key] = brand_id
        bind.execute(
            sa.text("UPDATE products SET brand_id = :b WHERE manufacturer = :m"),
            {"b": brand_id, "m": manufacturer},
        )


def downgrade() -> None:
    op.drop_constraint("products_brand_id_fkey", "products", type_="foreignkey")
    op.drop_index(op.f("ix_products_brand_id"), table_name="products")
    op.drop_column("products", "brand_id")
    op.drop_index(op.f("ix_brand_aliases_key"), table_name="brand_aliases")
    op.drop_index(op.f("ix_brand_aliases_brand_id"), table_name="brand_aliases")
    op.drop_table("brand_aliases")
    # The sheets created from manufacturer names go with the link.
    op.execute("DELETE FROM brands WHERE NOT is_validated")
    op.drop_column("brands", "is_validated")
    op.drop_constraint("brands_media_id_fkey", "brands", type_="foreignkey")
    op.drop_column("brands", "media_id")
    op.drop_index(op.f("ix_brands_slug"), table_name="brands")
    op.drop_column("brands", "slug")
