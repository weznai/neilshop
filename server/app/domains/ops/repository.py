"""运营域仓储 —— 纯查询/聚合（dashboard 聚合实现保持原样，SQL 条数是 test_perf 断言对象）"""

from datetime import date, datetime, timedelta

from sqlalchemy import case, func, or_, text
from sqlalchemy.orm import Query, Session

from app.models import (
    AdminLog, Cart, CookieConsent, DataRequest, NewsletterSubscriber, Order,
    PointsLedger, Product, ReconciliationDaily, Review, Subscription, Ticket,
    UgcSubmission, User, Variant,
)

# GDPR 数据请求状态推进 CAS（同 trade 域 claim_* 风格）：仅受理中(0)可抢占，
# 后台立即执行/后台驳回/worker 到期执行三方并发互斥，rowcount=0 = 已被处理
_CLAIM_DATA_REQUEST_SQL = text(
    "UPDATE data_requests SET status = :new WHERE id = :rid AND status = 0"
)
# 对账核销 CAS：0平/1告警 → 2已处理，并发双击/已处理 rowcount=0
_CLAIM_RECON_RESOLVED_SQL = text(
    "UPDATE reconciliation_daily SET status = 2 WHERE id = :rid AND status IN (0, 1)"
)


def claim_data_request(db: Session, req_id: int, new_status: int) -> int:
    return db.execute(
        _CLAIM_DATA_REQUEST_SQL, {"rid": req_id, "new": new_status}
    ).rowcount


def claim_reconciliation_resolved(db: Session, rec_id: int) -> int:
    return db.execute(_CLAIM_RECON_RESOLVED_SQL, {"rid": rec_id}).rowcount


def page(q: Query, page: int, size: int):
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    return rows, total


# ===== 看板聚合（与原 admin_ops.dashboard 同构：COUNT/SUM 聚合下推数据库）=====


def orders_placed_since(db: Session, start: datetime) -> int:
    return db.query(func.count(Order.id)).filter(Order.placed_at >= start).scalar() or 0


def paid_gmv_since(db: Session, start: datetime) -> int:
    # 口径=净支付成功：排除已取消(8)/已退款(9)（部分退款不改订单状态，订单保留计入）
    return (
        db.query(func.coalesce(func.sum(Order.grand_total), 0))
        .filter(Order.paid_at.isnot(None), Order.paid_at >= start,
                Order.status.notin_([8, 9]))
        .scalar()
    )


def paid_orders_since(db: Session, start: datetime) -> int:
    # 与 paid_gmv_since 同口径（AOV 分子分母一致），同步排除取消/退款单
    return (
        db.query(func.count(Order.id))
        .filter(Order.paid_at.isnot(None), Order.paid_at >= start,
                Order.status.notin_([8, 9]))
        .scalar()
        or 0
    )


def newsletter_count(db: Session) -> int:
    return db.query(func.count(NewsletterSubscriber.email)).scalar() or 0


def cookie_consent_count(db: Session) -> int:
    return db.query(func.count(CookieConsent.id)).scalar() or 0


def _has_items(db: Session):
    # JSON 数组长度 > 0：SQLite 用 json_array_length（部分构建无标量 json_length），
    # MySQL/MariaDB 用 json_length —— 对数组语义一致（[]→0，N 元素→N），双库兼容
    fn = (func.json_array_length if db.get_bind().dialect.name == "sqlite"
          else func.json_length)
    return func.coalesce(fn(Cart.items), 0) > 0


def carts_with_items_count(db: Session) -> int:
    return db.query(func.count(Cart.id)).filter(_has_items(db)).scalar() or 0


def abandoned_carts_count(db: Session, cutoff: datetime) -> int:
    return db.query(func.count(Cart.id)).filter(
        _has_items(db), Cart.updated_at <= cutoff).scalar() or 0


def pending_orders_count(db: Session) -> int:
    """待发货：已支付未发货（1已支付/2备货中）——与后台订单页「待发货」语义一致"""
    return db.query(func.count(Order.id)).filter(Order.status.in_([1, 2])).scalar() or 0


def unpaid_orders_count(db: Session) -> int:
    return db.query(func.count(Order.id)).filter(Order.status == 0).scalar() or 0


# 低库存统一口径：stock <= max(safety_stock, 8)（CASE WHEN 写法，SQLite/MySQL 双兼容，
# 与 catalog 侧同公式）；仅统计在售变体（is_active=1）
_LOW_STOCK_THRESHOLD = case(
    (Variant.safety_stock > 8, Variant.safety_stock), else_=8,
)


def low_stock_count(db: Session) -> int:
    return (
        db.query(func.count(Variant.id))
        .filter(Variant.is_active == 1, Variant.stock <= _LOW_STOCK_THRESHOLD)
        .scalar() or 0
    )


def pending_reviews_count(db: Session) -> int:
    return db.query(func.count(Review.id)).filter(Review.status == 0).scalar() or 0


def open_tickets_count(db: Session) -> int:
    # 未关口径：0/1/2/3（3=已解决待关，尚未确认关闭也算未关）
    return db.query(func.count(Ticket.id)).filter(Ticket.status.in_([0, 1, 2, 3])).scalar() or 0


def top_products(db: Session, limit: int = 5) -> list[Product]:
    return (
        db.query(Product)
        .order_by(Product.sold_count.desc(), Product.id.desc())
        .limit(limit)
        .all()
    )


def daily_paid_rows(db: Session, d_start: datetime) -> list:
    # 与 paid_gmv_since 同口径=净支付成功：排除已取消(8)/已退款(9)，两处聚合保持一致
    return (
        db.query(
            func.date(Order.paid_at),
            func.coalesce(func.sum(Order.grand_total), 0),
            func.count(Order.id),
        )
        .filter(Order.status >= 1, Order.status.notin_([8, 9]),
                Order.paid_at.isnot(None), Order.paid_at >= d_start)
        .group_by(func.date(Order.paid_at))
        .all()
    )


def latest_reconciliation(db: Session) -> ReconciliationDaily | None:
    return (
        db.query(ReconciliationDaily)
        .order_by(ReconciliationDaily.reconcile_date.desc(), ReconciliationDaily.id.desc())
        .first()
    )


def low_stock_top_rows(db: Session, limit: int = 5) -> list:
    return (
        db.query(Variant.sku, Product.title, Variant.stock)
        .join(Product, Product.id == Variant.product_id)
        .filter(Variant.is_active == 1, Variant.stock <= _LOW_STOCK_THRESHOLD)
        .order_by(Variant.stock.asc(), Variant.id.asc())
        .limit(limit)
        .all()
    )


# ===== 会员管理 =====


# 会员排序白名单：points/total_spent 升降序，id 倒序作稳定分页的次序键
_MEMBER_SORTS = {
    "points": (User.points.asc(), User.id.desc()),
    "-points": (User.points.desc(), User.id.desc()),
    "total_spent": (User.total_spent.asc(), User.id.desc()),
    "-total_spent": (User.total_spent.desc(), User.id.desc()),
}


def members_query(
    db: Session, q: str | None, tier: int | None, sort: str | None = None,
    risk: int | None = None,
) -> Query:
    query = db.query(User).filter(User.role == 0)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.email.ilike(like), User.name.ilike(like)))
    if tier is not None:
        query = query.filter(User.tier == tier)
    if risk is not None:
        query = query.filter(User.risk_flag == risk)
    order = _MEMBER_SORTS.get(sort or "")
    if order is None:
        # 非法/缺省排序走默认 id 倒序
        return query.order_by(User.id.desc())
    return query.order_by(*order)


def member_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def member_ledger_recent(db: Session, user_id: int, limit: int = 10) -> list[PointsLedger]:
    return (
        db.query(PointsLedger)
        .filter(PointsLedger.user_id == user_id)
        .order_by(PointsLedger.id.desc())
        .limit(limit)
        .all()
    )


# ===== 评价/UGC 审核（后台 /api/admin/ops 列表与批量队列） =====


def admin_reviews_query(
    db: Session, status: int | None, rating: int | None = None,
    product_id: int | None = None,
) -> Query:
    q = db.query(Review).order_by(Review.id.desc())
    if status is not None:
        q = q.filter(Review.status == status)
    if rating is not None:
        q = q.filter(Review.rating == rating)
    if product_id is not None:
        q = q.filter(Review.product_id == product_id)
    return q


def reviews_pending_by_ids(db: Session, ids: list[int]) -> list[Review]:
    """批量审核候选：仅取待审(0)记录，非待审/不存在静默跳过"""
    return (
        db.query(Review).filter(Review.id.in_(ids), Review.status == 0).all()
        if ids else []
    )


def ugc_pending_by_ids(db: Session, ids: list[int]) -> list[UgcSubmission]:
    return (
        db.query(UgcSubmission)
        .filter(UgcSubmission.id.in_(ids), UgcSubmission.status == 0).all()
        if ids else []
    )


# ===== 审计日志 =====


def admin_logs_query(
    db: Session, entity: str | None, *, action: str | None = None,
    admin_id: int | None = None, start=None, end=None,
) -> Query:
    q = db.query(AdminLog).order_by(AdminLog.id.desc())
    if entity:
        q = q.filter(AdminLog.entity == entity)
    if action:
        q = q.filter(AdminLog.action == action)
    if admin_id is not None:
        q = q.filter(AdminLog.admin_id == admin_id)
    if start is not None:
        q = q.filter(AdminLog.created_at >= start)
    if end is not None:
        q = q.filter(AdminLog.created_at <= end)
    return q


def users_by_ids(db: Session, ids: set[int]) -> list[User]:
    """日志 admin_name 回填用批量查询（避免逐行 join/查用户）"""
    return db.query(User).filter(User.id.in_(ids)).all() if ids else []


# ===== 运营队列：弃购 / 对账 / GDPR 数据请求 / Newsletter =====

# 弃购判定对齐 worker 口径（scripts/worker.py ABANDON_STAGES[0]）：有商品且最后活跃
# 超过第 1 封召回窗口（1 小时）未下单的 cart（下单成功后 cart.items 会被清空）
ABANDON_CUTOFF = timedelta(hours=1)


def abandoned_carts_query(db: Session, cutoff: datetime) -> Query:
    """cutoff = now - ABANDON_CUTOFF，由 service 层计算传入（naive UTC 口径）；
    仅保留有邮箱可触达的行（email 非空，与 worker scan_abandoned_carts 过滤口径一致）"""
    return (
        db.query(Cart)
        .filter(_has_items(db), Cart.updated_at <= cutoff,
                Cart.email.isnot(None), Cart.email != "")
        .order_by(Cart.updated_at.desc(), Cart.id.desc())
    )


def variants_by_ids(db: Session, ids: set[int]) -> list[Variant]:
    """弃购金额估算用批量取价（仅按页内出现的 variantId 批查，避免 N+1）"""
    return db.query(Variant).filter(Variant.id.in_(ids)).all() if ids else []


def reconciliations_query(
    db: Session, date_from: date | None = None, date_to: date | None = None,
) -> Query:
    q = db.query(ReconciliationDaily).order_by(
        ReconciliationDaily.reconcile_date.desc(), ReconciliationDaily.id.desc()
    )
    if date_from is not None:
        q = q.filter(ReconciliationDaily.reconcile_date >= date_from)
    if date_to is not None:
        q = q.filter(ReconciliationDaily.reconcile_date <= date_to)
    return q


def data_requests_query(
    db: Session, type_: int | None = None, status: int | None = None,
) -> Query:
    q = db.query(DataRequest).order_by(DataRequest.id.desc())
    if type_ is not None:
        q = q.filter(DataRequest.type == type_)
    if status is not None:
        q = q.filter(DataRequest.status == status)
    return q


def data_request_by_id(db: Session, req_id: int) -> DataRequest | None:
    return db.get(DataRequest, req_id)


def newsletters_query(db: Session, q: str | None) -> Query:
    query = db.query(NewsletterSubscriber).order_by(
        NewsletterSubscriber.created_at.desc(), NewsletterSubscriber.email.asc()
    )
    if q:
        query = query.filter(NewsletterSubscriber.email.ilike(f"%{q}%"))
    return query


def admin_email_taken(db: Session, email: str, exclude_id: int | None = None) -> bool:
    query = db.query(User.id).filter(User.email == email)
    if exclude_id is not None:
        query = query.filter(User.id != exclude_id)
    return query.first() is not None


def admin_by_id(db: Session, admin_id: int) -> User | None:
    return db.get(User, admin_id)
