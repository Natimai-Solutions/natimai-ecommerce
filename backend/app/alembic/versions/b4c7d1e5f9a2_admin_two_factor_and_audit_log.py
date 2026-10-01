"""administrateurs : double authentification et journal d'audit (R6)

Revision ID: b4c7d1e5f9a2
Revises: a3b6c9d2e4f8
Create Date: 2026-10-01 16:00:00.000000

* ``users.totp_*`` : secret TOTP chiffré, activation, dernier pas accepté
  (anti-rejeu), empreintes des codes de secours ;
* ``admin_audit_log`` : une ligne par action d'un administrateur (requête
  qui modifie) et par événement de connexion. Sans corps de requête.
"""

import sqlalchemy as sa
from alembic import op

revision = "b4c7d1e5f9a2"
down_revision = "a3b6c9d2e4f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "users", sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("totp_last_step", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("totp_recovery_hashes", sa.JSON(), nullable=True))

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("event", sa.String(length=50), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("path", sa.String(length=500), nullable=True),
        sa.Column("route", sa.String(length=300), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"]
    )
    op.create_index("ix_admin_audit_log_actor_id", "admin_audit_log", ["actor_id"])
    op.create_index("ix_admin_audit_log_event", "admin_audit_log", ["event"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_log_event", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_actor_id", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
    for column in (
        "totp_recovery_hashes",
        "totp_last_step",
        "totp_enabled_at",
        "totp_enabled",
        "totp_secret_encrypted",
    ):
        op.drop_column("users", column)
