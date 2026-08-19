"""积分服务（读侧）：余额总览/流水/即将过期。

写侧（发放/消费/退款作废）公共契约仍在 app.services.points（交易/营销域共用，集成者持有）。
"""

from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import PointsLedger, User
from app.services import points as points_svc

from app.domains.member import repository as repo

REASON_TEXT = {
    1: "下单获得（冻结中）",
    2: "解冻",
    3: "评价奖励",
    4: "签到",
    5: "推荐奖励",
    6: "生日礼",
    7: "消费扣除",
    8: "退款作废",
    9: "退款返还",
    10: "过期",
    11: "管理员调整",
    12: "买家秀奖励",
}


def _ledger_item(r: PointsLedger) -> dict:
    return {
        "id": r.id,
        "change": r.change,
        "balance_after": r.balance_after,
        "reason": REASON_TEXT.get(r.reason, str(r.reason)),
        "reason_code": r.reason,
        "frozen": r.frozen,
        "ref_type": r.ref_type,
        "ref_id": r.ref_id,
        "expires_at": r.expires_at,
        "created_at": r.created_at,
    }


def summary(db: Session, user: User) -> dict:
    balance = points_svc.get_balance(db, user.id)
    usable = points_svc.usable_balance(db, user.id)
    return {"balance": balance, "frozen": balance - usable, "usable": usable}


def ledger(db: Session, user: User, page: int, size: int) -> dict:
    total, rows = repo.ledger_page(db, user.id, (page - 1) * size, size)
    return {
        "items": [_ledger_item(r) for r in rows],
        "total": total,
        "page": page,
        "size": size,
    }


def expiring(db: Session, user: User) -> dict:
    rows = repo.expiring_ledger_rows(db, user.id, utcnow())
    return {"items": [_ledger_item(r) for r in rows]}
