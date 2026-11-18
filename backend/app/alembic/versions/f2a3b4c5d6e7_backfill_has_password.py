"""has_password des comptes existants, là où la réponse est connue

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-17 09:00:00.000000

La colonne restait inconnue (NULL) pour tous les comptes d'avant : un compte
ouvert avec un mot de passe qui se lie ensuite à Google / Microsoft se
supprimait encore sur la foi d'une connexion récente (relecture du
17/11/2026). Un compte non invité, sans lien OAuth et qui s'est déjà connecté
n'a pu le faire qu'avec un mot de passe.
"""

from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET has_password = TRUE
        WHERE has_password IS NULL
          AND is_guest = FALSE
          AND last_login IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM user_oauth_links l WHERE l.user_id = users.id
          )
        """
    )


def downgrade() -> None:
    # Nothing to undo: the value is true, and the column goes with e1f2a3b4c5d6.
    pass
