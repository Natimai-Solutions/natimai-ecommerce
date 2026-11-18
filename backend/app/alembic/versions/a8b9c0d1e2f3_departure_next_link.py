"""Lien d'un départ récurrent vers son suivant

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-11-18 19:00:00.000000

Un départ resté ouvert sous son seuil après sa date limite ne recevait plus
de commandes, et aucun autre départ n'était ouvert : les nouvelles commandes
n'étaient rattachées à aucun départ. Le suivant d'un départ récurrent est
désormais ouvert d'avance (décision du 18/11/2026, option B) ; le lien évite
qu'une clôture ultérieure en crée un second.
"""

import sqlalchemy as sa
from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "grouped_departures",
        sa.Column("next_departure_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_grouped_departures_next_departure_id",
        "grouped_departures",
        "grouped_departures",
        ["next_departure_id"],
        ["id"],
    )
    op.create_index(
        "ix_grouped_departures_next_departure_id",
        "grouped_departures",
        ["next_departure_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_grouped_departures_next_departure_id", table_name="grouped_departures"
    )
    op.drop_constraint(
        "fk_grouped_departures_next_departure_id",
        "grouped_departures",
        type_="foreignkey",
    )
    op.drop_column("grouped_departures", "next_departure_id")
