"""réglages en base : registre typé (R5)

Revision ID: c5d8e2f6a1b3
Revises: b4c7d1e5f9a2
Create Date: 2026-10-01 18:00:00.000000

* ``system_settings.value`` passe en ``Text`` (instructions de paiement,
  mentions de facture : la limite de 1 000 caractères tombait trop tôt) ;
* ``system_settings.updated_by_id`` : l'administrateur de la dernière
  modification (``SET NULL`` si son compte disparaît).
"""

import sqlalchemy as sa
from alembic import op

revision = "c5d8e2f6a1b3"
down_revision = "b4c7d1e5f9a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "system_settings",
        "value",
        type_=sa.Text(),
        existing_type=sa.String(length=1000),
        existing_nullable=False,
    )
    op.add_column(
        "system_settings", sa.Column("updated_by_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_system_settings_updated_by_id_users",
        "system_settings",
        "users",
        ["updated_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_system_settings_updated_by_id_users", "system_settings", type_="foreignkey"
    )
    op.drop_column("system_settings", "updated_by_id")
    op.alter_column(
        "system_settings",
        "value",
        type_=sa.String(length=1000),
        existing_type=sa.Text(),
        existing_nullable=False,
        postgresql_using="left(value, 1000)",
    )
