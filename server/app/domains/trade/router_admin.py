"""后台交易/履约/库存路由（薄路由，/api/admin/trade）—— 订单发货/送达/退款、RMA 队列推进、
库存调整与流水；业务与退款公共路径在 service_admin。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.domains.trade import service_admin, service_exchanges
from app.domains.trade.schemas import (
    ExchangeRejectRequest, NoteIn, RefundRequest, RmaRejectRequest, ShipRequest,
    ShippingRateIn, ShippingRateUpdateIn, StockAdjustRequest,
)
from app.models import User

router = APIRouter(prefix="/api/admin/trade", tags=["admin-trade"])


def _parse_order_status(raw: Optional[str]) -> tuple[Optional[int], Optional[list[int]]]:
    """订单状态过滤解析：含逗号拆分转 int 列表（任一段非法 422 invalid status），
    单值保持 int 语义（与旧 status: int 行为一致）；空/未传 → 不过滤"""
    if raw is None or raw.strip() == "":
        return None, None
    if "," in raw:
        try:
            return None, [int(x) for x in raw.split(",")]
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid status")
    try:
        return int(raw), None
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid status")


@router.get("/orders")
def list_orders(
    status: Optional[str] = None,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: Optional[int] = Query(default=None, ge=1),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    status_eq, status_in = _parse_order_status(status)
    return service_admin.list_orders(
        db, status_eq, q, page, per_page, date_from, date_to, sort,
        status_in=status_in,
    )


@router.get("/orders/{order_no}")
def order_detail(order_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service_admin.order_detail(db, order_no)


@router.post("/orders/{order_no}/ship")
def ship_order(order_no: str, body: ShipRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service_admin.ship_order(db, admin, order_no, body)


@router.post("/orders/{order_no}/mark-delivered")
def mark_delivered(order_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service_admin.mark_delivered(db, admin, order_no)


@router.post("/orders/{order_no}/refund")
def refund_order(
    order_no: str,
    body: RefundRequest | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_admin.refund_order(db, admin, order_no, body)


@router.post("/orders/{order_no}/cancel")
def cancel_order(order_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service_admin.cancel_order(db, admin, order_no)


@router.post("/orders/{order_no}/note")
def add_order_note(order_no: str, body: NoteIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service_admin.add_order_note(db, admin, order_no, body)


@router.get("/rmas")
def list_rmas(
    status: Optional[int] = None,
    q: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_admin.list_rmas(db, status, page, per_page, q)


@router.post("/rmas/{rma_no}/approve")
def approve_rma(rma_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service_admin.approve_rma(db, admin, rma_no)


@router.post("/rmas/{rma_no}/reject")
def reject_rma(
    rma_no: str,
    body: RmaRejectRequest | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_admin.reject_rma(db, admin, rma_no, body.reason if body else None)


@router.post("/rmas/{rma_no}/receive")
def receive_rma(rma_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service_admin.receive_rma(db, admin, rma_no)


@router.post("/rmas/{rma_no}/refund")
def refund_rma(rma_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service_admin.refund_rma(db, admin, rma_no)


@router.post("/stock/adjust")
def adjust_stock(body: StockAdjustRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service_admin.adjust_stock(db, admin, body)


@router.get("/stock/movements")
def stock_movements(
    variant_id: Optional[int] = None,
    type: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_admin.stock_movements(db, variant_id, page, type, date_from, date_to)


@router.get("/stock/low")
def low_stock(
    threshold: int = 8,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_admin.low_stock(db, threshold)


@router.get("/exchanges")
def list_exchanges(
    status: Optional[int] = None,
    q: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_exchanges.admin_list_exchanges(db, status, page, size, q)


@router.post("/exchanges/{exchange_no}/approve")
def approve_exchange(
    exchange_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service_exchanges.approve_exchange(db, admin, exchange_no)


@router.post("/exchanges/{exchange_no}/reject")
def reject_exchange(
    exchange_no: str,
    body: ExchangeRejectRequest | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_exchanges.reject_exchange(
        db, admin, exchange_no, body.reason if body else None)


@router.post("/exchanges/{exchange_no}/mark-paid")
def mark_paid_exchange(
    exchange_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service_exchanges.mark_paid_exchange(db, admin, exchange_no)


@router.post("/exchanges/{exchange_no}/ship")
def ship_exchange(
    exchange_no: str, body: ShipRequest,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service_exchanges.ship_exchange(db, admin, exchange_no, body)


@router.post("/exchanges/{exchange_no}/complete")
def complete_exchange(
    exchange_no: str, admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service_exchanges.complete_exchange(db, admin, exchange_no)


# ---------- 运费模板管理 ----------

@router.get("/shipping-rates")
def list_shipping_rates(
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service_admin.list_shipping_rates(db)


@router.post("/shipping-rates", status_code=201)
def create_shipping_rate(
    body: ShippingRateIn,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service_admin.create_shipping_rate(db, admin, body)


@router.put("/shipping-rates/{rate_id}")
def update_shipping_rate(
    rate_id: int,
    body: ShippingRateUpdateIn,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service_admin.update_shipping_rate(db, admin, rate_id, body)


@router.delete("/shipping-rates/{rate_id}")
def delete_shipping_rate(
    rate_id: int,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service_admin.delete_shipping_rate(db, admin, rate_id)
