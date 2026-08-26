"""payments.stripe_payment_intent widen 191 (hosted checkout cs_ ids)

Revision ID: e3f5a8c1d2b4
Revises: f2a4c6d8e0b1
Create Date: 2026-08-26 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f5a8c1d2b4'
down_revision: Union[str, Sequence[str], None] = 'f2a4c6d8e0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # hosted checkout：Payment 行主键口径改存 checkout session id（cs_test_… 66 字符，
    # live cs_ 更长），64 放不下 → 扩 191（batch 兼容 sqlite/MySQL 两方言）
    with op.batch_alter_table('payments') as batch_op:
        batch_op.alter_column(
            'stripe_payment_intent',
            existing_type=sa.String(length=64),
            type_=sa.String(length=191),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('payments') as batch_op:
        batch_op.alter_column(
            'stripe_payment_intent',
            existing_type=sa.String(length=191),
            type_=sa.String(length=64),
            existing_nullable=True,
        )
