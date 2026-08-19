"""对账域（1 表）"""

from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, SmallInteger, JSON

from app.core.db import Base, utcnow


class ReconciliationDaily(Base):
    __tablename__ = "reconciliation_daily"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    reconcile_date = Column(Date, nullable=False, unique=True)
    stripe_gross = Column(Integer)
    stripe_fee = Column(Integer)
    payments_gross = Column(Integer)
    orders_paid_total = Column(Integer)
    diff_payment = Column(Integer, nullable=False, default=0)
    diff_refund = Column(Integer, nullable=False, default=0)
    points_ledger_sum = Column(Integer)
    users_points_sum = Column(Integer)
    diff_points = Column(Integer, nullable=False, default=0)
    stock_diff_json = Column(JSON)
    status = Column(SmallInteger, nullable=False, default=0)  # 0平 1告警 2已处理
    checked_at = Column(DateTime)
    handled_by = Column(BigInteger)
