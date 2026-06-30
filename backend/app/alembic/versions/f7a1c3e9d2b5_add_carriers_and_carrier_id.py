"""add carriers table and carrier_id on trackings/consolidations

Revision ID: f7a1c3e9d2b5
Revises: e3f9a1c7b2d4
Create Date: 2026-06-29 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "f7a1c3e9d2b5"
down_revision = "e3f9a1c7b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "carriers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("tracking_url_template", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_carriers_code"), "carriers", ["code"], unique=False)

    op.add_column(
        "shipping_route_trackings",
        sa.Column("carrier_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_shipping_route_trackings_carrier_id"),
        "shipping_route_trackings",
        ["carrier_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_shipping_route_trackings_carrier_id",
        "shipping_route_trackings",
        "carriers",
        ["carrier_id"],
        ["id"],
    )

    op.add_column(
        "shipping_route_tracking_consolidations",
        sa.Column("carrier_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_shipping_route_tracking_consolidations_carrier_id"),
        "shipping_route_tracking_consolidations",
        ["carrier_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_shipping_route_tracking_consolidations_carrier_id",
        "shipping_route_tracking_consolidations",
        "carriers",
        ["carrier_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_shipping_route_tracking_consolidations_carrier_id",
        "shipping_route_tracking_consolidations",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_shipping_route_tracking_consolidations_carrier_id"),
        table_name="shipping_route_tracking_consolidations",
    )
    op.drop_column("shipping_route_tracking_consolidations", "carrier_id")

    op.drop_constraint(
        "fk_shipping_route_trackings_carrier_id",
        "shipping_route_trackings",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_shipping_route_trackings_carrier_id"),
        table_name="shipping_route_trackings",
    )
    op.drop_column("shipping_route_trackings", "carrier_id")

    op.drop_index(op.f("ix_carriers_code"), table_name="carriers")
    op.drop_table("carriers")
