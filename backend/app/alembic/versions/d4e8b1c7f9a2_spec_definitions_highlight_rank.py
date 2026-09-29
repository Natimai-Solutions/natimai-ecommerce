"""tuiles « caractéristiques clés » : rang de mise en avant des specs

La fiche produit affiche jusqu'à quatre tuiles (processeur, mémoire,
stockage, écran…). Le choix et l'ordre sont une donnée, éditable par l'admin :
``spec_definitions.highlight_rank`` (1 = première tuile, NULL = pas de tuile).
Les rangs initiaux reprennent spec_definitions.yaml.

Revision ID: d4e8b1c7f9a2
Revises: a7c3e9f1b2d4
Create Date: 2026-09-29 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d4e8b1c7f9a2"
down_revision = "a7c3e9f1b2d4"
branch_labels = None
depends_on = None

# Même ordre que spec_definitions.yaml.
_INITIAL_RANKS = {
    "cpu_family": 1,
    "memory_gb": 2,
    "storage_gb": 3,
    "screen_inches": 4,
    "form_factor": 5,
}


def upgrade() -> None:
    op.add_column(
        "spec_definitions", sa.Column("highlight_rank", sa.Integer(), nullable=True)
    )
    spec_definitions = sa.table(
        "spec_definitions",
        sa.column("key", sa.String()),
        sa.column("highlight_rank", sa.Integer()),
    )
    for key, rank in _INITIAL_RANKS.items():
        op.execute(
            spec_definitions.update()
            .where(spec_definitions.c.key == key)
            .values(highlight_rank=rank)
        )


def downgrade() -> None:
    op.drop_column("spec_definitions", "highlight_rank")
