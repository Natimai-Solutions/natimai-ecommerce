"""allow guest quote requests and add back-office tracking (A11)

``user_id`` et ``cart_id`` deviennent nullables : une demande de devis peut
venir d'un visiteur non connecté, qui n'a ni compte ni panier serveur. Ces
demandes n'étaient jusqu'ici **pas persistées du tout** — elles n'existaient
que sous forme d'email, et un email en échec les perdait définitivement.

S'y ajoutent les colonnes de suivi de l'écran admin : commentaire interne, date
de clôture et auteur de la clôture.

Revision ID: e5f9c3a7b2d8
Revises: c4d8e2a1f9b3
Create Date: 2026-08-27 15:00:00.000000

"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "e5f9c3a7b2d8"
down_revision = "c4d8e2a1f9b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "quote_requests", "user_id", existing_type=sa.Uuid(), nullable=True
    )
    op.alter_column(
        "quote_requests", "cart_id", existing_type=sa.Uuid(), nullable=True
    )
    op.add_column(
        "quote_requests",
        sa.Column(
            "admin_comment", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True
        ),
    )
    op.add_column(
        "quote_requests", sa.Column("handled_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "quote_requests", sa.Column("handled_by_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_quote_requests_handled_by_id_users",
        "quote_requests",
        "users",
        ["handled_by_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_quote_requests_handled_by_id_users", "quote_requests", type_="foreignkey"
    )
    op.drop_column("quote_requests", "handled_by_id")
    op.drop_column("quote_requests", "handled_at")
    op.drop_column("quote_requests", "admin_comment")
    # Les lignes invitées (user_id / cart_id NULL) empêcheraient le retour à
    # NOT NULL : elles sont supprimées, ce qui est la seule issue cohérente
    # puisque la version précédente ne savait pas les représenter.
    op.execute(
        "DELETE FROM quote_requests WHERE user_id IS NULL OR cart_id IS NULL"
    )
    op.alter_column(
        "quote_requests", "cart_id", existing_type=sa.Uuid(), nullable=False
    )
    op.alter_column(
        "quote_requests", "user_id", existing_type=sa.Uuid(), nullable=False
    )
