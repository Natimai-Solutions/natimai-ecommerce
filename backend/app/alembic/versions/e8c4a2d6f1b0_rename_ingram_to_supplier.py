"""rename ingram_* tracking tables to supplier_* (multi-supplier support)

Renames the Ingram-specific synchronization tables to supplier-agnostic ones and
adds an indexed ``supplier_name`` column (back-filled with ``"ingram_micro"``).

Revision ID: e8c4a2d6f1b0
Revises: d3f1a7b2c8e4
Create Date: 2026-05-12 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e8c4a2d6f1b0"
down_revision = "d3f1a7b2c8e4"
branch_labels = None
depends_on = None

_LEGACY_SUPPLIER = "ingram_micro"


def upgrade():
    # --- ingram_sync_logs -> supplier_sync_logs ---------------------------
    op.rename_table("ingram_sync_logs", "supplier_sync_logs")
    op.add_column(
        "supplier_sync_logs",
        sa.Column(
            "supplier_name",
            sa.String(),
            nullable=False,
            server_default=_LEGACY_SUPPLIER,
        ),
    )
    op.alter_column("supplier_sync_logs", "supplier_name", server_default=None)
    op.create_index(
        op.f("ix_supplier_sync_logs_supplier_name"),
        "supplier_sync_logs",
        ["supplier_name"],
        unique=False,
    )

    # --- ingram_product_mappings -> supplier_product_mappings -------------
    op.drop_index(
        op.f("ix_ingram_product_mappings_ingram_sku"),
        table_name="ingram_product_mappings",
    )
    op.drop_index(
        op.f("ix_ingram_product_mappings_local_product_id"),
        table_name="ingram_product_mappings",
    )
    op.rename_table("ingram_product_mappings", "supplier_product_mappings")
    op.alter_column(
        "supplier_product_mappings", "ingram_sku", new_column_name="supplier_sku"
    )
    op.add_column(
        "supplier_product_mappings",
        sa.Column(
            "supplier_name",
            sa.String(),
            nullable=False,
            server_default=_LEGACY_SUPPLIER,
        ),
    )
    op.alter_column("supplier_product_mappings", "supplier_name", server_default=None)
    op.alter_column(
        "supplier_product_mappings",
        "vendor_part_number",
        existing_type=sa.String(),
        nullable=True,
    )
    op.alter_column(
        "supplier_product_mappings",
        "manufacturer",
        existing_type=sa.String(),
        nullable=True,
    )
    op.create_index(
        op.f("ix_supplier_product_mappings_supplier_name"),
        "supplier_product_mappings",
        ["supplier_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_product_mappings_supplier_sku"),
        "supplier_product_mappings",
        ["supplier_sku"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_product_mappings_local_product_id"),
        "supplier_product_mappings",
        ["local_product_id"],
        unique=False,
    )


def downgrade():
    # --- supplier_product_mappings -> ingram_product_mappings ------------
    op.drop_index(
        op.f("ix_supplier_product_mappings_local_product_id"),
        table_name="supplier_product_mappings",
    )
    op.drop_index(
        op.f("ix_supplier_product_mappings_supplier_sku"),
        table_name="supplier_product_mappings",
    )
    op.drop_index(
        op.f("ix_supplier_product_mappings_supplier_name"),
        table_name="supplier_product_mappings",
    )
    op.alter_column(
        "supplier_product_mappings",
        "manufacturer",
        existing_type=sa.String(),
        nullable=False,
    )
    op.alter_column(
        "supplier_product_mappings",
        "vendor_part_number",
        existing_type=sa.String(),
        nullable=False,
    )
    op.drop_column("supplier_product_mappings", "supplier_name")
    op.alter_column(
        "supplier_product_mappings", "supplier_sku", new_column_name="ingram_sku"
    )
    op.rename_table("supplier_product_mappings", "ingram_product_mappings")
    op.create_index(
        op.f("ix_ingram_product_mappings_local_product_id"),
        "ingram_product_mappings",
        ["local_product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingram_product_mappings_ingram_sku"),
        "ingram_product_mappings",
        ["ingram_sku"],
        unique=False,
    )

    # --- supplier_sync_logs -> ingram_sync_logs --------------------------
    op.drop_index(
        op.f("ix_supplier_sync_logs_supplier_name"),
        table_name="supplier_sync_logs",
    )
    op.drop_column("supplier_sync_logs", "supplier_name")
    op.rename_table("supplier_sync_logs", "ingram_sync_logs")
