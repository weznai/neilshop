"""订阅月盒服务（用户侧 MVP）。

计划口径对齐 prototype/subscribe.html：每4周 $12.99 / 每6周 $13.99 / 每8周 $14.99
（美分 1299/1399/1499）；stripe_subscription_id 用 "SUBMOCK"+hex12 占位。
"""

import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import Subscription, User

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


def my_subscriptions(db: Session, user: User) -> dict:
    rows = repo.list_subscriptions(db, user.id)
    plans = [
        {"id": pid, "weeks": p["weeks"], "price_cents": p["price_cents"]}
        for pid, p in PLANS.items()
    ]
    return {"items": [_sub_out(r) for r in rows], "plans": plans}


def create(db: Session, user: User, body: SubscriptionCreateIn) -> dict:
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
    if sub.status != 1:
        raise HTTPException(status_code=409, detail="not active")
    sub.status = 2
    sub.resume_at = body.resume_at
    db.commit()
    return _sub_out(sub)


def resume(db: Session, user: User, sub_id: int) -> dict:
    sub = _get_owned(db, user.id, sub_id)
    if sub.status != 2:
        raise HTTPException(status_code=409, detail="not paused")
    now = utcnow()
    if sub.next_billing_at is None or sub.next_billing_at <= now:
        sub.next_billing_at = now + timedelta(weeks=PLANS[sub.plan]["weeks"])
    sub.status = 1
    sub.resume_at = None
    db.commit()
    return _sub_out(sub)


def cancel(db: Session, user: User, sub_id: int, body: SubscriptionCancelIn) -> dict:
    sub = _get_owned(db, user.id, sub_id)
    if sub.status not in (1, 2):
        raise HTTPException(status_code=409, detail="not cancellable")
    sub.status = 5
    sub.cancel_reason = body.cancel_reason
    db.commit()
    return _sub_out(sub)


def skip(db: Session, user: User, sub_id: int, body: SubscriptionSkipIn) -> dict:
    sub = _get_owned(db, user.id, sub_id)
    if sub.status != 1:
        raise HTTPException(status_code=409, detail="not active")
    sub.skip_until = body.skip_until
    db.commit()
    return _sub_out(sub)
