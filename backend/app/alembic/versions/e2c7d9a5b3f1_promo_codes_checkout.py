"""codes promo appliqués au checkout

Le modèle `discounts` existait (CRUD, validation d'un code) sans jamais
toucher une commande : le checkout figeait discount_amount à 0. Il gagne
une remise en montant fixe (alternative au pourcentage), un minimum de
commande, une limite par client et une unicité du code insensible à la
casse ; la commande garde la remise appliquée (code, montant, référence).

Revision ID: e2c7d9a5b3f1
Revises: d1f6b8c4a9e2
Create Date: 2026-09-10 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e2c7d9a5b3f1"
down_revision = "d1f6b8c4a9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("discounts", "percentage", existing_type=sa.Numeric(5, 2), nullable=True)
    op.add_column("discounts", sa.Column("amount", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "discounts", sa.Column("min_order_amount", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "discounts", sa.Column("max_uses_per_customer", sa.Integer(), nullable=True)
    )
    op.execute("UPDATE discounts SET code = upper(trim(code)) WHERE code IS NOT NULL")
    op.execute(
        "CREATE UNIQUE INDEX ux_discounts_code_ci ON discounts (upper(code)) "
        "WHERE code IS NOT NULL"
    )

    op.add_column("orders", sa.Column("discount_id", sa.Uuid(), nullable=True))
    op.add_column(
        "orders", sa.Column("discount_code", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "orders",
        sa.Column(
            "discount_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_foreign_key(
        "fk_orders_discount_id", "orders", "discounts", ["discount_id"], ["id"]
    )
    op.create_index("ix_orders_discount_id", "orders", ["discount_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_discount_id", table_name="orders")
    op.drop_constraint("fk_orders_discount_id", "orders", type_="foreignkey")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "discount_code")
    op.drop_column("orders", "discount_id")
    op.execute("DROP INDEX IF EXISTS ux_discounts_code_ci")
    op.drop_column("discounts", "max_uses_per_customer")
    op.drop_column("discounts", "min_order_amount")
    op.drop_column("discounts", "amount")
    op.alter_column("discounts", "percentage", existing_type=sa.Numeric(5, 2), nullable=False)
