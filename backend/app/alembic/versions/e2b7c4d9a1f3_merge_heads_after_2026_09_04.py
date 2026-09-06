"""merge the three heads left by the 2026-09-04 merges

Revision ID: e2b7c4d9a1f3
Revises: b3f7d1e6c8a4, b7e2d9c4a1f6, d3b8c5f1a742
Create Date: 2026-09-05 00:00:00.000000

Three branches were merged into main on 2026-09-04, each carrying its own
migration on top of a9c4e1f7b3d2 (F3 customs fees, category display_name,
credit notes). ``alembic upgrade head`` refused the ambiguity; this empty
merge revision gives the tree a single head again. No schema change.
"""

revision = "e2b7c4d9a1f3"
down_revision = ("b3f7d1e6c8a4", "b7e2d9c4a1f6", "d3b8c5f1a742")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
