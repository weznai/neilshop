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
    # 推荐码（/register?ref= 落地页透传，可选）：有效则建立推荐绑定（双方首单后各得 1000 积分）
    ref_code: str | None = Field(default=None, max_length=20)


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
    # 个性化开关：前端 CookieConsent.vue 会提交；模型 CookieConsent 暂无该列（落库需迁移），
    # 此处先接收避免 422 静默丢弃，持久化待列补齐后在 service_account.consent 落库
    personalization: bool = False
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


class PasswordChangeIn(BaseModel):
    """登录态改密（偏好中心入口）：需校验旧密码；匿名 OAuth 用户无旧密可验走重置流"""
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class EmailChangeIn(BaseModel):
    """邮箱修改第 1 步：密码二次验证 + 目标新邮箱（验证码发往新邮箱）"""
    password: str
    new_email: EmailStr


class EmailChangeConfirmIn(BaseModel):
    """邮箱修改第 2 步：新邮箱收到的 6 位数字验证码"""
    code: str = Field(min_length=4, max_length=10)


class OAuthDevLoginIn(BaseModel):
    """dev 环境演示登录（GM_ENV=dev 限定）：按 provider 查找/创建演示账号"""
    provider: str = Field(pattern="^(google|apple)$")
    email: EmailStr | None = None
    name: str | None = Field(default=None, max_length=100)


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
