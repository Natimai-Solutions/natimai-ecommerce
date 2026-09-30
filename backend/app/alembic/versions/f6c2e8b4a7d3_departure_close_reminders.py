"""départs groupés : bons de commande fournisseur, rappels réseaux sociaux

Revision ID: f6c2e8b4a7d3
Revises: e5b3d7a9c4f1
Create Date: 2026-09-25 16:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "f6c2e8b4a7d3"
down_revision = "e5b3d7a9c4f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "grouped_departures", sa.Column("supplier_orders", sa.JSON(), nullable=True)
    )
    op.create_table(
        "departure_reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("grouped_departure_id", sa.Uuid(), nullable=False),
        sa.Column("offset_days", sa.Integer(), nullable=False),
        sa.Column("anchor", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("message_template", sa.String(length=2000), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["grouped_departure_id"], ["grouped_departures.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "grouped_departure_id", "status", "scheduled_at"):
        op.create_index(
            op.f(f"ix_departure_reminders_{column}"),
            "departure_reminders",
            [column],
        )


def downgrade() -> None:
    for column in ("scheduled_at", "status", "grouped_departure_id", "id"):
        op.drop_index(
            op.f(f"ix_departure_reminders_{column}"), table_name="departure_reminders"
        )
    op.drop_table("departure_reminders")
    op.drop_column("grouped_departures", "supplier_orders")
