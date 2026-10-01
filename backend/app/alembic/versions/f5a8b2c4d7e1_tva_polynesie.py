"""Polynésie : les taux « TGC » deviennent des taux de TVA

Revision ID: f5a8b2c4d7e1
Revises: e4f7a1b3c6d9
Create Date: 2026-09-30 16:00:00.000000

La taxe à la consommation de Polynésie française est la TVA (« TGC » est
celle de Nouvelle-Calédonie). Les taux seedés sous les codes TGC_* sont
renommés (code et libellé d'origine) ; les articles et catégories qui les
référencent par id ne changent pas. Le taux intermédiaire de 13 % est ajouté
par le seed au démarrage suivant. Un libellé déjà modifié par l'admin est
conservé.
"""

import sqlalchemy as sa
from alembic import op

revision = "f5a8b2c4d7e1"
down_revision = "e4f7a1b3c6d9"
branch_labels = None
depends_on = None

_RENAMES = (
    ("TGC_NORMAL", "TVA_NORMALE", "TGC normal", "TVA taux normal"),
    ("TGC_REDUIT", "TVA_REDUITE", "TGC reduit", "TVA taux réduit"),
    ("TGC_EXONERE", "TVA_EXONEREE", "TGC exonere", "Exonéré de TVA"),
)


def _rename(old_code: str, new_code: str, old_label: str, new_label: str) -> None:
    bind = op.get_bind()
    taken = bind.execute(
        sa.text(
            "SELECT 1 FROM tax_rates WHERE territory_code = 'PF' AND code = :code"
        ),
        {"code": new_code},
    ).first()
    if taken is not None:
        return
    bind.execute(
        sa.text(
            "UPDATE tax_rates SET label = :new_label "
            "WHERE territory_code = 'PF' AND code = :old_code AND label = :old_label"
        ),
        {"new_label": new_label, "old_code": old_code, "old_label": old_label},
    )
    bind.execute(
        sa.text(
            "UPDATE tax_rates SET code = :new_code "
            "WHERE territory_code = 'PF' AND code = :old_code"
        ),
        {"new_code": new_code, "old_code": old_code},
    )


def upgrade() -> None:
    for old_code, new_code, old_label, new_label in _RENAMES:
        _rename(old_code, new_code, old_label, new_label)


def downgrade() -> None:
    bind = op.get_bind()
    for old_code, new_code, old_label, new_label in _RENAMES:
        bind.execute(
            sa.text(
                "UPDATE tax_rates SET code = :old_code, "
                "label = CASE WHEN label = :new_label THEN :old_label ELSE label END "
                "WHERE territory_code = 'PF' AND code = :new_code"
            ),
            {
                "old_code": old_code,
                "new_code": new_code,
                "old_label": old_label,
                "new_label": new_label,
            },
        )
