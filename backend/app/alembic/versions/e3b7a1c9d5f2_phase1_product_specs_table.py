"""phase1 product specs filterable table

Revision ID: e3b7a1c9d5f2
Revises: d1e5c3f8a294
Create Date: 2026-05-22 12:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e3b7a1c9d5f2"
down_revision = "d1e5c3f8a294"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_specs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("spec_key", sa.String(length=64), nullable=False),
        sa.Column("value_text", sa.String(length=256), nullable=True),
        sa.Column("value_numeric", sa.Numeric(precision=16, scale=4), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "spec_key", name="uq_product_spec_product_key"),
    )
    op.create_index(op.f("ix_product_specs_id"), "product_specs", ["id"], unique=False)
    op.create_index(
        op.f("ix_product_specs_product_id"), "product_specs", ["product_id"], unique=False
    )
    op.create_index(
        op.f("ix_product_specs_spec_key"), "product_specs", ["spec_key"], unique=False
    )
    # Composite index for numeric range filters (spec_key, value_numeric)
    op.create_index(
        "ix_product_specs_key_numeric",
        "product_specs",
        ["spec_key", "value_numeric"],
        unique=False,
    )
    # Composite index for enum filters (spec_key, value_text)
    op.create_index(
        "ix_product_specs_key_text",
        "product_specs",
        ["spec_key", "value_text"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_specs_key_text", table_name="product_specs")
    op.drop_index("ix_product_specs_key_numeric", table_name="product_specs")
    op.drop_index(op.f("ix_product_specs_spec_key"), table_name="product_specs")
    op.drop_index(op.f("ix_product_specs_product_id"), table_name="product_specs")
    op.drop_index(op.f("ix_product_specs_id"), table_name="product_specs")
    op.drop_table("product_specs")
