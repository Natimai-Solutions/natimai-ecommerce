"""add order status workflow fields

Revision ID: d8f3c5a91b2e
Revises: 22abd6580004
Create Date: 2025-12-10 21:03:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'd8f3c5a91b2e'
down_revision = '22abd6580004'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to order_statuses table
    # Note: code starts as nullable to handle existing data, then we'll make it NOT NULL after initial_data.py populates it
    op.add_column('order_statuses', sa.Column('code', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True))
    op.add_column('order_statuses', sa.Column('sequence', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('order_statuses', sa.Column('is_final', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('order_statuses', sa.Column('is_error', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('order_statuses', sa.Column('is_cancellation', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('order_statuses', sa.Column('color', sqlmodel.sql.sqltypes.AutoString(length=7), nullable=False, server_default='#6B7280'))
    op.add_column('order_statuses', sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True))
    
    # Create index on code (will be unique after data population)
    op.create_index(op.f('ix_order_statuses_code'), 'order_statuses', ['code'], unique=False)


def downgrade():
    # Drop index
    op.drop_index(op.f('ix_order_statuses_code'), table_name='order_statuses')
    
    # Drop columns
    op.drop_column('order_statuses', 'description')
    op.drop_column('order_statuses', 'color')
    op.drop_column('order_statuses', 'is_cancellation')
    op.drop_column('order_statuses', 'is_error')
    op.drop_column('order_statuses', 'is_final')
    op.drop_column('order_statuses', 'sequence')
    op.drop_column('order_statuses', 'code')
