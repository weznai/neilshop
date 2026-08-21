"""购物车请求模型（Pydantic v2）。"""

from pydantic import BaseModel, Field


class CartItemIn(BaseModel):
    variant_id: int
    qty: int = Field(ge=1, le=99)


class CartBatchIn(BaseModel):
    items: list[CartItemIn] = Field(max_length=20)


class CartQtyIn(BaseModel):
    qty: int = Field(ge=0, le=99)


class CartMergeIn(BaseModel):
    token: str = Field(min_length=1, max_length=36)
