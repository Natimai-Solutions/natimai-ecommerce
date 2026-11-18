"""Accueil : sections ordonnables, réglables et ciblées

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-11-18 23:30:00.000000

Les sections de l'accueil (catégories, coups de cœur, plus consultés) étaient
codées en dur dans la vitrine, après le héros et les bannières. Elles
deviennent des lignes de `homepage_blocks` : l'admin les ordonne, les masque,
leur donne un titre et un public (chantier accueil et messagerie, R1 et R8).

Reprise : les bannières gardent leur ordre, puis viennent les trois sections
d'aujourd'hui, publiées, pour tout le monde. Rien ne change à l'écran.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None

_BUILTIN = (
    ("categories", '{"limit": 8}'),
    ("featured", '{"limit": 8}'),
    ("popular", '{"limit": 8, "days": 30}'),
)


def upgrade() -> None:
    for column in ("config", "audience"):
        op.add_column(
            "homepage_blocks",
            sa.Column(
                column,
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="{}",
            ),
        )
    # One ordering for the whole page: heroes first (the storefront shows the
    # first live one at the top anyway), then the banners in their order.
    op.execute(
        """
        UPDATE homepage_blocks AS b
        SET position = ranked.rank - 1
        FROM (
            SELECT id, row_number() OVER (
                ORDER BY (kind <> 'hero'), position, title, id
            ) AS rank
            FROM homepage_blocks
        ) AS ranked
        WHERE b.id = ranked.id
        """
    )
    for kind, config in _BUILTIN:
        op.execute(
            sa.text(
                """
                INSERT INTO homepage_blocks (
                    id, kind, title, position, is_published, translations,
                    config, audience, is_active, is_admin_active, created_at
                )
                SELECT gen_random_uuid(), :kind, '',
                       COALESCE((SELECT max(position) FROM homepage_blocks), -1)
                       + 1, true, '{}'::jsonb, CAST(:config AS jsonb),
                       '{}'::jsonb, true, true, now()
                """
            ).bindparams(kind=kind, config=config)
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM homepage_blocks "
        "WHERE kind IN ('categories', 'featured', 'popular')"
    )
    op.drop_column("homepage_blocks", "audience")
    op.drop_column("homepage_blocks", "config")
