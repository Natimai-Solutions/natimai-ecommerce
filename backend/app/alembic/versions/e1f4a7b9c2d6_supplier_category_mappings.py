"""fournisseurs : mappage des catégories vers la boutique (R4 / S5)

Revision ID: e1f4a7b9c2d6
Revises: d9e3f6a8b1c5
Create Date: 2026-10-01 10:00:00.000000

* ``supplier_category_mappings`` : une règle par couple (catégorie,
  sous-catégorie) d'un fournisseur — catégorie boutique cible et action
  (import / draft / deactivate / skip) ;
* ``suppliers.unmapped_category_action`` : sort de ce qui n'est pas mappé
  (``auto`` = comportement historique, valeur des fournisseurs existants) ;
* ``products.supplier_category`` / ``supplier_subcategory`` élargis à 255
  caractères (les libellés des fichiers dépassaient les 50 d'origine).
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f4a7b9c2d6"
down_revision = "d9e3f6a8b1c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_category_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "supplier_id",
            sa.Uuid(),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_category", sa.String(length=255), nullable=True),
        sa.Column("source_subcategory", sa.String(length=255), nullable=True),
        sa.Column("source_key", sa.String(length=520), nullable=False),
        sa.Column(
            "category_id", sa.Uuid(), sa.ForeignKey("categories.id"), nullable=True
        ),
        sa.Column(
            "action", sa.String(length=20), nullable=False, server_default="import"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "supplier_id", "source_key", name="uq_supplier_category_mapping_key"
        ),
    )
    op.create_index(
        "ix_supplier_category_mappings_supplier_id",
        "supplier_category_mappings",
        ["supplier_id"],
    )
    op.create_index(
        "ix_supplier_category_mappings_category_id",
        "supplier_category_mappings",
        ["category_id"],
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "unmapped_category_action",
            sa.String(length=20),
            nullable=False,
            server_default="auto",
        ),
    )
    for column in ("supplier_category", "supplier_subcategory"):
        op.alter_column(
            "products",
            column,
            type_=sa.String(length=255),
            existing_type=sa.String(length=50),
            existing_nullable=True,
        )


def downgrade() -> None:
    for column in ("supplier_category", "supplier_subcategory"):
        op.execute(
            f"UPDATE products SET {column} = left({column}, 50) "
            f"WHERE length({column}) > 50"
        )
        op.alter_column(
            "products",
            column,
            type_=sa.String(length=50),
            existing_type=sa.String(length=255),
            existing_nullable=True,
        )
    op.drop_column("suppliers", "unmapped_category_action")
    op.drop_index(
        "ix_supplier_category_mappings_category_id",
        table_name="supplier_category_mappings",
    )
    op.drop_index(
        "ix_supplier_category_mappings_supplier_id",
        table_name="supplier_category_mappings",
    )
    op.drop_table("supplier_category_mappings")
