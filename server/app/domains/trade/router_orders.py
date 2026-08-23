"""用户订单路由（薄路由）—— 列表/详情/待付取消/物流轨迹；业务在 service_orders。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, get_current_user_optional
from app.domains.trade import service_orders
from app.models import User
from app.schemas.orders import CancelRequest

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("")
@router.get("/")
def list_orders(
    status: Optional[int] = None,
    page: int = Query(default=1, ge=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_orders.list_orders(db, user, status, page)


@router.get("/track")
def track(
    no: str = Query(...),
    email: str = Query(...),
    db: Session = Depends(get_db),
):
    return service_orders.track(db, no, email)


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
    return service_orders.cancel_order(db, order_no, user, email)


@router.post("/{order_no}/confirm-received")
def confirm_received(
    order_no: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_orders.confirm_received(db, order_no, user)
