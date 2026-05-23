"""add supplier mapping uniqueness and products supplier_name index

Revision ID: f1e9c2a7b4d1
Revises: e8c4a2d6f1b0
Create Date: 2026-05-12 16:30:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f1e9c2a7b4d1"
down_revision = "e8c4a2d6f1b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the most recent row per (supplier_name, supplier_sku) before adding
    # the uniqueness constraint.
    op.execute(
        """
        DELETE FROM supplier_product_mappings spm
        USING (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY supplier_name, supplier_sku
                        ORDER BY last_synced DESC, updated_at DESC, created_at DESC, id DESC
                    ) AS row_num
                FROM supplier_product_mappings
            ) ranked
            WHERE ranked.row_num > 1
        ) duplicates
        WHERE spm.id = duplicates.id
        """
    )

    op.create_unique_constraint(
        op.f("uq_supplier_product_mappings_supplier_name_supplier_sku"),
        "supplier_product_mappings",
        ["supplier_name", "supplier_sku"],
    )
    op.create_index(
        op.f("ix_products_supplier_name"),
        "products",
        ["supplier_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_products_supplier_name"), table_name="products")
    op.drop_constraint(
        op.f("uq_supplier_product_mappings_supplier_name_supplier_sku"),
        "supplier_product_mappings",
        type_="unique",
    )
