"""Retrait des notifications en application, jamais branchées

Revision ID: f4b5c6d7e8f9
Revises: e3f4a5b6c7d8
Create Date: 2026-11-19 01:30:00.000000

`notifications` / `user_notifications` n'avaient ni route ni écran : rien ne
les remplissait, seul l'export RGPD les lisait. Le badge de la messagerie se
calcule sur les conversations (chantier accueil et messagerie, décision du
18/11/2026). La migration refuse de supprimer des tables qui contiendraient
des lignes : elles seraient alors utilisées, contrairement à ce qu'on a vu.
"""

import sqlalchemy as sa
from alembic import op

revision = "f4b5c6d7e8f9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in ("user_notifications", "notifications"):
        count = bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
        if count:
            raise RuntimeError(
                f"{table} holds {count} row(s): not dropped. These in-app "
                "notifications were thought unused; check what writes them first."
            )
    op.drop_table("user_notifications")
    op.drop_table("notifications")


def _base() -> list[sa.Column]:
    return [
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
    ]


def downgrade() -> None:
    op.create_table(
        "notifications",
        *_base(),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.String(length=1000), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("action_url", sa.String(length=500), nullable=True),
        sa.Column("action_label", sa.String(length=100), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "order_id", "payment_id", "product_id"):
        op.create_index(f"ix_notifications_{column}", "notifications", [column])
    op.create_table(
        "user_notifications",
        *_base(),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "is_read", "notification_id", "user_id"):
        op.create_index(
            f"ix_user_notifications_{column}", "user_notifications", [column]
        )
