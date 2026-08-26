"""user_coupons 券包表 + discount_codes.is_claimable

Revision ID: d9e4f2a7c5b1
Revises: a9c4e2f1d7b3
Create Date: 2026-08-26 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9e4f2a7c5b1'
down_revision: Union[str, Sequence[str], None] = 'a9c4e2f1d7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 存量码默认不可领取（server_default 保 NOT NULL 加列不破坏既有数据）
    with op.batch_alter_table('discount_codes') as batch_op:
        batch_op.add_column(
            sa.Column('is_claimable', sa.SmallInteger(), nullable=False,
                      server_default='0'),
        )
    # 用户券包：领取只记持有（唯一约束防重复领取），核销在下单事务 CAS 置已用
    op.create_table(
        'user_coupons',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('code_id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.SmallInteger(), nullable=False),
        sa.Column('claimed_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('order_id', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'code_id', name='uq_user_coupons_user_code'),
    )
    op.create_index('ix_user_coupons_user_id', 'user_coupons', ['user_id'], unique=False)
    op.create_index('ix_user_coupons_code_id', 'user_coupons', ['code_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_user_coupons_code_id', table_name='user_coupons')
    op.drop_index('ix_user_coupons_user_id', table_name='user_coupons')
    op.drop_table('user_coupons')
    with op.batch_alter_table('discount_codes') as batch_op:
        batch_op.drop_column('is_claimable')
