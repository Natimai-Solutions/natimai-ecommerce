"""médias publics et blocs de la page d'accueil (R2)

Revision ID: a7m3e9d1h5b2
Revises: f4a8c2e6d9b1
Create Date: 2026-09-30 08:00:00.000000

``media_assets`` : images téléversées depuis l'admin, ré-encodées en WebP à
plusieurs largeurs (``variants``) et servies par ``GET /media/…``.
``homepage_blocks`` : le hero et les bannières de l'accueil vitrine, avec une
image de la médiathèque (``media_id``) ou une URL externe, et une fenêtre de
publication.
"""

import sqlalchemy as sa
from alembic import op

revision = "a7m3e9d1h5b2"
down_revision = "f4a8c2e6d9b1"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("alt", sa.String(length=255), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("variants", sa.JSON(), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_media_assets_id"), "media_assets", ["id"])
    op.create_index(op.f("ix_media_assets_kind"), "media_assets", ["kind"])

    op.create_table(
        "homepage_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=500), nullable=True),
        sa.Column("cta_label", sa.String(length=60), nullable=True),
        sa.Column("cta_link", sa.String(length=500), nullable=True),
        sa.Column("media_id", sa.Uuid(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("alt", sa.String(length=255), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["media_id"], ["media_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_homepage_blocks_id"), "homepage_blocks", ["id"])
    op.create_index(op.f("ix_homepage_blocks_kind"), "homepage_blocks", ["kind"])
    op.create_index(op.f("ix_homepage_blocks_media_id"), "homepage_blocks", ["media_id"])
    op.create_index(op.f("ix_homepage_blocks_position"), "homepage_blocks", ["position"])
    op.create_index(
        op.f("ix_homepage_blocks_is_published"), "homepage_blocks", ["is_published"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_homepage_blocks_is_published"), table_name="homepage_blocks")
    op.drop_index(op.f("ix_homepage_blocks_position"), table_name="homepage_blocks")
    op.drop_index(op.f("ix_homepage_blocks_media_id"), table_name="homepage_blocks")
    op.drop_index(op.f("ix_homepage_blocks_kind"), table_name="homepage_blocks")
    op.drop_index(op.f("ix_homepage_blocks_id"), table_name="homepage_blocks")
    op.drop_table("homepage_blocks")
    op.drop_index(op.f("ix_media_assets_kind"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_id"), table_name="media_assets")
    op.drop_table("media_assets")
