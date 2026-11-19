"""Accueil : titre et description pour les moteurs de recherche

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-11-19 13:00:00.000000

Titre et description de l'accueil saisis dans l'admin et traduits, à la
place des textes figés de la vitrine (lot A4, R11). Une seule ligne.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "homepage_seo",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=70), nullable=False),
        sa.Column("description", sa.String(length=170), nullable=False),
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("modify_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("homepage_seo")
