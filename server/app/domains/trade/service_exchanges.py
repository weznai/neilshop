"""换货 Exchange 服务 —— 用户侧申请/列表/详情（登录本人或 email 双因子）+ 后台队列与状态机
（0→approve 分流 2 待差价/1 直批 · 2→mark-paid→1 · 1→ship→3 新变体原子扣库存+shipment ·
3→complete→4 旧变体回补+exchanged_qty · 0→reject→5）；金额美分，naive UTC。"""

import uuid
from datetime import timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.domains.trade import repository as repo
from app.domains.trade.schemas import ExchangeCreateRequest, ShipRequest
from app.models import Exchange, Order, OrderItem, Shipment, User
from app.services.pricing import _setting

EXCHANGEABLE_STATUSES = {1, 2, 3, 4, 5}
STATUS_LABELS = {0: "申请", 1: "批准", 2: "待差价支付", 3: "已发货", 4: "完成", 5: "拒绝"}
PER_PAGE = 10


def _variant_view(v, pmap: dict) -> Optional[dict]:
    if not v:
        return None
    p = pmap.get(v.product_id)
    base = p.title if p else ""
    spec = " ".join(x for x in (v.option1_value, v.option2_value) if x)
    title = f"{base} · {spec}" if base and spec else (base or spec)
    return {"id": v.id, "title": title, "price": v.price}


def _rows_payload(db: Session, rows: list[tuple[Exchange, OrderItem, Order]]) -> list[dict]:
    vids = set()
    for ex, _item, _order in rows:
        vids.add(ex.old_variant_id)
        vids.add(ex.new_variant_id)
    vmap = repo.variants_by_ids(db, list(vids)) if vids else {}
    pmap = repo.products_by_ids(db, {v.product_id for v in vmap.values()})
    out = []
    for ex, item, order in rows:
        out.append({
            "exchange_no": ex.exchange_no,
            "order_no": order.order_no,
            "email": order.email,
            "status": ex.status,
            "status_label": STATUS_LABELS.get(ex.status, str(ex.status)),
            "price_diff": ex.price_diff,
            "shipment_id": ex.shipment_id,
            "created_at": ex.created_at.isoformat() if ex.created_at else None,
            "item": {
                "order_item_id": item.id, "variant_id": item.variant_id,
                "title": item.title_snapshot, "image": item.image,
                "unit_price": item.unit_price, "qty": item.qty,
            } if item else None,
            "old_variant": _variant_view(vmap.get(ex.old_variant_id), pmap),
            "new_variant": _variant_view(vmap.get(ex.new_variant_id), pmap),
        })
    return out


def _email_match(email: Optional[str], order: Order) -> bool:
    return email is not None and email.strip().lower() == order.email.lower()


def create_exchange(db: Session, user: Optional[User], body: ExchangeCreateRequest) -> dict:
    order = repo.order_by_no(db, body.order_no.strip().upper())
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    is_owner = user is not None and order.user_id == user.id
    if not (is_owner or _email_match(body.email, order)):
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.status not in EXCHANGEABLE_STATUSES:
        raise HTTPException(status_code=409, detail=f"not_exchangeable:{order.status}")
    return_days = int(_setting(db, "return_days", 30))
    if order.paid_at and utcnow() - order.paid_at > timedelta(days=return_days):
        raise HTTPException(status_code=409, detail="return_window_closed")

    item = repo.get_order_item(db, body.order_item_id)
    if not item or item.order_id != order.id:
        raise HTTPException(status_code=404, detail="order_item_not_found")
    available = item.qty - item.refunded_qty - item.exchanged_qty
    if available <= 0:
        raise HTTPException(status_code=409, detail=f"qty_exceeds_available:{available}")

    new_v = repo.get_variant(db, body.new_variant_id)
    if not new_v or not new_v.is_active:
        raise HTTPException(status_code=404, detail="variant_not_found")
    if new_v.stock < 1:
        raise HTTPException(status_code=409, detail="variant_out_of_stock")

    ex = Exchange(
        exchange_no="EX" + utcnow().strftime("%y%m%d") + uuid.uuid4().hex[:4].upper(),
        order_id=order.id,
        order_item_id=item.id,
        old_variant_id=item.variant_id,
        new_variant_id=new_v.id,
        price_diff=new_v.price - item.unit_price,
        status=0,
    )
    db.add(ex)
    db.flush()
    repo.add_timeline(db, order.id, "exchange_created", actor="user", detail={
        "exchange_no": ex.exchange_no, "order_item_id": item.id,
        "old_variant_id": item.variant_id, "new_variant_id": new_v.id,
        "price_diff": ex.price_diff, "reason": body.reason,
    })
    db.commit()
    return _rows_payload(db, [(ex, item, order)])[0]


def list_exchanges(db: Session, user: Optional[User], email: Optional[str]) -> dict:
    if user is not None:
        rows = repo.list_user_exchanges(db, user.id)
    elif email:
        rows = repo.list_exchanges_by_email(db, email)
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"items": _rows_payload(db, rows)}


def exchange_detail(
    db: Session, user: Optional[User], exchange_no: str, email: Optional[str],
) -> dict:
    ex = repo.exchange_by_no(db, exchange_no.strip().upper())
    if not ex:
        raise HTTPException(status_code=404, detail="exchange_not_found")
    order = repo.get_order(db, ex.order_id)
    is_owner = user is not None and order is not None and order.user_id == user.id
    if not (is_owner or (order is not None and _email_match(email, order))):
        raise HTTPException(status_code=404, detail="exchange_not_found")
    item = repo.get_order_item(db, ex.order_item_id)
    return _rows_payload(db, [(ex, item, order)])[0]


def _get_exchange(db: Session, exchange_no: str) -> Exchange:
    ex = repo.exchange_by_no(db, exchange_no.strip().upper())
    if not ex:
        raise HTTPException(status_code=404, detail="exchange_not_found")
    return ex


def _admin_log(db: Session, admin: User, action: str, ex: Exchange, diff: dict | None) -> None:
    repo.add_admin_log(
        db, admin_id=admin.id, action=action, entity="exchange",
        entity_id=ex.id, diff_json=diff or {},
    )


def admin_list_exchanges(
    db: Session, status: Optional[int], page: int, size: int = PER_PAGE,
) -> dict:
    rows, total = repo.paginate_exchanges(db, status=status, page=page, per_page=size)
    return {
        "items": _rows_payload(db, rows),
        "page": page, "per_page": size, "total": total,
        "pages": (total + size - 1) // size,
    }


def approve_exchange(db: Session, admin: User, exchange_no: str) -> dict:
    ex = _get_exchange(db, exchange_no)
    if ex.status != 0:
        raise HTTPException(status_code=409, detail=f"exchange_not_approvable:{ex.status}")
    ex.status = 2 if ex.price_diff > 0 else 1
    repo.add_timeline(db, ex.order_id, "exchange_approved", actor="admin", detail={
        "exchange_no": ex.exchange_no, "to": ex.status, "price_diff": ex.price_diff,
    })
    _admin_log(db, admin, "exchange_approve", ex, {
        "to": ex.status, "price_diff": ex.price_diff,
    })
    db.commit()
    return {"exchange_no": ex.exchange_no, "status": ex.status}


def reject_exchange(db: Session, admin: User, exchange_no: str, reason: Optional[str]) -> dict:
    ex = _get_exchange(db, exchange_no)
    if ex.status != 0:
        raise HTTPException(status_code=409, detail=f"exchange_not_rejectable:{ex.status}")
    ex.status = 5
    repo.add_timeline(db, ex.order_id, "exchange_rejected", actor="admin", detail={
        "exchange_no": ex.exchange_no, "reason": reason,
    })
    _admin_log(db, admin, "exchange_reject", ex, {"to": 5, "reason": reason})
    db.commit()
    return {"exchange_no": ex.exchange_no, "status": ex.status}


def mark_paid_exchange(db: Session, admin: User, exchange_no: str) -> dict:
    ex = _get_exchange(db, exchange_no)
    if ex.status != 2:
        raise HTTPException(status_code=409, detail=f"exchange_not_awaiting_diff:{ex.status}")
    ex.status = 1
    repo.add_timeline(db, ex.order_id, "exchange_diff_paid", actor="admin", detail={
        "exchange_no": ex.exchange_no, "price_diff": ex.price_diff,
    })
    _admin_log(db, admin, "exchange_mark_paid", ex, {"price_diff": ex.price_diff, "to": 1})
    db.commit()
    return {"exchange_no": ex.exchange_no, "status": ex.status, "price_diff": ex.price_diff}


def ship_exchange(db: Session, admin: User, exchange_no: str, body: ShipRequest) -> dict:
    ex = _get_exchange(db, exchange_no)
    if ex.status != 1:
        raise HTTPException(status_code=409, detail=f"exchange_not_shippable:{ex.status}")
    if repo.reserve_stock(db, ex.new_variant_id, 1) == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="variant_out_of_stock")
    repo.add_stock_movement(
        db, variant_id=ex.new_variant_id, change=-1,
        stock_after=repo.stock_of(db, ex.new_variant_id),
        type=3, ref_type="exchange", ref_id=ex.id,
    )
    now = utcnow()
    shipment = Shipment(
        shipment_no="SP" + now.strftime("%y%m%d") + uuid.uuid4().hex[:4].upper(),
        order_id=ex.order_id,
        carrier=body.carrier,
        tracking_no=body.tracking_no,
        status=3,
        item_json=[{"orderItemId": ex.order_item_id, "qty": 1}],
        shipped_at=now,
    )
    db.add(shipment)
    db.flush()
    ex.shipment_id = shipment.id
    ex.status = 3
    repo.add_timeline(db, ex.order_id, "exchange_shipped", actor="admin", detail={
        "exchange_no": ex.exchange_no, "shipment_no": shipment.shipment_no,
        "carrier": body.carrier, "tracking_no": body.tracking_no,
        "new_variant_id": ex.new_variant_id,
    })
    _admin_log(db, admin, "exchange_ship", ex, {
        "shipment_no": shipment.shipment_no, "carrier": body.carrier,
        "tracking_no": body.tracking_no,
    })
    db.commit()
    return {
        "exchange_no": ex.exchange_no, "status": ex.status,
        "shipment_no": shipment.shipment_no,
    }


def complete_exchange(db: Session, admin: User, exchange_no: str) -> dict:
    ex = _get_exchange(db, exchange_no)
    if ex.status != 3:
        raise HTTPException(status_code=409, detail=f"exchange_not_completable:{ex.status}")
    item = repo.get_order_item(db, ex.order_item_id)
    item.exchanged_qty += 1
    repo.release_stock(db, ex.old_variant_id, 1)
    repo.add_stock_movement(
        db, variant_id=ex.old_variant_id, change=1,
        stock_after=repo.stock_of(db, ex.old_variant_id),
        type=5, ref_type="exchange", ref_id=ex.id,
    )
    ex.status = 4
    repo.add_timeline(db, ex.order_id, "exchange_completed", actor="admin", detail={
        "exchange_no": ex.exchange_no, "restock_variant_id": ex.old_variant_id,
        "exchanged_qty": item.exchanged_qty,
    })
    _admin_log(db, admin, "exchange_complete", ex, {
        "to": 4, "restock_variant_id": ex.old_variant_id,
        "exchanged_qty": item.exchanged_qty,
    })
    db.commit()
    return {
        "exchange_no": ex.exchange_no, "status": ex.status,
        "exchanged_qty": item.exchanged_qty,
    }
