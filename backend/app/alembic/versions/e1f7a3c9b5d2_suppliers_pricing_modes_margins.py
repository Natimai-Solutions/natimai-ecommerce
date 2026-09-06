"""suppliers en base, modes de prix et marges par catégorie

S'enchaîne après ``a7d2e9f4b1c6`` (entrepôt principal, régime douanier d'origine
et dropshipping sur ``places``) — les deux chaînes ne touchent pas les mêmes
tables ; la fusion des trois têtes du 04/09 est ``e2b7c4d9a1f3``. Puis :

* crée la table ``suppliers`` — un fournisseur est désormais une ligne que
  l'admin déclare (entrepôt d'origine, régime douanier, méthode
  d'approvisionnement manual / file / api) et non plus une classe plus des
  variables ``.env`` ; la ligne ``ingram_micro`` est amorcée pour que les
  produits existants (``supplier_name = 'ingram_micro'``) restent rattachés ;
* ``products.pricing_mode`` : ``import`` (CAF + douane, comportement
  historique, appliqué à toutes les lignes existantes), ``domestic`` (coût +
  marge + taxe, sans douane ni fret import : entrepôt local ou fournisseur du
  même territoire douanier) ou ``fixed`` (``base_price`` est le prix TTC
  saisi) ;
* ``products.margin_rate_pct`` et ``categories.default_margin_rate_pct`` :
  la marge se résout produit → catégorie → groupe tarifaire.

Revision ID: e1f7a3c9b5d2
Revises: a7d2e9f4b1c6
Create Date: 2026-09-05 10:00:00.000000

"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "e1f7a3c9b5d2"
down_revision = "a7d2e9f4b1c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- suppliers ---------------------------------------------------------
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column("adapter_key", sa.String(length=50), nullable=True),
        sa.Column("origin_place_id", sa.Uuid(), nullable=True),
        sa.Column(
            "is_domestic",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "sync_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "sync_interval_hours",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("default_categories", sa.JSON(), nullable=True),
        sa.Column("price_currency", sa.String(length=3), nullable=True),
        sa.Column("column_mapping", sa.JSON(), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["origin_place_id"], ["places.id"], name="fk_suppliers_origin_place_id"
        ),
        sa.UniqueConstraint("code", name="uq_suppliers_code"),
    )
    op.create_index("ix_suppliers_code", "suppliers", ["code"])
    op.create_index("ix_suppliers_origin_place_id", "suppliers", ["origin_place_id"])

    # --- products / categories --------------------------------------------
    op.add_column(
        "products",
        sa.Column(
            "pricing_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'import'"),
        ),
    )
    op.add_column(
        "products",
        sa.Column("margin_rate_pct", sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.create_index("ix_products_pricing_mode", "products", ["pricing_mode"])
    op.add_column(
        "categories",
        sa.Column(
            "default_margin_rate_pct", sa.Numeric(precision=8, scale=2), nullable=True
        ),
    )

    # --- amorçage : le distributeur historique ----------------------------
    # Les produits synchronisés portent déjà supplier_name = 'ingram_micro' ;
    # sans cette ligne ils n'auraient plus de fournisseur résolu. L'entrepôt
    # d'origine est celui semé par initial_data (FR_SUPPLIERS) s'il existe
    # déjà ; sinon initial_data le complètera au prochain démarrage.
    bind = op.get_bind()
    origin_id = bind.execute(
        sa.text("SELECT id FROM places WHERE code = 'FR_SUPPLIERS' LIMIT 1")
    ).scalar()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    suppliers = sa.table(
        "suppliers",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("kind", sa.String()),
        sa.column("adapter_key", sa.String()),
        sa.column("origin_place_id", sa.Uuid()),
        sa.column("is_domestic", sa.Boolean()),
        sa.column("sync_enabled", sa.Boolean()),
        sa.column("sync_interval_hours", sa.Integer()),
        sa.column("default_categories", sa.JSON()),
        sa.column("price_currency", sa.String()),
        sa.column("settings", sa.JSON()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        suppliers,
        [
            {
                "id": uuid.uuid4(),
                "code": "ingram_micro",
                "name": "Ingram Micro",
                "kind": "api",
                "adapter_key": "ingram_micro",
                "origin_place_id": origin_id,
                "is_domestic": False,
                "sync_enabled": True,
                "sync_interval_hours": 6,
                "default_categories": ["Ordinateur/Serveur"],
                "price_currency": None,
                "settings": {"environment": "sandbox", "country_code": "FR"},
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_column("categories", "default_margin_rate_pct")
    op.drop_index("ix_products_pricing_mode", table_name="products")
    op.drop_column("products", "margin_rate_pct")
    op.drop_column("products", "pricing_mode")
    op.drop_index("ix_suppliers_origin_place_id", table_name="suppliers")
    op.drop_index("ix_suppliers_code", table_name="suppliers")
    op.drop_table("suppliers")
