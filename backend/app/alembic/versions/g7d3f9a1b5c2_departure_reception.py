"""départs groupés : réception par SKU, numéros de série, coûts réels

Revision ID: g7d3f9a1b5c2
Revises: f6c2e8b4a7d3
Create Date: 2026-09-25 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "g7d3f9a1b5c2"
down_revision = "f6c2e8b4a7d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("freight_cost", "customs_cost", "other_costs"):
        op.add_column(
            "grouped_departures",
            sa.Column(column, sa.Numeric(precision=12, scale=2), nullable=True),
        )
    op.add_column("order_lines", sa.Column("serial_numbers", sa.JSON(), nullable=True))
    op.create_table(
        "departure_receipt_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("grouped_departure_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_received", sa.Integer(), nullable=False),
        sa.Column("quantity_damaged", sa.Integer(), nullable=False),
        sa.Column("serial_numbers", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["grouped_departure_id"], ["grouped_departures.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "grouped_departure_id", "product_id", name="uq_receipt_line_product"
        ),
    )
    for column in ("id", "grouped_departure_id", "product_id"):
        op.create_index(
            op.f(f"ix_departure_receipt_lines_{column}"),
            "departure_receipt_lines",
            [column],
        )


def downgrade() -> None:
    for column in ("product_id", "grouped_departure_id", "id"):
        op.drop_index(
            op.f(f"ix_departure_receipt_lines_{column}"),
            table_name="departure_receipt_lines",
        )
    op.drop_table("departure_receipt_lines")
    op.drop_column("order_lines", "serial_numbers")
    for column in ("other_costs", "customs_cost", "freight_cost"):
        op.drop_column("grouped_departures", column)
