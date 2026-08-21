"""履约域（5 表）"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, SmallInteger, String

from app.core.db import Base, utcnow


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    shipment_no = Column(String(16), nullable=False, unique=True)  # SP260814xxxx
    order_id = Column(BigInteger, nullable=False, index=True)
    carrier = Column(String(30), nullable=False)   # usps/ups/dhl
    tracking_no = Column(String(64), nullable=False, index=True)
    label_url = Column(String(500))
    label_cost = Column(Integer)
    status = Column(SmallInteger, nullable=False, default=0, index=True)
    item_json = Column(JSON, nullable=False, default=list)  # [{orderItemId,qty}]
    shipped_at = Column(DateTime)
    delivered_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Rma(Base):
    __tablename__ = "returns"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rma_no = Column(String(16), nullable=False, unique=True)  # RMA260814AB12
    order_id = Column(BigInteger, nullable=False, index=True)
    order_item_id = Column(BigInteger, nullable=False)
    qty = Column(Integer, nullable=False)
    reason = Column(SmallInteger, nullable=False, index=True)  # 1尺码 2质量 3不喜欢 4损坏 5发错 6其他
    reason_detail = Column(String(500))
    status = Column(SmallInteger, nullable=False, default=0, index=True)
    label_url = Column(String(500))
    label_cost = Column(Integer)
    refund_amount = Column(Integer)                 # 实退（美分）
    refund_shipping = Column(Integer, nullable=False, default=0)
    restock_qty = Column(Integer, nullable=False, default=0)
    received_at = Column(DateTime)
    refunded_at = Column(DateTime)
    handled_by = Column(BigInteger)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Exchange(Base):
    __tablename__ = "exchanges"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange_no = Column(String(16), nullable=False, unique=True)
    order_id = Column(BigInteger, nullable=False, index=True)
    order_item_id = Column(BigInteger, nullable=False)
    old_variant_id = Column(BigInteger, nullable=False)
    new_variant_id = Column(BigInteger, nullable=False)
    qty = Column(Integer, nullable=False, default=1)         # 换货数量（1..可换量）
    price_diff = Column(Integer, nullable=False, default=0)  # 正补差/负退差/0（已乘 qty）
    status = Column(SmallInteger, nullable=False, default=0)
    shipment_id = Column(BigInteger)
    diff_payment_id = Column(BigInteger)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class OrderTimeline(Base):
    __tablename__ = "order_timeline"
    __table_args__ = (Index("idx_order_created", "order_id", "created_at"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, nullable=False)
    event = Column(String(50), nullable=False)
    # status_changed/payment_succeeded/refund_issued/rma_created/shipment_created/
    # tracking_updated/note_added/email_sent/ticket_linked/label_voided/points_granted
    detail = Column(JSON)
    actor = Column(String(20), nullable=False, default="system")  # system/admin/user
    created_at = Column(DateTime, nullable=False, default=utcnow)


class ShippingRate(Base):
    __tablename__ = "shipping_rates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dest_country = Column(String(2), nullable=False, default="US", index=True)
    carrier = Column(String(30), nullable=False)
    method = Column(String(50), nullable=False)   # standard/express
    min_weight_g = Column(Integer, nullable=False, default=0)
    max_weight_g = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    free_over = Column(Integer)                   # 满额免邮阈值（美分）
    eta_min_days = Column(SmallInteger, nullable=False)
    eta_max_days = Column(SmallInteger, nullable=False)
    active = Column(SmallInteger, nullable=False, default=1)
