"""compteur journalier de vues produit (produits les plus consultés)

La page d'accueil n'avait rien à mettre en avant au-delà des produits
« vedette » choisis à la main. La page produit incrémente une ligne par
produit et par jour ; l'accueil classe sur une fenêtre glissante.

Revision ID: c9e5a3b7d2f4
Revises: b8d4f2a6c7e1
Create Date: 2026-09-10 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c9e5a3b7d2f4"
down_revision = "b8d4f2a6c7e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_view_daily",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "day"),
    )
    op.create_index(
        "ix_product_view_daily_product_id", "product_view_daily", ["product_id"]
    )
    op.create_index("ix_product_view_daily_day", "product_view_daily", ["day"])


def downgrade() -> None:
    op.drop_index("ix_product_view_daily_day", table_name="product_view_daily")
    op.drop_index("ix_product_view_daily_product_id", table_name="product_view_daily")
    op.drop_table("product_view_daily")
