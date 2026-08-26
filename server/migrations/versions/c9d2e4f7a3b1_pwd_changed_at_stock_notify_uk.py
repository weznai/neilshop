"""users.pwd_changed_at + stock_notifications uk(variant_id,email)

Revision ID: c9d2e4f7a3b1
Revises: b7f3a2c9d4e1
Create Date: 2026-08-25 10:00:00.000000

- users.pwd_changed_at：密码重置 token 一次性校验锚点（iat <= pwd_changed_at 即作废）
- stock_notifications 唯一索引：库级拦截并发重复订阅（service 层 IntegrityError 兜底已就位）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d2e4f7a3b1'
down_revision: Union[str, Sequence[str], None] = 'b7f3a2c9d4e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 密码重置/改密时间锚点：nullable，存量用户为空 = 无历史改密记录（token 不受额外限制）
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('pwd_changed_at', sa.DateTime(), nullable=True))
    # 到货通知幂等：并发双击订阅撞唯一索引 → service 捕获 IntegrityError 幂等返回
    op.create_unique_constraint(
        'uk_stock_notify_variant_email',
        'stock_notifications',
        ['variant_id', 'email'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uk_stock_notify_variant_email', 'stock_notifications', type_='unique')
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('pwd_changed_at')
