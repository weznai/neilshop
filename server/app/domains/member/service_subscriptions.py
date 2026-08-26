"""订阅月盒服务（用户侧 MVP）。

计划口径对齐 prototype/subscribe.html：每4周 $12.99 / 每6周 $13.99 / 每8周 $14.99
（美分 1299/1399/1499）；stripe_subscription_id 用 "SUBMOCK"+hex12 占位。
"""

import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import AdminLog, Subscription, User

from app.domains.member import repository as repo
from app.domains.member.schemas import (
    SubscriptionCancelIn, SubscriptionCreateIn, SubscriptionPauseIn, SubscriptionSkipIn,
)

PLANS = {
    1: {"weeks": 4, "price_cents": 1299},
    2: {"weeks": 6, "price_cents": 1399},
    3: {"weeks": 8, "price_cents": 1499},
}

PLAN_TEXT = {1: "每4周", 2: "每6周", 3: "每8周"}
STATUS_TEXT = {1: "生效中", 2: "已暂停", 5: "已取消"}


def _log_admin(db: Session, admin: User, action: str, sub_id: int, diff: dict) -> None:
    """管理端代操作审计（entity=subscription，与各域 admin log 同构）"""
    db.add(AdminLog(
        admin_id=admin.id, action=action, entity="subscription",
        entity_id=int(sub_id or 0), diff_json=diff,
    ))


def _sub_out(s: Subscription) -> dict:
    return {
        "id": s.id,
        "plan": s.plan,
        "plan_text": PLAN_TEXT.get(s.plan, str(s.plan)),
        "style_mode": s.style_mode,
        "status": s.status,
        "status_text": STATUS_TEXT.get(s.status, str(s.status)),
        "next_billing_at": s.next_billing_at,
        "resume_at": s.resume_at,
        "skip_until": s.skip_until,
        "cancel_reason": s.cancel_reason,
        "stripe_subscription_id": s.stripe_subscription_id,
        "created_at": s.created_at,
    }


def _get_owned(db: Session, user_id: int, sub_id: int) -> Subscription:
    sub = repo.get_subscription(db, user_id, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="subscription not found")
    return sub


# ---- 状态流转核心（用户侧与后台代操作共用同一状态机与错误码） ----


def _pause_core(sub: Subscription, body: SubscriptionPauseIn) -> None:
    if sub.status != 1:
        raise HTTPException(status_code=409, detail="not active")
    sub.status = 2
    sub.resume_at = body.resume_at


def _resume_core(sub: Subscription) -> None:
    if sub.status != 2:
        raise HTTPException(status_code=409, detail="not paused")
    now = utcnow()
    if sub.next_billing_at is None or sub.next_billing_at <= now:
        sub.next_billing_at = now + timedelta(weeks=PLANS[sub.plan]["weeks"])
    sub.status = 1
    sub.resume_at = None


def _cancel_core(sub: Subscription, body: SubscriptionCancelIn) -> None:
    if sub.status not in (1, 2):
        raise HTTPException(status_code=409, detail="not cancellable")
    sub.status = 5
    sub.cancel_reason = body.cancel_reason


def my_subscriptions(db: Session, user: User) -> dict:
    rows = repo.list_subscriptions(db, user.id)
    plans = [
        {"id": pid, "weeks": p["weeks"], "price_cents": p["price_cents"]}
        for pid, p in PLANS.items()
    ]
    return {"items": [_sub_out(r) for r in rows], "plans": plans}


def create(db: Session, user: User, body: SubscriptionCreateIn) -> dict:
    # 双开防线：同一用户已有生效（status=1）订阅 → 409（与地址簿/推荐域 409 风格一致）
    if repo.active_subscription(db, user.id) is not None:
        raise HTTPException(status_code=409, detail="subscription_exists")
    sub = Subscription(
        user_id=user.id,
        stripe_subscription_id="SUBMOCK" + secrets.token_hex(6),
        plan=body.plan,
        style_mode=body.style_mode,
        status=1,
        next_billing_at=utcnow() + timedelta(weeks=PLANS[body.plan]["weeks"]),
    )
    repo.add_subscription(db, sub)
    db.commit()
    db.refresh(sub)
    return _sub_out(sub)


def pause(db: Session, user: User, sub_id: int, body: SubscriptionPauseIn) -> dict:
    sub = _get_owned(db, user.id, sub_id)
    _pause_core(sub, body)
    db.commit()
    return _sub_out(sub)


def resume(db: Session, user: User, sub_id: int) -> dict:
    sub = _get_owned(db, user.id, sub_id)
    _resume_core(sub)
    db.commit()
    return _sub_out(sub)


def cancel(db: Session, user: User, sub_id: int, body: SubscriptionCancelIn) -> dict:
    sub = _get_owned(db, user.id, sub_id)
    _cancel_core(sub, body)
    db.commit()
    return _sub_out(sub)


def skip(db: Session, user: User, sub_id: int, body: SubscriptionSkipIn) -> dict:
    sub = _get_owned(db, user.id, sub_id)
    if sub.status != 1:
        raise HTTPException(status_code=409, detail="not active")
    sub.skip_until = body.skip_until
    db.commit()
    return _sub_out(sub)


# ===== 后台：订阅盒管理（/api/admin/member/subscriptions，代操作 + 审计） =====


def _get_by_id(db: Session, sub_id: int) -> Subscription:
    sub = db.get(Subscription, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="subscription not found")
    return sub


def admin_list(
    db: Session, status: int | None, page: int, size: int, q: str | None = None,
) -> dict:
    """后台订阅列表：分页 + status 筛选，按 created_at 倒序；q 按用户 email 模糊搜索；
    用户 email 批量回填（避免逐行查询）"""
    query = (
        db.query(Subscription)
        .outerjoin(User, User.id == Subscription.user_id)
        .order_by(Subscription.created_at.desc(), Subscription.id.desc())
    )
    if q:
        query = query.filter(User.email.ilike(f"%{q}%"))
    if status is not None:
        query = query.filter(Subscription.status == status)
    total = query.count()
    rows = query.offset((page - 1) * size).limit(size).all()
    users = {
        u.id: u for u in repo.users_by_ids(db, {r.user_id for r in rows})
    } if rows else {}
    return {
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "email": users[r.user_id].email if r.user_id in users else None,
                "plan": r.plan,
                "plan_text": PLAN_TEXT.get(r.plan, str(r.plan)),
                "price_cents": PLANS.get(r.plan, {}).get("price_cents"),
                "style_mode": r.style_mode,
                "status": r.status,
                "status_text": STATUS_TEXT.get(r.status, str(r.status)),
                "next_billing_at": r.next_billing_at,
                "resume_at": r.resume_at,
                "skip_until": r.skip_until,
                "cancel_reason": r.cancel_reason,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size,
    }


def admin_pause(db: Session, admin: User, sub_id: int, body: SubscriptionPauseIn) -> dict:
    """代用户暂停：状态机复用用户侧 _pause_core（错误码一致），仅补审计"""
    sub = _get_by_id(db, sub_id)
    _pause_core(sub, body)
    _log_admin(db, admin, "pause", sub.id, {"status": 2, "resume_at": body.resume_at})
    db.commit()
    return _sub_out(sub)


def admin_resume(db: Session, admin: User, sub_id: int) -> dict:
    sub = _get_by_id(db, sub_id)
    _resume_core(sub)
    _log_admin(db, admin, "resume", sub.id, {"status": 1})
    db.commit()
    return _sub_out(sub)


def admin_cancel(db: Session, admin: User, sub_id: int, body: SubscriptionCancelIn) -> dict:
    sub = _get_by_id(db, sub_id)
    _cancel_core(sub, body)
    _log_admin(db, admin, "cancel", sub.id,
               {"status": 5, "cancel_reason": body.cancel_reason})
    db.commit()
    return _sub_out(sub)
