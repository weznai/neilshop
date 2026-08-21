"""退货 RMA 用户侧服务 —— 申请（退货窗口/可退量校验）/ 列表 / 详情"""

import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.domains.trade import repository as repo
from app.models import Order, OrderItem, Rma, User
from app.schemas.orders import RmaCreateRequest
from app.services.pricing import _setting

RETURNABLE_STATUSES = {1, 2, 3, 4, 5}


def _get_order(db: Session, order_no: str) -> Order:
    order = repo.order_by_no(db, order_no.strip().upper())
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    return order


def _payload(rma: Rma, item: OrderItem | None, order_no: str | None = None) -> dict:
    return {
        "rma_no": rma.rma_no,
        "order_no": order_no,
        "qty": rma.qty,
        "reason": rma.reason,
        "reason_detail": rma.reason_detail,
        "status": rma.status,
        "label_url": rma.label_url,
        "refund_amount": rma.refund_amount,
        "refund_shipping": rma.refund_shipping,
        "restock_qty": rma.restock_qty,
        "item": {
            "order_item_id": item.id,
            "variant_id": item.variant_id,
            "title": item.title_snapshot,
            "image": item.image,
            "unit_price": item.unit_price,
            "qty": item.qty,
        } if item else None,
        "received_at": rma.received_at.isoformat() if rma.received_at else None,
        "refunded_at": rma.refunded_at.isoformat() if rma.refunded_at else None,
        "created_at": rma.created_at.isoformat() if rma.created_at else None,
    }


def create_rma(db: Session, user: User, body: RmaCreateRequest) -> dict:
    order = _get_order(db, body.order_no)
    if order.user_id != user.id:
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.status not in RETURNABLE_STATUSES:
        raise HTTPException(status_code=409, detail=f"not_returnable:{order.status}")
    return_days = int(_setting(db, "return_days", 30))
    if order.paid_at and utcnow() - order.paid_at > timedelta(days=return_days):
        raise HTTPException(status_code=409, detail="return_window_closed")

    item = repo.get_order_item(db, body.order_item_id)
    if not item or item.order_id != order.id:
        raise HTTPException(status_code=404, detail="order_item_not_found")
    available = item.qty - item.refunded_qty - item.exchanged_qty
    if body.qty > available:
        raise HTTPException(status_code=409, detail=f"qty_exceeds_available:{available}")

    rma = Rma(
        rma_no="RMA" + utcnow().strftime("%y%m%d") + uuid.uuid4().hex[:4].upper(),
        order_id=order.id,
        order_item_id=item.id,
        qty=body.qty,
        reason=body.reason,
        reason_detail=body.reason_detail,
        status=0,
    )
    db.add(rma)
    db.flush()
    repo.add_timeline(db, order.id, "rma_created", actor="user", detail={
        "rma_no": rma.rma_no, "order_item_id": item.id,
        "qty": body.qty, "reason": body.reason,
    })
    db.commit()
    return _payload(rma, item, order_no=order.order_no)


def list_rmas(db: Session, user: User) -> dict:
    rows = repo.list_user_rmas(db, user.id)
    return {
        "items": [
            _payload(rma, item, order_no=order.order_no)
            for rma, item, order in rows
        ]
    }


def rma_detail(db: Session, user: User, rma_no: str) -> dict:
    rma = repo.rma_by_no(db, rma_no.strip().upper())
    if not rma:
        raise HTTPException(status_code=404, detail="rma_not_found")
    order = repo.get_order(db, rma.order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="rma_not_found")
    item = repo.get_order_item(db, rma.order_item_id)
    return _payload(rma, item, order_no=order.order_no)


def cancel_rma(db: Session, user: User, rma_no: str) -> dict:
    """误建 RMA 撤销：归属校验复用 rma_detail 模式 → CAS 删除 status=0（申请中）行，
    删后可重新申请；非申请中（已批/在途/已退）409。"""
    rma = repo.rma_by_no(db, rma_no.strip().upper())
    if not rma:
        raise HTTPException(status_code=404, detail="rma_not_found")
    order = repo.get_order(db, rma.order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="rma_not_found")
    deleted = (
        db.query(Rma)
        .filter(Rma.id == rma.id, Rma.status == 0)
        .delete(synchronize_session=False)
    )
    if deleted == 0:
        db.rollback()
        db.expire(rma)
        raise HTTPException(status_code=409, detail=f"rma_not_cancellable:{rma.status}")
    repo.add_timeline(db, order.id, "rma_canceled", actor="user", detail={
        "rma_no": rma.rma_no,
    })
    db.commit()
    return {"rma_no": rma.rma_no, "status": "canceled"}
