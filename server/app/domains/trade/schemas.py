"""trade 域 Pydantic DTO —— 结算/支付/后台履约请求模型（金额美分 int）。

由原 app/schemas/checkout.py 与 payments/admin_trade 路由内联 BaseModel 迁入；
app/schemas/checkout.py 保留为 re-export shim。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CartItemIn(BaseModel):
    variant_id: int
    qty: int = Field(default=1, ge=1)


class PreviewRequest(BaseModel):
    items: Optional[List[CartItemIn]] = None
    country: str = "US"
    state: Optional[str] = None
    code: Optional[str] = None
    points: int = 0
    gift_card_code: Optional[str] = None
    email: Optional[str] = None
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
    email: str
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


class MockPayRequest(BaseModel):
    order_no: str
    succeed: bool = True


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
    price: Optional[int] = Field(default=None, ge=0)
    free_over: Optional[int] = Field(default=None, ge=0)
    eta_min_days: Optional[int] = Field(default=None, ge=0, le=60)
    eta_max_days: Optional[int] = Field(default=None, ge=0, le=90)
    active: Optional[bool] = None


class ExchangeCreateRequest(BaseModel):
    order_no: str
    order_item_id: int
    new_variant_id: int
    reason: Optional[str] = None
    email: Optional[str] = None


class ExchangeRejectRequest(BaseModel):
    reason: Optional[str] = None
