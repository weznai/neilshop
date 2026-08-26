"""用户订单路由（薄路由）—— 列表/详情/待付取消/物流轨迹/改址；业务在 service_orders。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, get_current_user_optional
from app.domains.trade import service_orders
from app.models import User
from app.schemas.orders import CancelRequest

router = APIRouter(prefix="/api/orders", tags=["orders"])


class OrderAddressBody(BaseModel):
    """用户侧订单改址（整对象重建）：字段宽度对齐后台 OrderAddressUpdateIn"""
    full_name: str = Field(min_length=1, max_length=100)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    zip: str = Field(min_length=1, max_length=20)
    country: str = Field(min_length=2, max_length=2)
    phone: str | None = Field(default=None, max_length=32)


@router.get("")
@router.get("/")
def list_orders(
    status: Optional[int] = None,
    q: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_orders.list_orders(db, user, status, page, q)


@router.get("/track")
def track(
    no: str = Query(...),
    email: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """物流轨迹：登录属主免 email（会话即可）；游客必须 email 双因子。"""
    return service_orders.track(db, no, email, user)


@router.get("/{order_no}")
def order_detail(
    order_no: str,
    email: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return service_orders.order_detail(db, order_no, email, user)


@router.post("/{order_no}/cancel")
def cancel_order(
    order_no: str,
    body: CancelRequest | None = None,
    email: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """登录用户按属主取消；游客（未登录）以 email 双因子取消（与订单详情同口径）。"""
    return service_orders.cancel_order(
        db, order_no, user, email, reason=body.reason if body else None)


@router.put("/{order_no}/address")
def update_order_address(
    order_no: str,
    body: OrderAddressBody,
    email: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """修改未发货订单收货地址：登录属主 或 游客 ?email= 双因子（与详情同判定）；
    仅 status∈(0,1,2) 且未发货可改，其余 409 not_editable。"""
    return service_orders.update_order_address(db, order_no, body, user, email)


@router.post("/{order_no}/confirm-received")
def confirm_received(
    order_no: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_orders.confirm_received(db, order_no, user)
