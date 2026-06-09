"""phase3_system_settings

Revision ID: d2e7f5a4b9c3
Revises: c1d6e4f3a8b2
Create Date: 2026-06-08

Creates the system_settings table and seeds the initial
default_display_currency setting (XPF).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e7f5a4b9c3"
down_revision: str | None = "c1d6e4f3a8b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    import uuid
    from datetime import datetime, timezone

    op.create_table(
        "system_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.String(1000), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_system_settings_key"),
    )
    op.create_index("ix_system_settings_key", "system_settings", ["key"])

    # Seed default_display_currency
    settings_table = sa.table(
        "system_settings",
        sa.column("id", sa.UUID()),
        sa.column("key", sa.String()),
        sa.column("value", sa.String()),
        sa.column("description", sa.String()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "id": str(uuid.uuid4()),
                "key": "default_display_currency",
                "value": "XPF",
                "description": "Default currency shown to anonymous visitors and users with no currency preference",
                "updated_at": datetime.now(timezone.utc),
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_system_settings_key", table_name="system_settings")
    op.drop_table("system_settings")
