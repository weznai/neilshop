"""trade 域 Pydantic DTO —— 结算/支付/后台履约请求模型（金额美分 int）。

由原 app/schemas/checkout.py 与 payments/admin_trade 路由内联 BaseModel 迁入；
app/schemas/checkout.py 保留为 re-export shim。
"""

import re
from typing import Annotated, Any, Dict, List, Optional

from pydantic import AfterValidator, BaseModel, Field

# 轻量邮箱格式校验（strip + 单 @ + 域名含点），非法值 422 invalid_email。
# 不直接用 pydantic EmailStr：email-validator 2.x 默认拒绝 .test/.example 等
# 保留域，开发/测试环境的 glow.test 邮箱会被整站 422。
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_email(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v = v.strip()
    if not _EMAIL_RE.match(v):
        raise ValueError("invalid_email")
    return v


EmailIn = Annotated[str, AfterValidator(_check_email)]


class CartItemIn(BaseModel):
    variant_id: int
    qty: int = Field(default=1, ge=1, le=99)


class PreviewRequest(BaseModel):
    items: Optional[List[CartItemIn]] = None
    country: str = "US"
    state: Optional[str] = None
    code: Optional[str] = None
    points: int = 0
    gift_card_code: Optional[str] = None
    email: Optional[EmailIn] = None
    shipping_method: str = "standard"


class AddressIn(BaseModel):
    full_name: str
    line1: str
    line2: Optional[str] = None
    city: str
    state: Optional[str] = None
    zip: str
    country: str = "US"
    phone: Optional[str] = None


class PlaceRequest(BaseModel):
    email: EmailIn
    address: AddressIn
    shipping_method: str = "standard"
    code: Optional[str] = None
    points: int = 0
    gift_card_code: Optional[str] = None
    note: Optional[str] = None
    gift_flag: int = 0
    gift_message: Optional[str] = None
    utm: Optional[Dict[str, Any]] = None


class CreateIntentRequest(BaseModel):
    order_no: str
    email: Optional[EmailIn] = None


class MockPayRequest(BaseModel):
    order_no: str
    succeed: bool = True
    email: Optional[EmailIn] = None


class WebhookRequest(BaseModel):
    id: str
    type: str
    data: dict


class ShipRequest(BaseModel):
    carrier: str
    tracking_no: str


class RefundRequest(BaseModel):
    amount_cents: Optional[int] = None
    reason: Optional[str] = None


class RmaRejectRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)


class RmaRefundRequest(BaseModel):
    """RMA 退款金额可调：缺省按订单实付比例折算；传值须 >0 且 ≤ 折算可退额"""
    amount_cents: Optional[int] = Field(default=None, ge=1)


class OrderAddressUpdateIn(BaseModel):
    """后台订单改地址：全字段可选部分更新（仅未发货 status≤2 可改，其余 409）"""
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    line1: Optional[str] = Field(default=None, min_length=1, max_length=200)
    line2: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, min_length=1, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    zip: Optional[str] = Field(default=None, min_length=1, max_length=20)
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    phone: Optional[str] = Field(default=None, max_length=30)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class StockAdjustRequest(BaseModel):
    variant_id: int
    change: int
    reason: str


class ShippingRateIn(BaseModel):
    dest_country: str = Field(default="US", min_length=2, max_length=2)
    carrier: str = Field(min_length=1, max_length=30)
    method: str = Field(min_length=1, max_length=50, pattern="^(standard|express)$")
    price: int = Field(ge=0)
    free_over: Optional[int] = Field(default=None, ge=0)
    eta_min_days: int = Field(ge=0, le=60)
    eta_max_days: int = Field(ge=0, le=90)
    max_weight_g: int = Field(default=500, ge=1)


class ShippingRateUpdateIn(BaseModel):
    # 全字段局部更新（exclude_unset 语义：缺省不更新），字段集对齐 ShippingRateIn
    dest_country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    carrier: Optional[str] = Field(default=None, min_length=1, max_length=30)
    method: Optional[str] = Field(default=None, min_length=1, max_length=50,
                                  pattern="^(standard|express)$")
    price: Optional[int] = Field(default=None, ge=0)
    free_over: Optional[int] = Field(default=None, ge=0)
    eta_min_days: Optional[int] = Field(default=None, ge=0, le=60)
    eta_max_days: Optional[int] = Field(default=None, ge=0, le=90)
    max_weight_g: Optional[int] = Field(default=None, ge=1)
    active: Optional[bool] = None


class ExchangeCreateRequest(BaseModel):
    order_no: str
    order_item_id: int
    new_variant_id: int
    qty: int = Field(default=1, ge=1)
    reason: Optional[str] = None
    email: Optional[EmailIn] = None


class ExchangeRejectRequest(BaseModel):
    reason: Optional[str] = None


class ExchangeMockPayIn(BaseModel):
    succeed: bool = True
