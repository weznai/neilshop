"""积分服务 —— B(交易)/C(营销) 智能体的公共契约，由集成者持有，路由层不得改写语义
规则（与原型 rewards 页一致）：
- 赚取: 消费 $1 = 10 分（可配 points_per_dollar_earn）
- 兑换: 100 分 = $1（points_per_dollar_redeem 键固定 100）
- 下单获得先冻结（frozen=1），订单完成/过退货期后解冻
- 退款时未解冻部分作废（REFUND_VOID），已消费积分返还（REFUND_RETURN）
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.enums import PointsReason
from app.models import Order, PointsLedger, User

# 原子扣减/回补（余额守卫放进 WHERE，rowcount=0 即余额不足，杜绝并发双花）
_SPEND_SQL = text(
    "UPDATE users SET points = points - :amt WHERE id = :uid AND points >= :amt"
)
_ADD_POINTS_SQL = text("UPDATE users SET points = points + :amt WHERE id = :uid")
_POINTS_OF_SQL = text("SELECT points FROM users WHERE id = :uid")


def _write_ledger(db: Session, user_id: int, change: int, reason: PointsReason,
                  balance_after: int, *, ref_type: str | None = None,
                  ref_id: int | None = None, frozen: int = 0,
                  expires_at=None) -> PointsLedger:
    entry = PointsLedger(
        user_id=user_id, change=change, reason=int(reason),
        balance_after=balance_after, ref_type=ref_type, ref_id=ref_id,
        frozen=frozen, expires_at=expires_at, created_at=utcnow(),
    )
    db.add(entry)
    return entry


def get_balance(db: Session, user_id: int) -> int:
    user = db.get(User, user_id)
    return int(user.points) if user else 0


def usable_balance(db: Session, user_id: int) -> int:
    """可用 = 余额 - 冻结"""
    frozen = (
        db.query(PointsLedger)
        .filter(PointsLedger.user_id == user_id, PointsLedger.frozen == 1,
                PointsLedger.change > 0)
        .with_entities(PointsLedger.change)
    )
    frozen_sum = sum(r[0] for r in frozen) or 0
    return max(0, get_balance(db, user_id) - frozen_sum)


def grant_for_order(db: Session, order: Order, points_earned: int) -> PointsLedger | None:
    """支付成功后发放（冻结）。B 的支付回调在同一事务内调用。"""
    if not order.user_id or points_earned <= 0:
        return None
    user = db.get(User, order.user_id)
    if not user:
        return None
    user.points += points_earned
    entry = _write_ledger(
        db, user.id, points_earned, PointsReason.ORDER_EARN_FROZEN, user.points,
        ref_type="order", ref_id=order.id, frozen=1,
    )
    order.points_earned = points_earned
    return entry


def spend(db: Session, user_id: int, points: int, order_id: int | None = None) -> int:
    """下单用分（先扣，退款走返还）；返回扣减后余额。可用不足时抛 ValueError。
    扣减为原子 UPDATE（points >= :amt 守卫），并发下不会扣成负数/双花。"""
    if points <= 0:
        return get_balance(db, user_id)
    if points > usable_balance(db, user_id):
        raise ValueError("insufficient points")
    if db.execute(_SPEND_SQL, {"uid": user_id, "amt": points}).rowcount == 0:
        raise ValueError("insufficient points")
    balance = int(db.execute(_POINTS_OF_SQL, {"uid": user_id}).scalar())
    _write_ledger(db, user_id, -points, PointsReason.SPEND, balance,
                  ref_type="order", ref_id=order_id)
    return balance


def refund_return(db: Session, order: Order, user_id: int | None, amount: int) -> None:
    """已用积分返还（REFUND_RETURN=9）：用户取消 / 超时关单 / 全额退款路径共用。
    同单同 reason 幂等（重复调用只补一次）；amount<=0 或匿名单直接跳过。"""
    amt = int(amount or 0)
    if amt <= 0 or not user_id:
        return
    dup = (
        db.query(PointsLedger.id)
        .filter(PointsLedger.user_id == user_id,
                PointsLedger.reason == int(PointsReason.REFUND_RETURN),
                PointsLedger.ref_type == "order",
                PointsLedger.ref_id == order.id)
        .first()
    )
    if dup:
        return
    db.execute(_ADD_POINTS_SQL, {"uid": user_id, "amt": amt})
    balance = int(db.execute(_POINTS_OF_SQL, {"uid": user_id}).scalar())
    _write_ledger(db, user_id, amt, PointsReason.REFUND_RETURN, balance,
                  ref_type="order", ref_id=order.id)


def refund_void(db: Session, order: Order) -> None:
    """全额退款：作废该单冻结积分（若仍在冻结期）。"""
    if not order.user_id or order.points_earned <= 0:
        return
    frozen_rows = (
        db.query(PointsLedger)
        .filter(PointsLedger.user_id == order.user_id,
                PointsLedger.ref_type == "order",
                PointsLedger.ref_id == order.id,
                PointsLedger.frozen == 1,
                PointsLedger.change > 0)
        .all()
    )
    void_total = sum(r.change for r in frozen_rows)
    if void_total <= 0:
        return
    user = db.get(User, order.user_id)
    user.points = max(0, user.points - void_total)
    for r in frozen_rows:
        r.frozen = 0
    _write_ledger(db, order.user_id, -void_total, PointsReason.REFUND_VOID,
                  user.points, ref_type="order", ref_id=order.id)
