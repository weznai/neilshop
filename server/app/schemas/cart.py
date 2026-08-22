"""购物车请求模型（Pydantic v2）；CartItemIn 统一由 trade 域定义 re-export。"""

from pydantic import BaseModel, Field

from app.domains.trade.schemas import CartItemIn  # noqa: F401


class CartBatchIn(BaseModel):
    items: list[CartItemIn] = Field(max_length=20)


class CartQtyIn(BaseModel):
    qty: int = Field(ge=0, le=99)


class CartMergeIn(BaseModel):
    token: str = Field(min_length=1, max_length=36)
