"""merge the key-specs head with the features-check chain

Revision ID: p7a4c2e9d1b3
Revises: d4e8b1c7f9a2, f3d8e1b6c4a2
Create Date: 2026-09-30 00:00:00.000000

The key-specs tiles (spec_definitions.highlight_rank) and the features-check
branch (stock view, cart abandonment, promo codes, variants) both started
from a7c3e9f1b2d4. This empty merge revision gives the tree a single head
again. No schema change.
"""

revision = "p7a4c2e9d1b3"
down_revision = ("d4e8b1c7f9a2", "f3d8e1b6c4a2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
