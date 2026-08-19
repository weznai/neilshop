"""营销域（8 表）"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, SmallInteger, String, Text

from app.core.db import Base, utcnow


class DiscountCode(Base):
    __tablename__ = "discount_codes"
    __table_args__ = (Index("idx_active_window", "is_active", "starts_at", "ends_at"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(32), nullable=False, unique=True)  # 存大写
    name = Column(String(100))
    type = Column(SmallInteger, nullable=False)  # 1百分比 2固定 3免邮
    value = Column(Integer, nullable=False)      # type1: 20=20%；type2: 美分
    min_subtotal = Column(Integer, nullable=False, default=0)
    applies_to = Column(JSON)                    # {"category":"nails"}/{"variantIds":[]}
    max_discount = Column(Integer)               # 百分比封顶（美分）
    usage_limit = Column(Integer)
    per_user_limit = Column(Integer, nullable=False, default=1)
    first_order_only = Column(SmallInteger, nullable=False, default=0)
    used_count = Column(Integer, nullable=False, default=0)
    is_stacked = Column(SmallInteger, nullable=False, default=0)  # 可否与积分叠加
    starts_at = Column(DateTime, nullable=False, default=utcnow)
    ends_at = Column(DateTime)
    is_active = Column(SmallInteger, nullable=False, default=1)


class DiscountRedemption(Base):
    __tablename__ = "discount_redemptions"
    __table_args__ = (Index("idx_code_email", "code_id", "email"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code_id = Column(BigInteger, nullable=False, index=True)
    order_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger)
    email = Column(String(191), nullable=False)
    discount_amount = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Bundle(Base):
    __tablename__ = "bundles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(150), nullable=False)
    variant_ids = Column(JSON, nullable=False)
    bundle_price = Column(Integer, nullable=False)
    active = Column(SmallInteger, nullable=False, default=1)
    starts_at = Column(DateTime)
    ends_at = Column(DateTime)


class GiftCard(Base):
    __tablename__ = "gift_cards"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(19), nullable=False, unique=True)  # GC-XXXX-XXXX-XXXX
    initial_amount = Column(Integer, nullable=False)
    balance = Column(Integer, nullable=False)
    status = Column(SmallInteger, nullable=False, default=0, index=True)
    # 0待激活 1有效 2冻结 3用尽 4作废
    purchaser_email = Column(String(191), nullable=False)
    purchaser_order_id = Column(BigInteger)
    recipient_email = Column(String(191))
    expires_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class GiftCardLedger(Base):
    __tablename__ = "gift_card_ledger"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    gift_card_id = Column(BigInteger, nullable=False, index=True)
    order_id = Column(BigInteger)
    change_type = Column(SmallInteger, nullable=False)  # 1激活 2消费冻结 3消费确认 4解冻 5退款返还 6作废
    amount = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (Index("uk_code_email", "code", "invited_email", unique=True),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(20), nullable=False)   # 推荐人码 RF-xxxx
    referrer_user_id = Column(BigInteger, nullable=False, index=True)
    invited_email = Column(String(191), nullable=False)
    invited_user_id = Column(BigInteger)
    first_order_no = Column(String(20))
    status = Column(SmallInteger, nullable=False, default=0)  # 0点击 1注册 2首单待确认 3已奖励 4无效
    reward_referrer = Column(Integer, nullable=False, default=1000)
    reward_invitee = Column(Integer, nullable=False, default=1000)
    rewarded_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    stripe_subscription_id = Column(String(64), nullable=False)
    plan = Column(SmallInteger, nullable=False)  # 1每4周 2每6周 3每8周
    style_mode = Column(SmallInteger, nullable=False, default=1)  # 1自选 2盲盒
    status = Column(SmallInteger, nullable=False, default=1)
    next_billing_at = Column(DateTime, nullable=False, index=True)
    resume_at = Column(DateTime)
    skip_until = Column(DateTime)
    cancel_reason = Column(SmallInteger)  # 1贵 2款式 3囤货 4其他
    created_at = Column(DateTime, nullable=False, default=utcnow)


class PopupConfig(Base):
    __tablename__ = "popup_configs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    scene = Column(String(30), nullable=False, index=True)  # exit_intent/welcome/newsletter
    title = Column(String(200))
    content_md = Column(Text)
    coupon_code = Column(String(32))
    trigger_rules = Column(JSON)  # {"delaySec":7,"exitIntent":true,"mobileOnly":false}
    start_at = Column(DateTime)
    end_at = Column(DateTime)
    active = Column(SmallInteger, nullable=False, default=0)
    stats_shown = Column(Integer, nullable=False, default=0)
    stats_converted = Column(Integer, nullable=False, default=0)
