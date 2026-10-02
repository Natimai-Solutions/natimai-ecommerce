"""caractéristiques saisies à la main (R9 / T4) : product_specs.source

Revision ID: r9c6e4a2f3b5
Revises: q8b5d3f1e2a4
Create Date: 2026-10-02 04:00:00.000000

``source`` dit d'où vient une ligne de ``product_specs`` : ``icecat`` (projection
des données Icecat, réécrite à chaque enrichissement) ou ``manual`` (saisie
dans la fiche produit, jamais réécrite par la projection).
"""

import sqlalchemy as sa
from alembic import op

revision = "r9c6e4a2f3b5"
down_revision = "q8b5d3f1e2a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_specs",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="icecat",
        ),
    )
    op.create_index(op.f("ix_product_specs_source"), "product_specs", ["source"])


def downgrade() -> None:
    op.drop_index(op.f("ix_product_specs_source"), table_name="product_specs")
    op.drop_column("product_specs", "source")
