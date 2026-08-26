"""member 扩展：邮箱修改验证码表 email_change_requests + users 第三方登录绑定列

- email_change_requests：双步邮箱修改的 6 位数字码（10 分钟有效，同用户新请求作废旧码）
- users.oauth_provider / oauth_subject：google/apple 登录定位（组合索引）

Revision ID: c7e9d2b4a6f8
Revises: a9c4e2f1d7b3
Create Date: 2026-08-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e9d2b4a6f8'
down_revision: Union[str, Sequence[str], None] = 'a9c4e2f1d7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'email_change_requests',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('new_email', sa.String(191), nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table('email_change_requests') as batch_op:
        batch_op.create_index('idx_ecr_user_created', ['user_id', 'created_at'])
        batch_op.create_index(
            op.f('ix_email_change_requests_user_id'), ['user_id'])
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('oauth_provider', sa.String(20)))
        batch_op.add_column(sa.Column('oauth_subject', sa.String(191)))
        batch_op.create_index('idx_user_oauth', ['oauth_provider', 'oauth_subject'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_index('idx_user_oauth')
        batch_op.drop_column('oauth_subject')
        batch_op.drop_column('oauth_provider')
    with op.batch_alter_table('email_change_requests') as batch_op:
        batch_op.drop_index(op.f('ix_email_change_requests_user_id'))
        batch_op.drop_index('idx_ecr_user_created')
    op.drop_table('email_change_requests')
