"""add_user_refresh_tokens_table

Revision ID: 5c7b6e4a1f29
Revises: 9f17bebf3261
Create Date: 2026-05-08 16:05:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "5c7b6e4a1f29"
down_revision = "9f17bebf3261"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_refresh_tokens",
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("jti", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column(
            "replaced_by_jti", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True
        ),
        sa.Column(
            "revoked_reason", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=True
        ),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_user_refresh_tokens_expires_at"),
        "user_refresh_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_refresh_tokens_id"),
        "user_refresh_tokens",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_refresh_tokens_jti"),
        "user_refresh_tokens",
        ["jti"],
        unique=True,
    )
    op.create_index(
        op.f("ix_user_refresh_tokens_replaced_by_jti"),
        "user_refresh_tokens",
        ["replaced_by_jti"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_refresh_tokens_revoked_at"),
        "user_refresh_tokens",
        ["revoked_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_refresh_tokens_user_id"),
        "user_refresh_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_user_refresh_tokens_user_id"), table_name="user_refresh_tokens")
    op.drop_index(
        op.f("ix_user_refresh_tokens_revoked_at"), table_name="user_refresh_tokens"
    )
    op.drop_index(
        op.f("ix_user_refresh_tokens_replaced_by_jti"),
        table_name="user_refresh_tokens",
    )
    op.drop_index(op.f("ix_user_refresh_tokens_jti"), table_name="user_refresh_tokens")
    op.drop_index(op.f("ix_user_refresh_tokens_id"), table_name="user_refresh_tokens")
    op.drop_index(
        op.f("ix_user_refresh_tokens_expires_at"), table_name="user_refresh_tokens"
    )
    op.drop_table("user_refresh_tokens")
