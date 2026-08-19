"""订单/退货域请求模型（reason 取值见 core.enums.RmaReason）"""

from typing import Optional

from pydantic import BaseModel, Field


class CancelRequest(BaseModel):
    reason: Optional[str] = None


class RmaCreateRequest(BaseModel):
    order_no: str
    order_item_id: int
    qty: int = Field(default=1, ge=1)
    reason: int = Field(ge=1, le=6)
    reason_detail: Optional[str] = None
