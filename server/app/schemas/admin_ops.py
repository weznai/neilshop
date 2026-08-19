from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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


class ReasonIn(BaseModel):
    reason: str


class ReplyIn(BaseModel):
    content: str


class CloseIn(BaseModel):
    close_reason: int | None = None


class AssignIn(BaseModel):
    admin_id: int


class RiskIn(BaseModel):
    flag: int = Field(ge=0, le=2)
