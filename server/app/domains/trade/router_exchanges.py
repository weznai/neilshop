"""换货 exchanges —— 用户侧（智能体 A 领地）
契约：
- POST /api/exchanges {order_no, order_item_id, new_variant_id, reason?}
  校验：订单已付且在退货期（同 RMA 窗口）/ item 属于该单 / 可换量 qty-refunded-exchanged>0
  / 新变体 is_active 且有库存 → exchange_no=EX+yymmdd+4hex, price_diff=new.price-item.unit_price
  （正=待补差 负=退差 0=同价）, status=0 + timeline(exchange_created)
- GET /api/exchanges（登录本人，游客 ?email=）· GET /api/exchanges/{exchange_no}
- 后台（router_admin.py 内，绝对路径 /api/admin/trade/exchanges/*）：
  GET ?status= 队列 · POST /{no}/approve（diff>0→2 待差价，否则→1）/reject /mark-paid（→1）
  /ship {carrier,tracking_no}（→3：新变体扣库存 type=3 ref exchange + shipment + timeline）
  /complete（→4：item.exchanged_qty+=1 + 旧变体回补 type=5 + timeline）
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user_optional
from app.domains.trade import service_exchanges
from app.domains.trade.schemas import ExchangeCreateRequest
from app.models import User

router = APIRouter(prefix="/api/exchanges", tags=["exchanges"])


@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_exchange(
    body: ExchangeCreateRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if user is None and not body.email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return service_exchanges.create_exchange(db, user, body)


@router.get("")
@router.get("/")
def list_exchanges(
    email: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return service_exchanges.list_exchanges(db, user, email)


@router.get("/{exchange_no}")
def exchange_detail(
    exchange_no: str,
    email: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if user is None and not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return service_exchanges.exchange_detail(db, user, exchange_no, email)
