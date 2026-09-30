"""départs groupés (vagues) et rattachement des commandes

Revision ID: b9e4d2c7a1f5
Revises: a7c3e9f1b2d4
Create Date: 2026-09-24 21:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b9e4d2c7a1f5"
down_revision = "a7c3e9f1b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grouped_departures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("order_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estimated_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("departure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("min_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("min_units", sa.Integer(), nullable=True),
        sa.Column("recurrence_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("consolidation_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["consolidation_id"], ["shipping_route_tracking_consolidations.id"]
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "order_cutoff_at", "status", "is_published", "consolidation_id"):
        op.create_index(
            op.f(f"ix_grouped_departures_{column}"),
            "grouped_departures",
            [column],
            unique=False,
        )

    op.add_column(
        "orders", sa.Column("grouped_departure_id", sa.Uuid(), nullable=True)
    )
    op.create_index(
        op.f("ix_orders_grouped_departure_id"),
        "orders",
        ["grouped_departure_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_orders_grouped_departure_id",
        "orders",
        "grouped_departures",
        ["grouped_departure_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_orders_grouped_departure_id", "orders", type_="foreignkey")
    op.drop_index(op.f("ix_orders_grouped_departure_id"), table_name="orders")
    op.drop_column("orders", "grouped_departure_id")
    for column in ("consolidation_id", "is_published", "status", "order_cutoff_at", "id"):
        op.drop_index(
            op.f(f"ix_grouped_departures_{column}"), table_name="grouped_departures"
        )
    op.drop_table("grouped_departures")
