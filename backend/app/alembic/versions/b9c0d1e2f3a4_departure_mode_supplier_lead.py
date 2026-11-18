"""Mode d'import d'un départ, délai d'approvisionnement d'un fournisseur

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-11-18 20:00:00.000000

Le délai affiché ignorait le mode d'import choisi et le délai du fournisseur ;
un départ groupé ne portait pas de mode, une commande payée en bateau partait
avec le prochain avion (audit fonctionnel, D1).
"""

import sqlalchemy as sa
from alembic import op

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "grouped_departures",
        sa.Column("service_level", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_grouped_departures_service_level",
        "grouped_departures",
        ["service_level"],
    )
    op.add_column("suppliers", sa.Column("lead_time_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("suppliers", "lead_time_days")
    op.drop_index("ix_grouped_departures_service_level", table_name="grouped_departures")
    op.drop_column("grouped_departures", "service_level")
