"""merge the heads of the features-check and lots A to D branches

Revision ID: o6f3b9d2e8a4
Revises: f3d8e1b6c4a2, n5e2a8c3d9f1
Create Date: 2026-09-30 00:00:00.000000

Two branches started from the same head (a7c3e9f1b2d4), each with its own
chain: features-check (stock view, cart abandonment, promo codes, variants)
and lots A to D (grouped departures, drafts, deposits, store credit, price
history). This empty merge revision gives the tree a single head again. No
schema change.
"""

revision = "o6f3b9d2e8a4"
down_revision = ("f3d8e1b6c4a2", "n5e2a8c3d9f1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
