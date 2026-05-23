"""phase1 pricing tax featured quote

Revision ID: 8c2f1d4a6e90
Revises: 3b5d9a1c7e42
Create Date: 2026-05-18 15:40:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8c2f1d4a6e90"
down_revision = "3b5d9a1c7e42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_groups",
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("margin_rate_pct", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("default", sa.Boolean(), nullable=False),
        sa.Column("requires_validation", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_price_groups_code"),
    )
    op.create_index(op.f("ix_price_groups_code"), "price_groups", ["code"], unique=False)
    op.create_index(op.f("ix_price_groups_default"), "price_groups", ["default"], unique=False)
    op.create_index(op.f("ix_price_groups_id"), "price_groups", ["id"], unique=False)

    op.create_table(
        "tax_rates",
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("rate_pct", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("territory_code", sa.String(length=8), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tax_rates_code"), "tax_rates", ["code"], unique=False)
    op.create_index(op.f("ix_tax_rates_territory_code"), "tax_rates", ["territory_code"], unique=False)
    op.create_index(op.f("ix_tax_rates_id"), "tax_rates", ["id"], unique=False)

    op.create_table(
        "quote_requests",
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("shipping_address", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("items_snapshot", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["cart_id"], ["carts.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_quote_requests_user_id"), "quote_requests", ["user_id"], unique=False)
    op.create_index(op.f("ix_quote_requests_cart_id"), "quote_requests", ["cart_id"], unique=False)
    op.create_index(op.f("ix_quote_requests_id"), "quote_requests", ["id"], unique=False)

    op.add_column("users", sa.Column("price_group_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_users_price_group_id"), "users", ["price_group_id"], unique=False)
    op.create_foreign_key(
        "fk_users_price_group_id_price_groups",
        "users",
        "price_groups",
        ["price_group_id"],
        ["id"],
    )

    op.add_column("categories", sa.Column("default_tax_rate_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_categories_default_tax_rate_id"),
        "categories",
        ["default_tax_rate_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_categories_default_tax_rate_id_tax_rates",
        "categories",
        "tax_rates",
        ["default_tax_rate_id"],
        ["id"],
    )

    op.add_column(
        "products",
        sa.Column(
            "cost_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "cost_currency",
            sa.String(length=10),
            nullable=False,
            server_default="XPF",
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "customs_rate_pct",
            sa.Numeric(precision=8, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column("products", sa.Column("tax_rate_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_products_tax_rate_id"), "products", ["tax_rate_id"], unique=False)
    op.create_foreign_key(
        "fk_products_tax_rate_id_tax_rates",
        "products",
        "tax_rates",
        ["tax_rate_id"],
        ["id"],
    )

    op.add_column(
        "products",
        sa.Column(
            "is_featured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("products", sa.Column("featured_position", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("featured_until", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_products_is_featured"), "products", ["is_featured"], unique=False)
    op.create_index(
        "ix_products_featured_active_window",
        "products",
        ["is_featured", "featured_until", "featured_position"],
        unique=False,
    )

    op.add_column("order_lines", sa.Column("tax_rate_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_order_lines_tax_rate_id"), "order_lines", ["tax_rate_id"], unique=False)
    op.create_foreign_key(
        "fk_order_lines_tax_rate_id_tax_rates",
        "order_lines",
        "tax_rates",
        ["tax_rate_id"],
        ["id"],
    )

    op.alter_column("products", "cost_amount", server_default=None)
    op.alter_column("products", "cost_currency", server_default=None)
    op.alter_column("products", "customs_rate_pct", server_default=None)
    op.alter_column("products", "is_featured", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_order_lines_tax_rate_id_tax_rates", "order_lines", type_="foreignkey")
    op.drop_index(op.f("ix_order_lines_tax_rate_id"), table_name="order_lines")
    op.drop_column("order_lines", "tax_rate_id")

    op.drop_index("ix_products_featured_active_window", table_name="products")
    op.drop_index(op.f("ix_products_is_featured"), table_name="products")
    op.drop_column("products", "featured_until")
    op.drop_column("products", "featured_position")
    op.drop_column("products", "is_featured")

    op.drop_constraint("fk_products_tax_rate_id_tax_rates", "products", type_="foreignkey")
    op.drop_index(op.f("ix_products_tax_rate_id"), table_name="products")
    op.drop_column("products", "tax_rate_id")
    op.drop_column("products", "customs_rate_pct")
    op.drop_column("products", "cost_currency")
    op.drop_column("products", "cost_amount")

    op.drop_constraint(
        "fk_categories_default_tax_rate_id_tax_rates",
        "categories",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_categories_default_tax_rate_id"), table_name="categories")
    op.drop_column("categories", "default_tax_rate_id")

    op.drop_constraint("fk_users_price_group_id_price_groups", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_price_group_id"), table_name="users")
    op.drop_column("users", "price_group_id")

    op.drop_index(op.f("ix_quote_requests_id"), table_name="quote_requests")
    op.drop_index(op.f("ix_quote_requests_cart_id"), table_name="quote_requests")
    op.drop_index(op.f("ix_quote_requests_user_id"), table_name="quote_requests")
    op.drop_table("quote_requests")

    op.drop_index(op.f("ix_tax_rates_id"), table_name="tax_rates")
    op.drop_index(op.f("ix_tax_rates_territory_code"), table_name="tax_rates")
    op.drop_index(op.f("ix_tax_rates_code"), table_name="tax_rates")
    op.drop_table("tax_rates")

    op.drop_index(op.f("ix_price_groups_id"), table_name="price_groups")
    op.drop_index(op.f("ix_price_groups_default"), table_name="price_groups")
    op.drop_index(op.f("ix_price_groups_code"), table_name="price_groups")
    op.drop_table("price_groups")
