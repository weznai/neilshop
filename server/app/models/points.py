"""积分域（2 表）"""

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, SmallInteger, String

from app.core.db import Base, utcnow


class PointsLedger(Base):
    __tablename__ = "points_ledger"
    __table_args__ = (
        Index("idx_user_created", "user_id", "created_at"),
        Index("idx_expires", "expires_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    change = Column(Integer, nullable=False)      # 正得负用
    balance_after = Column(Integer, nullable=False)
    reason = Column(SmallInteger, nullable=False)  # 见 PointsReason
    ref_type = Column(String(20))                  # order/review/referral/admin
    ref_id = Column(BigInteger)
    frozen = Column(SmallInteger, nullable=False, default=0)  # 1=冻结中(退货期内)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    user_id = Column(BigInteger, primary_key=True)
    product_id = Column(BigInteger, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
