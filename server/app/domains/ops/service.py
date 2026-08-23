"""运营域服务 —— 看板聚合编排 / 会员管理与风控 / 审计日志 / 运营队列（弃购/对账/GDPR/Newsletter/管理员账号）"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.security import hash_password
from app.models import AdminLog, Review, UgcSubmission, User
from app.domains.content import service as content_service
from app.domains.content.schemas import ReasonIn
from app.domains.member.service_account import _gdpr_delay_days, anonymize_user
from app.domains.ops import repository as repo
from app.domains.ops.schemas import (
    REASON_TEXT, AdminCreateIn, AdminUpdateIn, PointsAdjustIn,
    ReviewBulkIn, RiskIn, UgcBulkIn,
)
from app.services import points as points_svc

logger = logging.getLogger("glowmag.ops")


def log_admin(db: Session, admin: User, action: str, entity: str, entity_id: int, diff: dict | None = None):
    db.add(AdminLog(
        admin_id=admin.id,
        action=action,
        entity=entity,
        entity_id=int(entity_id or 0),
        diff_json=diff,
    ))


def _naive_utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ===== 看板 =====


def dashboard(db: Session) -> dict:
    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _win(start):
        orders = repo.orders_placed_since(db, start)
        gmv = repo.paid_gmv_since(db, start)
        return {"gmv_cents": int(gmv), "orders": int(orders)}

    views = repo.newsletter_count(db) + repo.cookie_consent_count(db)
    add_to_cart = repo.carts_with_items_count(db)
    orders_today = repo.orders_placed_since(db, today_start)
    paid_today = repo.paid_orders_since(db, today_start)
    cutoff = _naive_utcnow() - timedelta(hours=24)
    abandoned = repo.abandoned_carts_count(db, cutoff)
    pending_orders = repo.pending_orders_count(db)
    unpaid_orders = repo.unpaid_orders_count(db)
    low_stock = repo.low_stock_count(db)
    pending_reviews = repo.pending_reviews_count(db)
    open_tickets = repo.open_tickets_count(db)
    top = repo.top_products(db, 5)
    daily: list = []
    try:
        d_start = (now - timedelta(days=13)).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = repo.daily_paid_rows(db, d_start)
        by_day = {str(r[0]): (int(r[1] or 0), int(r[2] or 0)) for r in rows}
        for i in range(14):
            day = (d_start + timedelta(days=i)).date()
            gmv, cnt = by_day.get(str(day), (0, 0))
            daily.append({"date": day.strftime("%m-%d"), "gmv_cents": gmv, "orders": cnt})
    except Exception:
        logger.warning("dashboard daily paid aggregation failed", exc_info=True)
        daily = []
    reconcile = None
    try:
        rec = repo.latest_reconciliation(db)
        if rec:
            reconcile = {
                "reconcile_date": rec.reconcile_date,
                "diff_payment": rec.diff_payment,
                "diff_points": rec.diff_points,
                "status": rec.status,
            }
    except Exception:
        logger.warning("dashboard latest reconciliation failed", exc_info=True)
        reconcile = None
    low_stock_top: list = []
    try:
        lows = repo.low_stock_top_rows(db, 5)
        low_stock_top = [{"sku": r[0], "title": r[1], "stock": r[2]} for r in lows]
    except Exception:
        logger.warning("dashboard low stock top failed", exc_info=True)
        low_stock_top = []
    return {
        "today": _win(today_start),
        "last7": _win(now - timedelta(days=7)),
        "last30": _win(now - timedelta(days=30)),
        "funnel": {
            "views": int(views),
            "add_to_cart": add_to_cart,
            "orders": int(orders_today),
            "paid": int(paid_today),
            "approximate": True,
        },
        "pending_orders": int(pending_orders),
        "unpaid_orders": int(unpaid_orders),
        "low_stock": int(low_stock),
        "pending_reviews": int(pending_reviews),
        "open_tickets": int(open_tickets),
        "abandoned_carts": abandoned,
        "top_products": [
            {"id": p.id, "slug": p.slug, "title": p.title, "sold_count": p.sold_count}
            for p in top
        ],
        "daily": daily,
        "reconcile": reconcile,
        "low_stock_top": low_stock_top,
    }


# ===== 会员管理 =====


def list_members(
    db: Session, q: str | None, tier: int | None, page: int, size: int,
    sort: str | None = None, risk: int | None = None,
) -> dict:
    query = repo.members_query(db, q, tier, sort, risk)
    rows, total = repo.page(query, page, size)
    return {
        "items": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "tier": u.tier,
                "points": u.points,
                "total_spent": u.total_spent,
                "last_order_at": u.last_order_at,
                "risk_flag": u.risk_flag,
            }
            for u in rows
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


def member_detail(db: Session, user_id: int) -> dict:
    u = repo.member_by_id(db, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="member not found")
    ledger = repo.member_ledger_recent(db, u.id, 10)
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "tier": u.tier,
        "points": u.points,
        "total_spent": u.total_spent,
        "last_order_at": u.last_order_at,
        "risk_flag": u.risk_flag,
        "created_at": u.created_at,
        "ledger": [
            {
                "id": r.id,
                "change": r.change,
                "balance_after": r.balance_after,
                "reason": REASON_TEXT.get(r.reason, str(r.reason)),
                "frozen": r.frozen,
                "created_at": r.created_at,
            }
            for r in ledger
        ],
    }


def member_risk(db: Session, admin: User, user_id: int, body: RiskIn) -> dict:
    u = repo.member_by_id(db, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="member not found")
    u.risk_flag = body.flag
    log_admin(db, admin, "risk", "member", u.id, {"risk_flag": body.flag})
    db.commit()
    db.refresh(u)
    return {"id": u.id, "risk_flag": u.risk_flag}


def list_admins(db: Session) -> dict:
    """管理账号列表（供工单指派选择器）：role>=2 且启用中，按 id 升序"""
    rows = (
        db.query(User)
        .filter(User.role >= 2, User.status == 1)
        .order_by(User.id.asc())
        .all()
    )
    return {
        "items": [
            {"id": u.id, "name": u.name, "email": u.email, "role": u.role}
            for u in rows
        ]
    }


def member_points_adjust(db: Session, admin: User, user_id: int, body: PointsAdjustIn) -> dict:
    """积分人工调整：走 points.admin_adjust 公共通道（原子增减 + ADMIN_ADJUST 流水），
    此处仅补审计日志并统一提交"""
    balance = points_svc.admin_adjust(db, user_id, body.delta, admin_id=admin.id)
    log_admin(db, admin, "points_adjust", "member", user_id,
              {"delta": body.delta, "reason": body.reason})
    db.commit()
    return {"ok": True, "balance": balance}


# ===== 评价/UGC 审核（/api/admin/ops，复用 content 域单条 approve/reject） =====


def admin_reviews(
    db: Session, status: int | None, rating: int | None,
    product_id: int | None, page: int, size: int,
) -> dict:
    """后台评价队列：在 content 域列表基础上加 rating/product_id 过滤（响应结构不变）"""
    rows, total = repo.page(
        repo.admin_reviews_query(db, status, rating, product_id), page, size,
    )
    return {
        "items": [
            {
                "id": r.id,
                "product_id": r.product_id,
                "user_id": r.user_id,
                "order_item_id": r.order_item_id,
                "rating": r.rating,
                "content": r.content,
                "images": r.images,
                "status": r.status,
                "reject_reason": r.reject_reason,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


def bulk_reviews(db: Session, admin: User, body: ReviewBulkIn) -> dict:
    """批量审核：仅处理待审(0)记录（非待审/不存在跳过），单条逻辑复用 content 域 service"""
    rows = repo.reviews_pending_by_ids(db, body.ids)
    for r in rows:
        if body.action == "approve":
            content_service.approve_review(db, admin, r.id)
        else:
            content_service.reject_review(db, admin, r.id, ReasonIn(reason=body.reason or ""))
    return {"updated": len(rows)}


def unapprove_review(db: Session, admin: User, review_id: int) -> dict:
    """审核撤回：1通过/2拒绝 → 0 重新待审；撤回已通过评价需重算商品评分聚合"""
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(status_code=404, detail="review not found")
    if r.status not in (1, 2):
        raise HTTPException(status_code=409, detail="invalid_status")
    prev = r.status
    r.status = 0
    if prev == 1:
        content_service._recalc_rating(db, r.product_id)
    log_admin(db, admin, "unapprove", "review", r.id, {"from": prev, "to": 0})
    db.commit()
    return {"id": r.id, "status": r.status}


def bulk_ugc(db: Session, admin: User, body: UgcBulkIn) -> dict:
    """UGC 批量审核：与评价同构（无 reason），单条逻辑复用 content 域 service"""
    rows = repo.ugc_pending_by_ids(db, body.ids)
    for u in rows:
        if body.action == "approve":
            content_service.approve_ugc(db, admin, u.id)
        else:
            content_service.reject_ugc(db, admin, u.id)
    return {"updated": len(rows)}


def unapprove_ugc(db: Session, admin: User, ugc_id: int) -> dict:
    """UGC 审核撤回：1上墙/2拒绝 → 0 重新待审（已发积分不回收）"""
    u = db.get(UgcSubmission, ugc_id)
    if not u:
        raise HTTPException(status_code=404, detail="ugc not found")
    if u.status not in (1, 2):
        raise HTTPException(status_code=409, detail="invalid_status")
    prev = u.status
    u.status = 0
    log_admin(db, admin, "unapprove", "ugc", u.id, {"from": prev, "to": 0})
    db.commit()
    return {"id": u.id, "status": u.status}


# ===== 审计日志 =====


def _parse_log_dt(value: str, name: str) -> datetime:
    """ISO 日期(时间)解析：支持 Z 后缀与显式时区，统一落 naive UTC（与 created_at 列口径一致）"""
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid {name}")
    if d.tzinfo is not None:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d


def admin_logs(
    db: Session, entity: str | None, page: int, size: int, *,
    action: str | None = None, admin_id: int | None = None,
    start: str | None = None, end: str | None = None,
) -> dict:
    start_at = _parse_log_dt(start, "start") if start else None
    end_at = _parse_log_dt(end, "end") if end else None
    q = repo.admin_logs_query(
        db, entity, action=action, admin_id=admin_id, start=start_at, end=end_at
    )
    rows, total = repo.page(q, page, size)
    admins = {u.id: (u.name or u.email) for u in repo.users_by_ids(
        db, {a.admin_id for a in rows}
    )}
    return {
        "items": [
            {
                "id": a.id,
                "admin_id": a.admin_id,
                "admin_name": admins.get(a.admin_id),
                "action": a.action,
                "entity": a.entity,
                "entity_id": a.entity_id,
                "diff_json": a.diff_json,
                "created_at": a.created_at,
            }
            for a in rows
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


# ===== 运营队列：弃购 / 对账历史 / GDPR 数据请求 / Newsletter =====


def abandoned_carts(db: Session, page: int, size: int) -> dict:
    """弃购队列：口径对齐 worker（有商品 + 最后活跃超 1 小时未下单），
    按最后活跃倒序；金额按页内 variantId 批量取价估算"""
    cutoff = _naive_utcnow() - repo.ABANDON_CUTOFF
    rows, total = repo.page(repo.abandoned_carts_query(db, cutoff), page, size)
    prices = {
        v.id: v.price for v in repo.variants_by_ids(
            db, {it.get("variantId") for c in rows for it in (c.items or [])}
        )
    }
    now = _naive_utcnow()
    items = []
    for c in rows:
        entries = c.items or []
        items.append({
            "id": c.id,
            "email": c.email,
            "items_count": len(entries),
            "total_qty": sum(int(it.get("qty") or 0) for it in entries),
            "amount_cents": sum(
                int(it.get("qty") or 0) * prices.get(it.get("variantId"), 0)
                for it in entries
            ),
            "updated_at": c.updated_at,
            "days_ago": round((now - c.updated_at).total_seconds() / 86400, 1)
            if c.updated_at else None,
        })
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


def reconciliations(
    db: Session, page: int, size: int,
    date_from: datetime | None = None, date_to: datetime | None = None,
) -> dict:
    """对账历史：按日期倒序，可按日期区间过滤"""
    rows, total = repo.page(
        repo.reconciliations_query(db, date_from, date_to), page, size
    )
    return {
        "items": [
            {
                "id": r.id,
                "reconcile_date": r.reconcile_date,
                "payments_gross": r.payments_gross,
                "orders_paid_total": r.orders_paid_total,
                "diff_payment": r.diff_payment,
                "diff_refund": r.diff_refund,
                "points_ledger_sum": r.points_ledger_sum,
                "users_points_sum": r.users_points_sum,
                "diff_points": r.diff_points,
                "status": r.status,
                "checked_at": r.checked_at,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


# DataRequest 状态：0受理 1完成（worker/用户侧既有语义）+ 2驳回（后台审核扩展）
_TYPE_TEXT = {1: "导出", 2: "删除"}
_STATUS_TEXT = {0: "受理中", 1: "已完成", 2: "已驳回"}


def data_requests(
    db: Session, page: int, size: int,
    type_: int | None = None, status: int | None = None,
) -> dict:
    rows, total = repo.page(repo.data_requests_query(db, type_, status), page, size)
    users = {u.id: u for u in repo.users_by_ids(db, {r.user_id for r in rows})}
    delay_days = _gdpr_delay_days(db)
    return {
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "email": users[r.user_id].email if r.user_id in users else None,
                "type": r.type,
                "type_text": _TYPE_TEXT.get(r.type, str(r.type)),
                "status": r.status,
                "status_text": _STATUS_TEXT.get(r.status, str(r.status)),
                "created_at": r.created_at,
                # 计划执行时间：删除类 = 申请时间 + 冷静期（对齐 worker 到期口径）
                "scheduled_at": (
                    r.created_at + timedelta(days=delay_days) if r.type == 2 else None
                ),
                "fulfilled_at": r.fulfilled_at,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


def reject_data_request(db: Session, admin: User, req_id: int) -> dict:
    """驳回：仅受理中(0)可驳回（已执行/已驳回 → 409）"""
    req = repo.data_request_by_id(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="data request not found")
    if req.status != 0:
        raise HTTPException(status_code=409, detail="request not pending")
    req.status = 2
    log_admin(db, admin, "reject", "data_request", req.id, {"status": 2})
    db.commit()
    return {"id": req.id, "status": req.status}


def execute_data_request(db: Session, admin: User, req_id: int) -> dict:
    """立即执行：删除类走 anonymize_user（与 worker 同一实现），
    导出类申请时即已完成（正常不会出现 pending 导出单，防御性直接置完成）；
    已执行/已驳回 → 409"""
    req = repo.data_request_by_id(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="data request not found")
    if req.status != 0:
        raise HTTPException(status_code=409, detail="request not pending")
    anonymized = anonymize_user(db, req.user_id) if req.type == 2 else False
    req.status = 1
    req.fulfilled_at = utcnow()
    log_admin(db, admin, "execute", "data_request", req.id,
              {"type": req.type, "status": 1, "anonymized": anonymized})
    db.commit()
    return {"id": req.id, "status": req.status, "anonymized": anonymized}


def newsletters(db: Session, page: int, size: int, q: str | None = None) -> dict:
    """Newsletter 订阅者：按订阅时间倒序，q 模糊搜索 email"""
    rows, total = repo.page(repo.newsletters_query(db, q), page, size)
    return {
        "items": [
            {
                "email": n.email,
                "source": n.source,
                "klaviyo_synced": n.klaviyo_synced,
                "created_at": n.created_at,
            }
            for n in rows
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


# ===== 管理员账号管理（仅超管） =====


def _admin_out(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "status": u.status,
        "last_login_at": u.last_login_at,
        "created_at": u.created_at,
    }


def create_admin(db: Session, admin: User, body: AdminCreateIn) -> dict:
    email = body.email.strip().lower()
    if repo.admin_email_taken(db, email):
        raise HTTPException(status_code=409, detail="email exists")
    account = User(
        email=email,
        password_hash=hash_password(body.password),
        name=body.name.strip(),
        role=body.role,
        status=1,
    )
    db.add(account)
    db.flush()
    log_admin(db, admin, "create", "admin", account.id,
              {"email": email, "name": account.name, "role": body.role})
    db.commit()
    db.refresh(account)
    return _admin_out(account)


def update_admin(db: Session, admin: User, admin_id: int, body: AdminUpdateIn) -> dict:
    account = repo.admin_by_id(db, admin_id)
    if not account or account.role < 2:
        raise HTTPException(status_code=404, detail="admin not found")
    data = body.model_dump(exclude_unset=True)
    if admin_id == admin.id and ("role" in data or "status" in data):
        # 不能改自己角色 / 停用自己（避免超管自锁后台）
        raise HTTPException(status_code=400, detail="cannot modify self")
    if "email" in data:
        data.pop("email")
    if not data:
        raise HTTPException(status_code=400, detail="no fields to update")
    for k, v in data.items():
        setattr(account, k, v)
    log_admin(db, admin, "update", "admin", account.id, dict(data))
    db.commit()
    db.refresh(account)
    return _admin_out(account)


def admin_detail(db: Session, admin_id: int) -> dict:
    account = repo.admin_by_id(db, admin_id)
    if not account or account.role < 2:
        raise HTTPException(status_code=404, detail="admin not found")
    return _admin_out(account)
