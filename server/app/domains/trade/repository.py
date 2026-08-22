"""trade 域数据访问层 —— 全域 SQL/ORM 查询与写入集中于此：
乐观锁库存三连（预扣 _RESERVE / 回补 _RELEASE / 版本调整 _ADJUST）、库存现值读、
订单/支付/RMA/GiftCard/Webhook 查询与分页、时间线/流水/后台日志/outbox 追加。
纯查询/写入，无业务分支、无 HTTP 语义。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models import (
    AdminLog, Cart, DiscountCode, DiscountRedemption, GiftCard, GiftCardLedger,
    Order, OrderItem, OrderTimeline, OutboxEvent, Payment, Product, Rma,
    Shipment, StockMovement, User, Variant, WebhookEvent,
)
from app.models import Exchange

_RESERVE_SQL = text(
    "UPDATE variants SET stock = stock - :qty, version = version + 1 "
    "WHERE id = :vid AND is_active = 1 AND stock >= :qty"
)
_RELEASE_SQL = text(
    "UPDATE variants SET stock = stock + :qty, version = version + 1 WHERE id = :vid"
)
_ADJUST_SQL = text(
    "UPDATE variants SET stock = stock + :chg, version = version + 1 "
    "WHERE id = :vid AND version = :version AND stock + :chg >= 0"
)
_STOCK_OF_SQL = text("SELECT stock FROM variants WHERE id = :vid")

# 状态推进 CAS（抢占式 UPDATE + rowcount 判定）：支付回调/取消/关单并发互斥的原子底座
_CLAIM_PAID_SQL = text(
    "UPDATE orders SET status = 1, paid_at = :now WHERE id = :oid AND status = 0"
)
_CLAIM_PAYMENT_PAID_SQL = text(
    "UPDATE payments SET status = 1 WHERE id = :pid AND status != 1"
)
_CLAIM_CANCELED_SQL = text(
    "UPDATE orders SET status = 8, canceled_at = :now, cancel_reason = :reason "
    "WHERE id = :oid AND status = 0"
)
# 已支付未发货取消 CAS：与发货（ship 只允许 status 1/2 且会推 shipping_status）并发互斥
_CLAIM_PAID_CANCEL_SQL = text(
    "UPDATE orders SET status = 8, canceled_at = :now, cancel_reason = :reason "
    "WHERE id = :oid AND status = 1 AND shipping_status = 0"
)
# 礼品卡原子扣减：余额守卫进 WHERE，并发双花时 rowcount=0
_DEBIT_GIFT_CARD_SQL = text(
    "UPDATE gift_cards SET balance = balance - :amt "
    "WHERE id = :gid AND status = 1 AND balance >= :amt"
)


# ---------- 库存：乐观锁写 + 现值读 ----------
def stock_of(db: Session, variant_id: int) -> int:
    return int(db.execute(_STOCK_OF_SQL, {"vid": variant_id}).scalar())


def reserve_stock(db: Session, variant_id: int, qty: int) -> int:
    return db.execute(_RESERVE_SQL, {"vid": variant_id, "qty": qty}).rowcount


def release_stock(db: Session, variant_id: int, qty: int) -> None:
    db.execute(_RELEASE_SQL, {"vid": variant_id, "qty": qty})


def adjust_stock_locked(db: Session, variant_id: int, change: int, version: int) -> int:
    return db.execute(_ADJUST_SQL, {
        "vid": variant_id, "chg": change, "version": version,
    }).rowcount


# ---------- 状态推进 CAS（rowcount=1 才算抢占成功，调用方据此决定是否继续派生动作） ----------
def claim_order_paid(db: Session, order_id: int, now) -> int:
    return db.execute(_CLAIM_PAID_SQL, {"oid": order_id, "now": now}).rowcount


def claim_payment_paid(db: Session, payment_id: int) -> int:
    return db.execute(_CLAIM_PAYMENT_PAID_SQL, {"pid": payment_id}).rowcount


def claim_order_canceled(db: Session, order_id: int, now, reason: str) -> int:
    return db.execute(_CLAIM_CANCELED_SQL, {
        "oid": order_id, "now": now, "reason": reason,
    }).rowcount


def claim_order_paid_canceled(db: Session, order_id: int, now, reason: str) -> int:
    return db.execute(_CLAIM_PAID_CANCEL_SQL, {
        "oid": order_id, "now": now, "reason": reason,
    }).rowcount


# ---------- 礼品卡：原子扣减 ----------
def debit_gift_card(db: Session, gift_card_id: int, amount: int) -> int:
    return db.execute(_DEBIT_GIFT_CARD_SQL, {
        "gid": gift_card_id, "amt": amount,
    }).rowcount


def variant_stock_map(db: Session, vids: list[int]) -> dict[int, int]:
    return {
        vid: int(stock)
        for vid, stock in db.query(Variant.id, Variant.stock)
        .filter(Variant.id.in_(vids)).all()
    }


# ---------- 实体单读 ----------
def get_variant(db: Session, variant_id: int) -> Optional[Variant]:
    return db.get(Variant, variant_id)


def get_order(db: Session, order_id: int) -> Optional[Order]:
    return db.get(Order, order_id)


def get_order_item(db: Session, item_id: int) -> Optional[OrderItem]:
    return db.get(OrderItem, item_id)


def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def get_gift_card(db: Session, gift_card_id: int) -> Optional[GiftCard]:
    return db.get(GiftCard, gift_card_id)


def get_discount_code(db: Session, code_id: int) -> Optional[DiscountCode]:
    return db.get(DiscountCode, code_id)


def get_webhook_event(db: Session, event_id: str) -> Optional[WebhookEvent]:
    return db.get(WebhookEvent, event_id)


def order_by_no(db: Session, order_no: str) -> Optional[Order]:
    return db.query(Order).filter(Order.order_no == order_no).first()


def rma_by_no(db: Session, rma_no: str) -> Optional[Rma]:
    return db.query(Rma).filter(Rma.rma_no == rma_no).first()


# ---------- 商品/变体批量读（购物车视图） ----------
def variants_by_ids(db: Session, vids: list[int]) -> dict[int, Variant]:
    if not vids:
        return {}
    return {v.id: v for v in db.query(Variant).filter(Variant.id.in_(vids)).all()}


def products_by_ids(db: Session, pids: set[int]) -> dict[int, Product]:
    return {p.id: p for p in db.query(Product).filter(Product.id.in_(pids)).all()}


# ---------- 购物车 ----------
def find_guest_cart(db: Session, token: str) -> Optional[Cart]:
    return (
        db.query(Cart)
        .filter(Cart.session_id == token, Cart.user_id.is_(None))
        .first()
    )


# ---------- 订单聚合读 ----------
# 后台订单排序白名单（total → grand_total 列；-前缀倒序，非法值 .get 落空走默认）
_ORDER_SORTS = {
    "placed_at": Order.placed_at.asc(),
    "-placed_at": Order.placed_at.desc(),
    "total": Order.grand_total.asc(),
    "-total": Order.grand_total.desc(),
}


def paginate_orders(
    db: Session, *, user_id: Optional[int] = None, status: Optional[int] = None,
    q: Optional[str] = None, page: int = 1, per_page: int = 10,
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
    sort: Optional[str] = None,
) -> tuple[list[Order], int]:
    query = db.query(Order)
    if user_id is not None:
        query = query.filter(Order.user_id == user_id)
    if status is not None:
        query = query.filter(Order.status == status)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((Order.order_no.like(like)) | (Order.email.like(like)))
    # 下单时间范围（naive UTC 闭区间，date_to 由调用方补到 23:59:59）
    if date_from is not None:
        query = query.filter(Order.placed_at >= date_from)
    if date_to is not None:
        query = query.filter(Order.placed_at <= date_to)
    total = query.count()
    # 排序白名单：非法/缺省走默认 placed_at 倒序 + id 稳定尾键
    order_col = _ORDER_SORTS.get(sort or "")
    order_by_cols = (
        (order_col, Order.id.desc()) if order_col is not None
        else (Order.placed_at.desc(), Order.id.desc())
    )
    orders = (
        query.order_by(*order_by_cols)
        .offset((page - 1) * per_page).limit(per_page).all()
    )
    return orders, total


def order_items(db: Session, order_id: int) -> list[OrderItem]:
    return db.query(OrderItem).filter(OrderItem.order_id == order_id).all()


def order_items_map(db: Session, order_ids: list[int]) -> dict[int, list[OrderItem]]:
    """批量订单条目（多订单装配用，替代逐单 order_items 的 N+1 调用模式）。"""
    imap: dict[int, list[OrderItem]] = {}
    if not order_ids:
        return imap
    rows = (
        db.query(OrderItem)
        .filter(OrderItem.order_id.in_(order_ids))
        .order_by(OrderItem.id.asc())
        .all()
    )
    for r in rows:
        imap.setdefault(r.order_id, []).append(r)
    return imap


def order_timeline_desc(db: Session, order_id: int) -> list[OrderTimeline]:
    return (
        db.query(OrderTimeline).filter(OrderTimeline.order_id == order_id)
        .order_by(OrderTimeline.id.desc()).all()
    )


def order_shipments(db: Session, order_id: int) -> list[Shipment]:
    return db.query(Shipment).filter(Shipment.order_id == order_id).all()


def order_shipments_map(db: Session, order_ids: list[int]) -> dict[int, list[Shipment]]:
    """批量订单物流（多订单装配用，替代逐单 order_shipments 的 N+1 调用模式）。"""
    smap: dict[int, list[Shipment]] = {}
    if not order_ids:
        return smap
    rows = (
        db.query(Shipment)
        .filter(Shipment.order_id.in_(order_ids))
        .order_by(Shipment.id.asc())
        .all()
    )
    for r in rows:
        smap.setdefault(r.order_id, []).append(r)
    return smap


def order_payments(db: Session, order_id: int) -> list[Payment]:
    return db.query(Payment).filter(Payment.order_id == order_id).all()


def order_payments_map(db: Session, order_ids: list[int]) -> dict[int, list[Payment]]:
    """批量订单支付（多订单装配用，替代逐单 order_payments 的 N+1 调用模式）。"""
    pmap: dict[int, list[Payment]] = {}
    if not order_ids:
        return pmap
    rows = (
        db.query(Payment)
        .filter(Payment.order_id.in_(order_ids))
        .order_by(Payment.id.asc())
        .all()
    )
    for r in rows:
        pmap.setdefault(r.order_id, []).append(r)
    return pmap


def order_redemptions(db: Session, order_id: int) -> list[DiscountRedemption]:
    return db.query(DiscountRedemption).filter(DiscountRedemption.order_id == order_id).all()


def checkout_created_event(db: Session, order_id: int) -> Optional[OrderTimeline]:
    return (
        db.query(OrderTimeline)
        .filter(OrderTimeline.order_id == order_id, OrderTimeline.event == "checkout_created")
        .first()
    )


# ---------- 支付 ----------
def latest_payment_of_order(db: Session, order_id: int) -> Optional[Payment]:
    return (
        db.query(Payment).filter(Payment.order_id == order_id)
        .order_by(Payment.id.desc()).first()
    )


# create-intent 幂等复用的 provider → PI id 前缀映射（跨 provider 不复用，建新行）
_PI_PREFIXES = {"mock": "PI_", "stripe": "pi_", "paypal": "PAYID-"}


def pending_payment_of_order(
    db: Session, order_id: int, provider: Optional[str] = None,
) -> Optional[Payment]:
    """订单当前 PENDING(0) 的最近一笔支付（create-intent 幂等复用，避免堆积新行）；
    指定 provider 时仅复用同 provider 创建的行（按 PI id 前缀判定），跨 provider 返回 None。"""
    query = (
        db.query(Payment)
        .filter(Payment.order_id == order_id, Payment.status == 0)
    )
    if provider:
        prefix = _PI_PREFIXES.get(provider)
        if prefix:
            query = query.filter(
                Payment.stripe_payment_intent.like(prefix + "%")
            )
    return query.order_by(Payment.id.desc()).first()


def refundable_payment_of_order(db: Session, order_id: int) -> Optional[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.order_id == order_id, Payment.status.in_([1, 4]))
        .order_by(Payment.id.desc()).first()
    )


def payment_by_intent(db: Session, payment_intent: str) -> Optional[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.stripe_payment_intent == payment_intent).first()
    )


# ---------- RMA ----------
def list_user_rmas(db: Session, user_id: int) -> list[tuple[Rma, OrderItem, Order]]:
    return (
        db.query(Rma, OrderItem, Order)
        .join(OrderItem, Rma.order_item_id == OrderItem.id)
        .join(Order, Rma.order_id == Order.id)
        .filter(Order.user_id == user_id)
        .order_by(Rma.id.desc())
        .all()
    )


def list_rmas(
    db: Session, status: Optional[int] = None, q: Optional[str] = None,
    page: int = 1, per_page: int = 20,
) -> tuple[list[tuple[Rma, OrderItem, Order]], int]:
    query = (
        db.query(Rma, OrderItem, Order)
        .join(OrderItem, Rma.order_item_id == OrderItem.id)
        .join(Order, Rma.order_id == Order.id)
    )
    if status is not None:
        query = query.filter(Rma.status == status)
    if q:
        # 后台搜索：RMA 单号 / 订单号 / 下单邮箱 三字段模糊
        like = f"%{q.strip()}%"
        query = query.filter(or_(
            Rma.rma_no.ilike(like), Order.order_no.ilike(like), Order.email.ilike(like),
        ))
    total = query.count()
    rows = (
        query.order_by(Rma.id.desc())
        .offset((page - 1) * per_page).limit(per_page).all()
    )
    return rows, total


# ---------- 礼品卡 ----------
def giftcards_to_activate(db: Session, order_id: int) -> list[GiftCard]:
    return (
        db.query(GiftCard)
        .filter(GiftCard.purchaser_order_id == order_id, GiftCard.status == 0)
        .all()
    )


def giftcard_debit_ledgers(db: Session, order_id: int) -> list[GiftCardLedger]:
    return (
        db.query(GiftCardLedger)
        .filter(GiftCardLedger.order_id == order_id, GiftCardLedger.change_type == 3)
        .all()
    )


# ---------- 库存流水（后台分页/低库存） ----------
def paginate_stock_movements(
    db: Session, variant_id: Optional[int] = None, page: int = 1, per_page: int = 20,
    type: Optional[int] = None,
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
) -> tuple[list[StockMovement], int]:
    query = db.query(StockMovement)
    if variant_id is not None:
        query = query.filter(StockMovement.variant_id == variant_id)
    if type is not None:
        query = query.filter(StockMovement.type == type)
    # 发生时间范围（naive UTC 闭区间，date_to 由调用方补到 23:59:59）
    if date_from is not None:
        query = query.filter(StockMovement.created_at >= date_from)
    if date_to is not None:
        query = query.filter(StockMovement.created_at <= date_to)
    total = query.count()
    rows = (
        query.order_by(StockMovement.id.desc())
        .offset((page - 1) * per_page).limit(per_page).all()
    )
    return rows, total


def low_stock_variants(db: Session, threshold: int) -> list[tuple[Variant, Product]]:
    return (
        db.query(Variant, Product)
        .join(Product, Variant.product_id == Product.id)
        .filter(Variant.stock <= threshold, Variant.is_active == 1)
        .order_by(Variant.stock.asc())
        .all()
    )


# ---------- 追加写入（纯 append，字段取值由 service 决定） ----------
def add_timeline(
    db: Session, order_id: int, event: str,
    actor: str = "system", detail: dict | None = None,
) -> None:
    db.add(OrderTimeline(order_id=order_id, event=event, actor=actor, detail=detail or {}))


def add_stock_movement(
    db: Session, *, variant_id: int, change: int, stock_after: int, type: int,
    ref_type: Optional[str] = None, ref_id: Optional[int] = None,
    operator: Optional[str] = None,
) -> None:
    db.add(StockMovement(
        variant_id=variant_id, change=change, stock_after=stock_after,
        type=type, ref_type=ref_type, ref_id=ref_id, operator=operator,
    ))


def add_admin_log(
    db: Session, *, admin_id: int, action: str, entity: str, entity_id: int,
    diff_json: dict | None = None,
) -> None:
    db.add(AdminLog(
        admin_id=admin_id, action=action, entity=entity, entity_id=entity_id,
        diff_json=diff_json or {},
    ))


def add_outbox_event(
    db: Session, *, aggregate_type: str, aggregate_id: int, event_type: str,
    payload: dict,
) -> None:
    db.add(OutboxEvent(
        aggregate_type=aggregate_type, aggregate_id=aggregate_id,
        event_type=event_type, payload=payload,
    ))


def add_giftcard_ledger(
    db: Session, *, gift_card_id: int, change_type: int, amount: int,
    balance_after: int, order_id: Optional[int] = None,
) -> None:
    db.add(GiftCardLedger(
        gift_card_id=gift_card_id, order_id=order_id, change_type=change_type,
        amount=amount, balance_after=balance_after,
    ))


def add_discount_redemption(
    db: Session, *, code_id: int, order_id: int, user_id: Optional[int],
    email: Optional[str], discount_amount: int,
) -> None:
    db.add(DiscountRedemption(
        code_id=code_id, order_id=order_id, user_id=user_id,
        email=email, discount_amount=discount_amount,
    ))


def add_webhook_event(
    db: Session, *, event_id: str, source: str, type: str, payload: dict,
) -> None:
    db.add(WebhookEvent(
        event_id=event_id, source=source, type=type, payload=payload,
    ))


# ---------- 换货 Exchange ----------
def exchange_by_no(db: Session, exchange_no: str) -> Optional[Exchange]:
    return db.query(Exchange).filter(Exchange.exchange_no == exchange_no).first()


def list_user_exchanges(db: Session, user_id: int) -> list[tuple[Exchange, OrderItem, Order]]:
    return (
        db.query(Exchange, OrderItem, Order)
        .join(OrderItem, Exchange.order_item_id == OrderItem.id)
        .join(Order, Exchange.order_id == Order.id)
        .filter(Order.user_id == user_id)
        .order_by(Exchange.id.desc())
        .all()
    )


def list_exchanges_by_email(db: Session, email: str) -> list[tuple[Exchange, OrderItem, Order]]:
    return (
        db.query(Exchange, OrderItem, Order)
        .join(OrderItem, Exchange.order_item_id == OrderItem.id)
        .join(Order, Exchange.order_id == Order.id)
        .filter(Order.email == email.strip().lower())
        .order_by(Exchange.id.desc())
        .all()
    )


def paginate_exchanges(
    db: Session, status: Optional[int] = None, page: int = 1, per_page: int = 10,
    q: Optional[str] = None,
) -> tuple[list[tuple[Exchange, OrderItem, Order]], int]:
    query = (
        db.query(Exchange, OrderItem, Order)
        .join(OrderItem, Exchange.order_item_id == OrderItem.id)
        .join(Order, Exchange.order_id == Order.id)
    )
    if status is not None:
        query = query.filter(Exchange.status == status)
    if q:
        # 后台搜索：换货单号 / 订单号 / 下单邮箱 三字段模糊
        like = f"%{q.strip()}%"
        query = query.filter(or_(
            Exchange.exchange_no.ilike(like), Order.order_no.ilike(like), Order.email.ilike(like),
        ))
    total = query.count()
    rows = (
        query.order_by(Exchange.id.desc())
        .offset((page - 1) * per_page).limit(per_page).all()
    )
    return rows, total
