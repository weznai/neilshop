"""order_items 售后未决占用列（rma_pending_qty / ex_pending_qty）

Revision ID: a9c4e2f1d7b3
Revises: b7f3a2c9d4e1
Create Date: 2026-08-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9c4e2f1d7b3'
down_revision: Union[str, Sequence[str], None] = 'b7f3a2c9d4e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 售后未决占用（RMA/换货申请抢占，终态结转 refunded/exchanged 或释放）：
    # 存量行 server_default='0' 保 NOT NULL 加列不破坏既有数据
    with op.batch_alter_table('order_items') as batch_op:
        batch_op.add_column(
            sa.Column('rma_pending_qty', sa.Integer(), nullable=False,
                      server_default='0'),
        )
        batch_op.add_column(
            sa.Column('ex_pending_qty', sa.Integer(), nullable=False,
                      server_default='0'),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('order_items') as batch_op:
        batch_op.drop_column('ex_pending_qty')
        batch_op.drop_column('rma_pending_qty')
