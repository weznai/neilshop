"""交易域（6 表）—— 购物车主体在 DB（MVP 无 Redis，字段对齐文档镜像表）"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, SmallInteger, String

from app.core.db import Base, utcnow


class Cart(Base):
    __tablename__ = "carts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, unique=True)
    session_id = Column(String(36), unique=True)   # 游客 X-Cart-Token
    email = Column(String(191))                    # 弃购邮件依赖
    items = Column(JSON, nullable=False, default=list)  # [{"variantId":1,"qty":2}]
    abandoned_mails_sent = Column(SmallInteger, nullable=False, default=0)
    recovery_token = Column(String(36))
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow, index=True)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("idx_user_placed", "user_id", "placed_at"),
        Index("idx_status_placed", "status", "placed_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_no = Column(String(20), nullable=False, unique=True)  # NS260814A1B2C3
    user_id = Column(BigInteger)
    email = Column(String(191), nullable=False, index=True)
    status = Column(SmallInteger, nullable=False, default=0)
    shipping_status = Column(SmallInteger, nullable=False, default=0)  # 0未发 1部分 2全发
    currency = Column(String(3), nullable=False, default="USD")
    subtotal = Column(Integer, nullable=False)                 # 美分
    discount_total = Column(Integer, nullable=False, default=0)
    points_discount = Column(Integer, nullable=False, default=0)
    giftcard_discount = Column(Integer, nullable=False, default=0)
    shipping_fee = Column(Integer, nullable=False, default=0)
    tax = Column(Integer, nullable=False, default=0)
    grand_total = Column(Integer, nullable=False)
    shipping_address = Column(JSON, nullable=False)
    discount_code_id = Column(BigInteger)
    points_used = Column(Integer, nullable=False, default=0)
    points_earned = Column(Integer, nullable=False, default=0)
    gift_flag = Column(SmallInteger, nullable=False, default=0)
    gift_message = Column(String(255))
    source = Column(String(20), nullable=False, default="web", index=True)
    utm_json = Column(JSON)
    shipping_method = Column(String(50))                       # standard/express
    note = Column(String(255))
    tracking_no = Column(String(64))                           # 单包冗余，多包看 shipments
    placed_at = Column(DateTime, nullable=False, default=utcnow)
    paid_at = Column(DateTime)
    fulfilled_at = Column(DateTime)
    shipped_at = Column(DateTime)
    delivered_at = Column(DateTime)
    completed_at = Column(DateTime)
    canceled_at = Column(DateTime)
    cancel_reason = Column(String(100))                        # timeout/refund/user/stockout
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, nullable=False, index=True)
    variant_id = Column(BigInteger, nullable=False, index=True)
    product_slug = Column(String(150), nullable=False)         # 快照
    title_snapshot = Column(String(300), nullable=False)       # "Bare Gems · Short Almond"
    image = Column(String(500), nullable=False, default="")
    qty = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False)               # 美分
    subtotal = Column(Integer, nullable=False)
    refunded_qty = Column(Integer, nullable=False, default=0)  # 退货资格 = qty - refunded - exchanged - pending
    exchanged_qty = Column(Integer, nullable=False, default=0)
    rma_pending_qty = Column(Integer, nullable=False, default=0)  # 未决 RMA 占用（申请至终态期间扣减可退量）
    ex_pending_qty = Column(Integer, nullable=False, default=0)   # 未决换货占用（同上，防重复超量申请）
    reviewed = Column(SmallInteger, nullable=False, default=0)


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, nullable=False, index=True)
    provider = Column(SmallInteger, nullable=False)   # 1stripe 2paypal 3klarna 4giftcard 5points
    amount = Column(Integer, nullable=False)
    status = Column(SmallInteger, nullable=False, default=0)
    provider_ref = Column(String(64), index=True)     # PI_xxx / GC-xxx


class Payment(Base):
    __tablename__ = "payments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, nullable=False, index=True)
    # Stripe PI(pi_ 27)/checkout session(cs_ 可达 100+)；hosted 流程两列同存 session id
    stripe_payment_intent = Column(String(191), index=True)
    stripe_checkout_session = Column(String(255))            # checkout session URL / PI secret 快照
    amount = Column(Integer, nullable=False)
    status = Column(SmallInteger, nullable=False, default=0)  # 0待 1成功 2失败 3已退款 4部分退款
    refunded_amount = Column(Integer, nullable=False, default=0)
    failure_reason = Column(String(255))
    raw_event = Column(JSON)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    event_id = Column(String(64), primary_key=True)   # evt_xxx
    source = Column(String(20), nullable=False, default="stripe")
    type = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(SmallInteger, nullable=False, default=0)  # 0待处理 1成功 2失败待重试
    processed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
