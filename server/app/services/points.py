"""积分服务 —— B(交易)/C(营销) 智能体的公共契约，由集成者持有，路由层不得改写语义
规则（与原型 rewards 页一致）：
- 赚取: 消费 $1 = 10 分（可配 points_per_dollar_earn）
- 兑换: 100 分 = $1（points_per_dollar_redeem 键固定 100）
- 下单获得先冻结（frozen=1），订单完成/过退货期后解冻
- 退款时未解冻部分作废（REFUND_VOID），已消费积分返还（REFUND_RETURN）
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.enums import PointsReason
from app.models import Order, PointsLedger, Setting, User

# 原子扣减/回补（余额守卫放进 WHERE，rowcount=0 即余额不足，杜绝并发双花）
# 可用额守卫一并下推 SQL：扣减后余额须 ≥ 冻结额（points_ledger 中 frozen=1 的正流水和，
# 与 usable_balance 口径一致），封死 Python 预检（ORM 读）与实际扣减（SQL）之间的并发窗口；
# `change` 在 MySQL 是保留字须反引号（SQLite 兼容该引号），子查 points_ledger 非被更新表，两库均合法
_SPEND_SQL = text(
    "UPDATE users SET points = points - :amt WHERE id = :uid "
    "AND points - :amt >= (SELECT COALESCE(SUM(`change`), 0) FROM points_ledger "
    "WHERE user_id = :uid AND frozen = 1 AND `change` > 0)"
)
_ADD_POINTS_SQL = text("UPDATE users SET points = points + :amt WHERE id = :uid")
_POINTS_OF_SQL = text("SELECT points FROM users WHERE id = :uid")
# GDPR 匿名化清零（置 0 无需守卫；与 _VOID_POINTS_SQL 同为 raw 通道防 ORM 脏值覆盖）
_ZERO_POINTS_SQL = text("UPDATE users SET points = 0 WHERE id = :uid")
# 管理员人工扣减（delta 为负）：余额守卫进 WHERE，并发下不会扣成负数
_ADMIN_DEBIT_SQL = text(
    "UPDATE users SET points = points + :delta WHERE id = :uid AND points + :delta >= 0"
)
# 作废扣减（下限 0）：raw SQL 与 _ADD_POINTS_SQL 同通道，避免同事务内 ORM 脏值
# 在 commit flush 时覆盖 refund_return 的回补；CASE 下限写法 MySQL/SQLite 通用
_VOID_POINTS_SQL = text(
    "UPDATE users SET points = CASE WHEN points < :amt THEN 0 ELSE points - :amt END "
    "WHERE id = :uid"
)


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


def earn_rate(db: Session) -> int:
    """消费 $1 赚取积分数：读取运营设置 points_per_dollar_earn（缺省 10），
    非法/越界值回落默认，保证支付路径永不因配置报错"""
    row = db.query(Setting).filter(Setting.key == "points_per_dollar_earn").first()
    if row is None or row.value is None:
        return 10
    try:
        rate = int(row.value)
    except (TypeError, ValueError):
        return 10
    return rate if 0 <= rate <= 1_000_000 else 10


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


def add_points(db: Session, user_id: int, delta: int) -> int:
    """发放类原子累加公共原语（推荐奖励/grant/GDPR/后续 worker 复用）：
    raw UPDATE + 回读现值，返回新余额；调用方自写 ledger（balance_after 用返回值），
    杜绝 ORM 读-改-写在并发提交时丢更新（少发积分）。只写不 commit，事务归调用方。"""
    db.execute(_ADD_POINTS_SQL, {"uid": user_id, "amt": delta})
    return int(db.execute(_POINTS_OF_SQL, {"uid": user_id}).scalar())


def clear_points(db: Session, user_id: int, *, ref_type: str = "gdpr",
                 ref_id: int | None = None) -> int:
    """GDPR 匿名化积分清零：原子置 0 并补写 ledger（reason=ADMIN_ADJUST，balance_after=0），
    保证对账 diff_points=0；余额本就为 0 时不写空流水。返回清零前余额。"""
    balance = int(db.execute(_POINTS_OF_SQL, {"uid": user_id}).scalar() or 0)
    if balance > 0:
        db.execute(_ZERO_POINTS_SQL, {"uid": user_id})
        _write_ledger(db, user_id, -balance, PointsReason.ADMIN_ADJUST, 0,
                      ref_type=ref_type, ref_id=ref_id)
    return balance


def grant_for_order(db: Session, order: Order, points_earned: int) -> PointsLedger | None:
    """支付成功后发放（冻结）。B 的支付回调在同一事务内调用。"""
    if not order.user_id or points_earned <= 0:
        return None
    if db.get(User, order.user_id) is None:
        return None
    # 原子累加后回读现值写 ledger（对齐 refund_void/refund_return 写法）：
    # ORM user.points += 在并发回调下会丢更新（少发积分）；不改 user.points 属性，
    # 避免 commit flush 时 ORM 脏快照覆盖 raw 扣减结果
    balance = add_points(db, order.user_id, points_earned)
    entry = _write_ledger(
        db, order.user_id, points_earned, PointsReason.ORDER_EARN_FROZEN, balance,
        ref_type="order", ref_id=order.id, frozen=1,
    )
    order.points_earned = points_earned
    return entry


def spend(db: Session, user_id: int, points: int, order_id: int | None = None) -> int:
    """下单用分（先扣，退款走返还）；返回扣减后余额。可用不足时抛 ValueError。
    扣减为原子 UPDATE，守卫进 WHERE（余额足够 且 扣后不侵占冻结额），并发下不会
    扣成负数/双花/花掉冻结分。Python 预检仅保留友好报错，以 SQL 守卫为准。"""
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


def admin_adjust(db: Session, user_id: int, delta: int, *, admin_id: int) -> int:
    """管理员人工调整积分（delta>0 加 / delta<0 减），返回调整后余额。
    加分走 _ADD_POINTS_SQL 通道；扣分走余额守卫的原子 UPDATE（rowcount=0 → 409 余额不足）；
    流水 reason=ADMIN_ADJUST(11)、ref_type="admin"、ref_id=操作管理员 id。
    事务边界与 spend/grant_for_order 一致：只写不 commit，由调用方统一提交。"""
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="user not found")
    if delta > 0:
        db.execute(_ADD_POINTS_SQL, {"uid": user_id, "amt": delta})
    else:
        if db.execute(_ADMIN_DEBIT_SQL, {"uid": user_id, "delta": delta}).rowcount == 0:
            raise HTTPException(status_code=409, detail="insufficient points")
    balance = int(db.execute(_POINTS_OF_SQL, {"uid": user_id}).scalar())
    _write_ledger(db, user_id, delta, PointsReason.ADMIN_ADJUST, balance,
                  ref_type="admin", ref_id=admin_id)
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
    user = db.get(User, order.user_id)
    if not user:
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
    # raw SQL 扣减（下限 0）：与 refund_return 的 raw 回补同事务共存，
    # ORM 赋值会在 commit flush 时用脏快照覆盖回补结果
    db.execute(_VOID_POINTS_SQL, {"uid": order.user_id, "amt": void_total})
    balance = int(db.execute(_POINTS_OF_SQL, {"uid": order.user_id}).scalar())
    for r in frozen_rows:
        r.frozen = 0
    _write_ledger(db, order.user_id, -void_total, PointsReason.REFUND_VOID,
                  balance, ref_type="order", ref_id=order.id)
