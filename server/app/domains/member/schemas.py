"""会员域请求模型（Pydantic v2）。

汇集原 app/schemas/account.py、app/schemas/referrals.py、app/schemas/subscriptions.py
及 account 路由内联模型（退订/改密 body）。
"""

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field


# ---------- 账户 ----------

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    birthday: date | None = None


class AddressIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    line1: str = Field(min_length=1, max_length=191)
    line2: str | None = Field(default=None, max_length=191)
    city: str = Field(min_length=1, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    zip: str = Field(min_length=1, max_length=20)
    country: str = Field(default="US", max_length=2)
    phone: str | None = Field(default=None, max_length=32)
    is_default: bool = False


class NewsletterIn(BaseModel):
    email: EmailStr
    source: str = Field(min_length=1, max_length=30)


class ConsentIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=36)
    necessary: bool = True
    analytics: bool = False
    marketing: bool = False
    region: str | None = Field(default=None, max_length=10)


class UnsubscribeIn(BaseModel):
    email: EmailStr
    token: str | None = None


class EmailPreferencesUpdateIn(BaseModel):
    """偏好中心部分更新：仅传需要改的开关，未传字段保持原值。"""
    sub_promo: bool | None = None
    sub_new_arrival: bool | None = None
    sub_cart_abandon: bool | None = None


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetConfirmIn(BaseModel):
    email: EmailStr
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# ---------- 推荐 ----------

class SimulateInviteIn(BaseModel):
    email: EmailStr


# ---------- 订阅 ----------

class SubscriptionCreateIn(BaseModel):
    plan: int = Field(ge=1, le=3)
    style_mode: int = Field(ge=1, le=2)


class SubscriptionPauseIn(BaseModel):
    resume_at: datetime | None = None


class SubscriptionCancelIn(BaseModel):
    cancel_reason: int | None = Field(default=None, ge=1, le=4)


class SubscriptionSkipIn(BaseModel):
    skip_until: datetime
