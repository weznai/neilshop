"""用户域（5 表）—— 金额美分；枚举见 core.enums"""

from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, SmallInteger, String

from app.core.db import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(191), nullable=False, unique=True, index=True)
    password_hash = Column(String(255))  # NULL=纯OAuth
    google_id = Column(String(64), unique=True)
    name = Column(String(100), nullable=False, default="")
    role = Column(SmallInteger, nullable=False, default=0)  # 0顾客 1客服 2运营 3仓库 4美甲师 9超管
    # 美甲师（role=4）公开简介：前台聊天窗美甲师列表展示（ensure_schema 幂等补列）
    artist_intro = Column(String(300), nullable=False, default="")
    points = Column(Integer, nullable=False, default=0)     # 冗余余额，真相在 points_ledger
    birthday = Column(Date)
    tier = Column(SmallInteger, nullable=False, default=0)  # 0普通 1银 2金
    tier_updated_at = Column(DateTime)
    risk_flag = Column(SmallInteger, nullable=False, default=0)  # 0正常 1关注 2黑名单
    total_spent = Column(Integer, nullable=False, default=0)     # 美分
    last_order_at = Column(DateTime, index=True)
    status = Column(SmallInteger, nullable=False, default=1)     # 1正常 0禁用 -1注销
    email_verified_at = Column(DateTime)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class UserAddress(Base):
    __tablename__ = "user_addresses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    line1 = Column(String(191), nullable=False)
    line2 = Column(String(191))
    city = Column(String(100), nullable=False)
    state = Column(String(100))
    zip = Column(String(20), nullable=False)
    country = Column(String(2), nullable=False, default="US")
    phone = Column(String(32))
    is_default = Column(SmallInteger, nullable=False, default=0)
    verified = Column(SmallInteger, nullable=False, default=0)


class EmailPreference(Base):
    __tablename__ = "email_preferences"

    email = Column(String(191), primary_key=True)
    user_id = Column(BigInteger)
    sub_promo = Column(SmallInteger, nullable=False, default=1)
    sub_new_arrival = Column(SmallInteger, nullable=False, default=1)
    sub_cart_abandon = Column(SmallInteger, nullable=False, default=1)
    unsubscribed_at = Column(DateTime)
    source = Column(String(30))  # popup/checkout/account
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class CookieConsent(Base):
    __tablename__ = "cookie_consents"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(36), nullable=False, index=True)
    user_id = Column(BigInteger)
    necessary = Column(SmallInteger, nullable=False, default=1)
    analytics = Column(SmallInteger, nullable=False, default=0)
    marketing = Column(SmallInteger, nullable=False, default=0)
    region = Column(String(10))
    created_at = Column(DateTime, nullable=False, default=utcnow)


class DataRequest(Base):
    __tablename__ = "data_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    type = Column(SmallInteger, nullable=False)      # 1导出 2删除
    status = Column(SmallInteger, nullable=False, default=0)  # 0受理 1完成
    fulfilled_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
