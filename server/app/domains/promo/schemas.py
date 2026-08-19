"""营销域 Pydantic 输入模型与静态映射表（就近存放）"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

REASON_TEXT = {
    "empty": "请输入折扣码",
    "code_not_found": "折扣码不存在",
    "not_started": "活动未开始",
    "expired": "折扣码已过期",
    "usage_limit": "折扣码已被领完",
    "min_subtotal": "未达到最低消费金额",
    "first_order_only": "仅限首单使用",
    "per_user_limit": "已达到使用次数上限",
    "ok": "",
}


class ValidateIn(BaseModel):
    code: str
    subtotal_cents: int
    email: str | None = None


class GiftcardIn(BaseModel):
    code: str


class GiftcardPurchaseIn(BaseModel):
    amount_cents: Literal[2500, 5000, 10000]
    purchaser_email: EmailStr
    recipient_email: EmailStr | None = None
    message: str | None = Field(default=None, max_length=255)


class DiscountCreateIn(BaseModel):
    code: str
    type: int = Field(ge=1, le=3)
    value: int = Field(ge=0)
    min_subtotal: int = 0
    max_discount: int | None = None
    usage_limit: int | None = None
    per_user_limit: int = 1
    first_order_only: int = 0
    starts_at: datetime
    ends_at: datetime | None = None


class DiscountUpdateIn(BaseModel):
    code: str | None = None
    type: int | None = Field(default=None, ge=1, le=3)
    value: int | None = Field(default=None, ge=0)
    min_subtotal: int | None = None
    max_discount: int | None = None
    usage_limit: int | None = None
    per_user_limit: int | None = None
    first_order_only: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class PopupCreateIn(BaseModel):
    scene: str
    title: str
    content_md: str | None = None
    coupon_code: str | None = None
    trigger_rules: dict | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    active: int = 0


class PopupUpdateIn(BaseModel):
    scene: str | None = None
    title: str | None = None
    content_md: str | None = None
    coupon_code: str | None = None
    trigger_rules: dict | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    active: int | None = None


class SettingIn(BaseModel):
    key: str
    value: Any
