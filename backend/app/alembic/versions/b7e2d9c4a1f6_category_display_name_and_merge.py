"""category display_name + merged_into_id (A17 / A12)

``categories.name`` est la clé de rapprochement de la synchronisation
fournisseur : le renommer casserait le rapprochement et la sync recréerait la
catégorie. Le titre vitrine choisi par un admin vit donc dans une colonne à
part, ``display_name`` (NULL = afficher ``name``).

``merged_into_id`` porte la fusion de catégories : la catégorie absorbée reste
en base, inactive, et pointe vers celle qui la remplace — la sync continue
ainsi de résoudre son nom vers la bonne cible au lieu de la recréer.

Revision ID: b7e2d9c4a1f6
Revises: a9c4e1f7b3d2
Create Date: 2026-09-04 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b7e2d9c4a1f6"
down_revision = "a9c4e1f7b3d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("display_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "categories",
        sa.Column("merged_into_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_categories_merged_into_id", "categories", ["merged_into_id"]
    )
    op.create_foreign_key(
        "fk_categories_merged_into_id",
        "categories",
        "categories",
        ["merged_into_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_categories_merged_into_id", "categories", type_="foreignkey")
    op.drop_index("ix_categories_merged_into_id", "categories")
    op.drop_column("categories", "merged_into_id")
    op.drop_column("categories", "display_name")
