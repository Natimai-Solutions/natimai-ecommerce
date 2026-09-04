"""add invoices.emailed_at (invoice delivery e-mail)

The invoice was issued and stored but never sent: the customer had to know it
existed and go and download it. This column records the delivery, so a replayed
outbox event does not mail the same invoice twice.

Delivery metadata, not invoice content — the ``snapshot`` that the PDF renders
from stays frozen, so the document itself remains immutable.

Revision ID: c8f1a4d6e920
Revises: b7d4e9a2c518
Create Date: 2026-09-02 11:40:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c8f1a4d6e920"
down_revision = "b7d4e9a2c518"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("emailed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "emailed_at")
