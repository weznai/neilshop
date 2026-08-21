"""exchange qty + payments.stripe_checkout_session widen 255

Revision ID: b7f3a2c9d4e1
Revises: 11e1cc89ae3a
Create Date: 2026-08-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f3a2c9d4e1'
down_revision: Union[str, Sequence[str], None] = '11e1cc89ae3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 换货数量：存量行回填默认 1（server_default 保 NOT NULL 加列不破坏既有数据）
    op.add_column(
        'exchanges',
        sa.Column('qty', sa.Integer(), nullable=False, server_default='1'),
    )
    # hosted checkout：session URL 长于 64，扩列宽（batch 兼容 sqlite/MySQL 两方言）
    with op.batch_alter_table('payments') as batch_op:
        batch_op.alter_column(
            'stripe_checkout_session',
            existing_type=sa.String(length=64),
            type_=sa.String(length=255),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('payments') as batch_op:
        batch_op.alter_column(
            'stripe_checkout_session',
            existing_type=sa.String(length=255),
            type_=sa.String(length=64),
            existing_nullable=True,
        )
    op.drop_column('exchanges', 'qty')
