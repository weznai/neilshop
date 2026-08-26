"""trade 域数据访问层 —— 全域 SQL/ORM 查询与写入集中于此：
乐观锁库存三连（预扣 _RESERVE / 回补 _RELEASE / 版本调整 _ADJUST）、库存现值读、
订单/支付/RMA/GiftCard/Webhook 查询与分页、时间线/流水/后台日志/outbox 追加。
纯查询/写入，无业务分支、无 HTTP 语义。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, text
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
# 用户确认收货 CAS：仅已送达(4)可推进完成(5)，与后台 mark-completed 并发互斥
_CLAIM_COMPLETED_SQL = text(
    "UPDATE orders SET status = 5, completed_at = :now "
    "WHERE id = :oid AND status = 4"
)
# 开始备货 CAS：仅已支付(1)可推进备货(2)，与取消/发货/支付回调并发互斥
_CLAIM_PREPARING_SQL = text(
    "UPDATE orders SET status = 2 WHERE id = :oid AND status = 1"
)
# 发货 CAS：仅已支付/待差价(1/2)可发货（置 3/发货中/发货时间/物流单号），
# 与已付取消（shipping_status 守卫）/重复发货并发互斥，rowcount=0 即不可发货
_CLAIM_SHIPPED_SQL = text(
    "UPDATE orders SET status = 3, shipping_status = 2, shipped_at = :now, "
    "tracking_no = :tracking WHERE id = :oid AND status IN (1, 2)"
)
# 换货差价支付核销 CAS：仅待差价(2)可推进批准(1)，mock-pay/webhook/mark-paid 三方互斥
_CLAIM_EXCHANGE_DIFF_PAID_SQL = text(
    "UPDATE exchanges SET status = 1 WHERE id = :eid AND status = 2"
)
# RMA 状态推进 CAS：并发双击互斥（rowcount=0 即已被并发处理）
_CLAIM_RMA_APPROVED_SQL = text(
    "UPDATE returns SET status = 2 WHERE id = :rid AND status = 0")
_CLAIM_RMA_REJECTED_SQL = text(
    "UPDATE returns SET status = 6 WHERE id = :rid AND status = 0")
_CLAIM_RMA_RECEIVED_SQL = text(
    "UPDATE returns SET status = 4 WHERE id = :rid AND status IN (1, 2, 3)")
# RMA 退款占用：refunded_at 由 NULL 变非 NULL，天然防并发双退
_CLAIM_RMA_REFUND_SQL = text(
    "UPDATE returns SET refunded_at = :now "
    "WHERE id = :rid AND status = 4 AND refunded_at IS NULL")
# 退款记账原子化：可退余守卫进 WHERE（并发双退后者 rowcount=0），累计防丢失更新
_CLAIM_PAYMENT_REFUND_SQL = text(
    "UPDATE payments SET refunded_amount = refunded_amount + :amt, status = :st "
    "WHERE id = :pid AND amount - refunded_amount >= :amt"
)
# 换货状态推进 CAS：approve 按 price_diff 分流待差价(2)/直批(1)；
# ship 仅批准(1)可发，complete 仅发货中(3)可收尾（CASE WHEN 双库兼容 MySQL/SQLite）
_CLAIM_EXCHANGE_APPROVED_SQL = text(
    "UPDATE exchanges SET status = CASE WHEN price_diff > 0 THEN 2 ELSE 1 END "
    "WHERE id = :eid AND status = 0"
)
_CLAIM_EXCHANGE_REJECTED_SQL = text(
    "UPDATE exchanges SET status = 5 WHERE id = :eid AND status = 0"
)
_CLAIM_EXCHANGE_SHIPPED_SQL = text(
    "UPDATE exchanges SET status = 3 WHERE id = :eid AND status = 1"
)
_CLAIM_EXCHANGE_COMPLETED_SQL = text(
    "UPDATE exchanges SET status = 4 WHERE id = :eid AND status = 3"
)
# 礼品卡原子扣减：余额守卫进 WHERE，并发双花时 rowcount=0
_DEBIT_GIFT_CARD_SQL = text(
    "UPDATE gift_cards SET balance = balance - :amt "
    "WHERE id = :gid AND status = 1 AND balance >= :amt"
)
# 礼品卡原子回补：作废卡(4)守卫进 WHERE（回补不可复活作废卡），rowcount=0 = 卡作废
_CREDIT_GIFT_CARD_SQL = text(
    "UPDATE gift_cards SET balance = balance + :amt "
    "WHERE id = :gid AND status != 4"
)
# order_items 占量 CAS（可退/可换余守卫进 WHERE）：RMA 收货占 refunded_qty / 换货发货占
# exchanged_qty，与整单退款回补、并发占量互斥，rowcount=0 = 余量不足
_CLAIM_ITEM_REFUNDED_SQL = text(
    "UPDATE order_items SET refunded_qty = refunded_qty + :q "
    "WHERE id = :iid AND qty - refunded_qty - exchanged_qty >= :q"
)
_CLAIM_ITEM_EXCHANGED_SQL = text(
    "UPDATE order_items SET exchanged_qty = exchanged_qty + :q "
    "WHERE id = :iid AND qty - refunded_qty - exchanged_qty >= :q"
)
# 后台送达 CAS：仅发货中(3)可推送达(4)，与重复标记/状态回退并发互斥
_CLAIM_DELIVERED_SQL = text(
    "UPDATE orders SET status = 4, delivered_at = :now "
    "WHERE id = :oid AND status = 3"
)
# 折扣码计数原子自增：限额守卫进 WHERE，并发支付回调抢同码不超发（rowcount=0 = 已满）
_BUMP_DC_USED_SQL = text(
    "UPDATE discount_codes SET used_count = used_count + 1 "
    "WHERE id = :cid AND (usage_limit IS NULL OR used_count < usage_limit)"
)
# 用户累计消费原子加（读改写在并发回调下会丢失更新）；同时提供读回现值供 tier 判断
_ADD_TOTAL_SPENT_SQL = text(
    "UPDATE users SET total_spent = total_spent + :amt WHERE id = :uid"
)
_TOTAL_SPENT_OF_SQL = text("SELECT total_spent FROM users WHERE id = :uid")
# 商品销量原子累计（支付成功按 OrderItem 聚合逐商品 UPDATE）
_BUMP_SOLD_SQL = text(
    "UPDATE products SET sold_count = sold_count + :qty WHERE id = :pid"
)
# 售后未决占用 CAS 抢占：可退余守卫进 WHERE，同一 OrderItem 并发/重复申请不超量
_CLAIM_ITEM_RMA_SQL = text(
    "UPDATE order_items SET rma_pending_qty = rma_pending_qty + :qty "
    "WHERE id = :iid AND qty - refunded_qty - exchanged_qty "
    "- rma_pending_qty - ex_pending_qty >= :qty"
)
_CLAIM_ITEM_EX_SQL = text(
    "UPDATE order_items SET ex_pending_qty = ex_pending_qty + :qty "
    "WHERE id = :iid AND qty - refunded_qty - exchanged_qty "
    "- rma_pending_qty - ex_pending_qty >= :qty"
)
# 占用释放（取消/拒绝）：>= 守卫防负数；存量行无占用时 rowcount=0 为无害空操作
_RELEASE_ITEM_RMA_SQL = text(
    "UPDATE order_items SET rma_pending_qty = rma_pending_qty - :qty "
    "WHERE id = :iid AND rma_pending_qty >= :qty"
)
_RELEASE_ITEM_EX_SQL = text(
    "UPDATE order_items SET ex_pending_qty = ex_pending_qty - :qty "
    "WHERE id = :iid AND ex_pending_qty >= :qty"
)
# 终态结转（RMA 退款 → refunded / 换货完成 → exchanged）：单语句原子累计防丢失更新，
# CASE 防负数（存量/直建行无占用时照常累计、占用保持 0）
_CONVERT_ITEM_RMA_SQL = text(
    "UPDATE order_items SET refunded_qty = refunded_qty + :qty, "
    "rma_pending_qty = CASE WHEN rma_pending_qty >= :qty "
    "THEN rma_pending_qty - :qty ELSE 0 END WHERE id = :iid"
)
_CONVERT_ITEM_EX_SQL = text(
    "UPDATE order_items SET exchanged_qty = exchanged_qty + :qty, "
    "ex_pending_qty = CASE WHEN ex_pending_qty >= :qty "
    "THEN ex_pending_qty - :qty ELSE 0 END WHERE id = :iid"
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


def claim_order_completed(db: Session, order_id: int, now) -> int:
    return db.execute(_CLAIM_COMPLETED_SQL, {"oid": order_id, "now": now}).rowcount


def claim_order_preparing(db: Session, order_id: int) -> int:
    return db.execute(_CLAIM_PREPARING_SQL, {"oid": order_id}).rowcount


def claim_order_shipped(db: Session, order_id: int, now, tracking_no: str) -> int:
    return db.execute(_CLAIM_SHIPPED_SQL, {
        "oid": order_id, "now": now, "tracking": tracking_no,
    }).rowcount


def claim_exchange_diff_paid(db: Session, exchange_id: int) -> int:
    return db.execute(_CLAIM_EXCHANGE_DIFF_PAID_SQL, {"eid": exchange_id}).rowcount


def claim_exchange_approved(db: Session, exchange_id: int) -> int:
    return db.execute(_CLAIM_EXCHANGE_APPROVED_SQL, {"eid": exchange_id}).rowcount


def claim_exchange_rejected(db: Session, exchange_id: int) -> int:
    return db.execute(_CLAIM_EXCHANGE_REJECTED_SQL, {"eid": exchange_id}).rowcount


def claim_exchange_shipped(db: Session, exchange_id: int) -> int:
    return db.execute(_CLAIM_EXCHANGE_SHIPPED_SQL, {"eid": exchange_id}).rowcount


def claim_exchange_completed(db: Session, exchange_id: int) -> int:
    return db.execute(_CLAIM_EXCHANGE_COMPLETED_SQL, {"eid": exchange_id}).rowcount


def claim_rma_approved(db: Session, rma_id: int) -> int:
    return db.execute(_CLAIM_RMA_APPROVED_SQL, {"rid": rma_id}).rowcount


def claim_rma_rejected(db: Session, rma_id: int) -> int:
    return db.execute(_CLAIM_RMA_REJECTED_SQL, {"rid": rma_id}).rowcount


def claim_rma_received(db: Session, rma_id: int) -> int:
    return db.execute(_CLAIM_RMA_RECEIVED_SQL, {"rid": rma_id}).rowcount


def claim_rma_refund(db: Session, rma_id: int, now) -> int:
    return db.execute(_CLAIM_RMA_REFUND_SQL, {"rid": rma_id, "now": now}).rowcount


def claim_payment_refund(db: Session, payment_id: int, amount: int, full: bool) -> int:
    """退款原子累计：全额 → status=3，部分 → status=4；余额守卫失败 rowcount=0"""
    return db.execute(_CLAIM_PAYMENT_REFUND_SQL, {
        "pid": payment_id, "amt": amount, "st": 3 if full else 4,
    }).rowcount


def claim_order_delivered(db: Session, order_id: int, now) -> int:
    return db.execute(_CLAIM_DELIVERED_SQL, {"oid": order_id, "now": now}).rowcount


# ---------- order_items 占量（RMA 收货 / 换货发货） ----------
def claim_item_refunded(db: Session, item_id: int, qty: int) -> int:
    """RMA 占可退量：qty - refunded_qty - exchanged_qty 守卫进 WHERE（P0-1）"""
    return db.execute(_CLAIM_ITEM_REFUNDED_SQL, {"iid": item_id, "q": qty}).rowcount


def claim_item_exchanged(db: Session, item_id: int, qty: int) -> int:
    """换货占可换量：同 refunded 守卫（两口径同看双计数，防 RMA/换货互相穿透）"""
    return db.execute(_CLAIM_ITEM_EXCHANGED_SQL, {"iid": item_id, "q": qty}).rowcount


# ---------- 礼品卡：原子扣减/回补 ----------
def debit_gift_card(db: Session, gift_card_id: int, amount: int) -> int:
    return db.execute(_DEBIT_GIFT_CARD_SQL, {
        "gid": gift_card_id, "amt": amount,
    }).rowcount


def credit_gift_card(db: Session, gift_card_id: int, amount: int) -> int:
    """礼品卡回补原子化（ORM 读改写在并发回补下会丢失更新）：作废卡守卫进 WHERE"""
    return db.execute(_CREDIT_GIFT_CARD_SQL, {
        "gid": gift_card_id, "amt": amount,
    }).rowcount


# ---------- 支付成功侧原子累计（折扣码/用户消费/商品销量） ----------
def bump_discount_used_count(db: Session, code_id: int) -> int:
    """折扣码 used_count 原子 +1（限额守卫进 WHERE）：rowcount=0 = 已达 usage_limit。
    支付已成功场景由调用方决定超发语义（记日志放行，不回滚订单）。"""
    return db.execute(_BUMP_DC_USED_SQL, {"cid": code_id}).rowcount


def redemption_count_by_code_email(db: Session, code_id: int, email: str) -> int:
    """按 (code_id, email) 的已核销 Redemption 计数 —— 支付侧 per-user 限额守卫用，
    口径与 promo_rules.validate_code 一致（email 需调用方 strip+lower 归一）。"""
    return (
        db.query(DiscountRedemption)
        .filter(DiscountRedemption.code_id == code_id,
                DiscountRedemption.email == email)
        .count()
    )


def add_user_total_spent(db: Session, user_id: int, amount: int) -> int:
    """total_spent 原子累计（UPDATE ... SET total_spent = total_spent + :amt），
    返回更新后的现值（tier 晋升判断用，避免 ORM 脏快照）。"""
    db.execute(_ADD_TOTAL_SPENT_SQL, {"uid": user_id, "amt": amount})
    return int(db.execute(_TOTAL_SPENT_OF_SQL, {"uid": user_id}).scalar())


def bump_product_sold_count(db: Session, product_id: int, qty: int) -> None:
    db.execute(_BUMP_SOLD_SQL, {"pid": product_id, "qty": qty})


# ---------- 售后未决占用：抢占 / 释放 / 结转 ----------
def claim_item_rma(db: Session, item_id: int, qty: int) -> int:
    return db.execute(_CLAIM_ITEM_RMA_SQL, {"iid": item_id, "qty": qty}).rowcount


def claim_item_exchange(db: Session, item_id: int, qty: int) -> int:
    return db.execute(_CLAIM_ITEM_EX_SQL, {"iid": item_id, "qty": qty}).rowcount


def release_item_rma(db: Session, item_id: int, qty: int) -> int:
    return db.execute(_RELEASE_ITEM_RMA_SQL, {"iid": item_id, "qty": qty}).rowcount


def release_item_exchange(db: Session, item_id: int, qty: int) -> int:
    return db.execute(_RELEASE_ITEM_EX_SQL, {"iid": item_id, "qty": qty}).rowcount


def convert_item_rma_refunded(db: Session, item_id: int, qty: int) -> None:
    db.execute(_CONVERT_ITEM_RMA_SQL, {"iid": item_id, "qty": qty})


def convert_item_ex_exchanged(db: Session, item_id: int, qty: int) -> None:
    db.execute(_CONVERT_ITEM_EX_SQL, {"iid": item_id, "qty": qty})


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


def blacklisted_email(db: Session, email: str) -> bool:
    """下单 email 命中黑名单用户（risk_flag=2，email 已归一 strip+lower 等值匹配）"""
    return (
        db.query(User.id)
        .filter(User.email == email, User.risk_flag == 2)
        .first() is not None
    )


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
    status_in: Optional[list[int]] = None,
    q: Optional[str] = None, page: int = 1, per_page: int = 10,
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
    sort: Optional[str] = None, email: Optional[str] = None,
) -> tuple[list[Order], int]:
    query = db.query(Order)
    if user_id is not None:
        # 游客下同邮箱的单并入账户列表（email 已归一且有索引；单表 or 条件不产生重复行）
        if email:
            query = query.filter(or_(Order.user_id == user_id, Order.email == email))
        else:
            query = query.filter(Order.user_id == user_id)
    if status is not None:
        query = query.filter(Order.status == status)
    if status_in is not None:
        query = query.filter(Order.status.in_(status_in))
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
    """可退支付行 = 主支付行：金额等于 order.grand_total 的成功行优先，否则 id 最小的
    成功行（status∈1/4）。旧行为按 id 最大取 —— 换货差价 Payment（挂原订单、
    amount=price_diff 远小于 grand_total、settle 后 id 更大）会污染退款池：
    全额退款只退差价额且误判 full=True 整单置 REFUNDED，主款永不退。"""
    rows = (
        db.query(Payment)
        .filter(Payment.order_id == order_id, Payment.status.in_([1, 4]))
        .order_by(Payment.id.asc())
        .all()
    )
    if not rows:
        return None
    order = db.get(Order, order_id)
    grand = int(order.grand_total) if order is not None else None
    for row in rows:
        if grand is not None and int(row.amount) == grand:
            return row
    return rows[0]


def supersede_stale_pending(db: Session, keep: Payment) -> int:
    """废弃同单同 provider 的旧 PENDING 支付行（保留 keep 最新一条）：
    create_intent 先查后插的并发窗口（双击）可能堆积多条 PENDING —— 提交后
    将旧行置 status=2(FAILED) + failure_reason=superseded，返回废弃行数。
    按 PI id 前缀限定同 provider（跨 provider 行不受影响）。"""
    pi = keep.stripe_payment_intent or ""
    prefix = next((p for p in _PI_PREFIXES.values() if pi.startswith(p)), None)
    if not prefix:
        return 0
    return (
        db.query(Payment)
        .filter(Payment.order_id == keep.order_id,
                Payment.status == 0,
                Payment.id != keep.id,
                Payment.stripe_payment_intent.like(prefix + "%"))
        .update({Payment.status: 2, Payment.failure_reason: "superseded_by_newer_intent"},
                synchronize_session=False)
    )


def payment_by_intent(db: Session, payment_intent: str) -> Optional[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.stripe_payment_intent == payment_intent).first()
    )


def stale_pending_intents_of_order(db: Session, keep: Payment) -> list[str]:
    """与 supersede_stale_pending 同口径将被废弃的旧 PENDING PI 先行取出
    （供调用方废弃后尽力 provider 取消 —— 旧 intent 在 provider 侧仍可支付，
    用户完成旧支付即双扣款）。"""
    pi = keep.stripe_payment_intent or ""
    prefix = next((p for p in _PI_PREFIXES.values() if pi.startswith(p)), None)
    if not prefix:
        return []
    rows = (
        db.query(Payment.stripe_payment_intent)
        .filter(Payment.order_id == keep.order_id,
                Payment.status == 0,
                Payment.id != keep.id,
                Payment.stripe_payment_intent.like(prefix + "%"))
        .all()
    )
    return [r[0] for r in rows if r[0]]


def exchange_linked_to_payment(db: Session, payment_id: int) -> Optional[Exchange]:
    """按 diff_payment_id 反查换货（任意状态）：webhook 退款回调识别「换货差价支付行」
    用 —— settle 后换货状态已离开 2，exchange_by_diff_payment 的 status==2 过滤会漏判，
    差价行退款会被误当主款退款进整单语义。"""
    return (
        db.query(Exchange)
        .filter(Exchange.diff_payment_id == payment_id)
        .first()
    )


# ---------- RMA ----------
def rma_inflight_qty(db: Session, order_item_id: int) -> int:
    """该条目未终态 RMA 在途占量（0-3；4 已收货在 receive 原子计入 refunded_qty 不重复计）"""
    total = (
        db.query(func.sum(Rma.qty))
        .filter(Rma.order_item_id == order_item_id, Rma.status.in_([0, 1, 2, 3]))
        .scalar()
    )
    return int(total or 0)


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
    page: int = 1, per_page: int = 20, status_in: Optional[list[int]] = None,
) -> tuple[list[tuple[Rma, OrderItem, Order]], int]:
    query = (
        db.query(Rma, OrderItem, Order)
        .join(OrderItem, Rma.order_item_id == OrderItem.id)
        .join(Order, Rma.order_id == Order.id)
    )
    if status is not None:
        query = query.filter(Rma.status == status)
    if status_in is not None:
        query = query.filter(Rma.status.in_(status_in))
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


def giftcard_refund_marks(db: Session, order_id: int) -> list[OrderTimeline]:
    """礼品卡比例回补标记（timeline giftcard_refunded，detail.ref_no=RMA 单号）：
    查重 + 逐卡累计钳制数据源（detail 为 JSON，跨库不查键值、内存比对，
    同 exchange_diff_refunded 模式）"""
    return (
        db.query(OrderTimeline)
        .filter(OrderTimeline.order_id == order_id,
                OrderTimeline.event == "giftcard_refunded")
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
def exchange_inflight_qty(db: Session, order_item_id: int) -> int:
    """该条目在途换货占量（0-2；3 已发货在 ship 原子计入 exchanged_qty 不重复计）"""
    total = (
        db.query(func.sum(Exchange.qty))
        .filter(Exchange.order_item_id == order_item_id, Exchange.status.in_([0, 1, 2]))
        .scalar()
    )
    return int(total or 0)


def exchange_by_no(db: Session, exchange_no: str) -> Optional[Exchange]:
    return db.query(Exchange).filter(Exchange.exchange_no == exchange_no).first()


def exchange_by_diff_payment(db: Session, payment_id: int) -> Optional[Exchange]:
    return (
        db.query(Exchange)
        .filter(Exchange.diff_payment_id == payment_id, Exchange.status == 2)
        .first()
    )


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


def exchange_diff_refunded(db: Session, order_id: int, exchange_no: str) -> bool:
    """换货负差价是否已退（timeline exchange_diff_refunded 标记按单号判定，
    防状态回退/重放场景下的二次退款；detail 为 JSON，跨库不查询键值、内存比对）"""
    rows = (
        db.query(OrderTimeline)
        .filter(OrderTimeline.order_id == order_id,
                OrderTimeline.event == "exchange_diff_refunded")
        .all()
    )
    return any((t.detail or {}).get("exchange_no") == exchange_no for t in rows)
