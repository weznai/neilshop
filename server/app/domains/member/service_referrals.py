"""推荐有礼服务 —— 用户侧（我的推荐/模拟邀请）+ on_order_paid 支付钩子。

on_order_paid 由 payments.mark_order_paid 在同一事务内调用（经
app/services/referrals.py 兼容 shim 转发）；derive_code 为确定性派生：
sha256(f"{user.id}:{settings.jwt_secret}")[:8].upper()。
"""

import hashlib

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.enums import PointsReason, ReferralStatus
from app.models import (
    Order, OrderTimeline, PointsLedger, Referral, User,
)

from app.domains.member import repository as repo
from app.domains.member.schemas import SimulateInviteIn


def derive_code(user_id: int) -> str:
    digest = hashlib.sha256(f"{user_id}:{settings.jwt_secret}".encode()).hexdigest()
    return "GLOW-" + digest[:8].upper()


STATUS_TEXT = {
    int(ReferralStatus.CLICKED): "点击注册",
    int(ReferralStatus.REGISTERED): "已注册",
    int(ReferralStatus.FIRST_ORDER): "首单待确认",
    int(ReferralStatus.REWARDED): "已奖励",
    int(ReferralStatus.INVALID): "无效",
}


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) < 2:
        return f"{local}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


def my_referrals(db: Session, user: User) -> dict:
    code = derive_code(user.id)
    rows = repo.referrals_by_referrer(db, user.id)
    earned = repo.referral_points_earned(
        db, user.id, int(PointsReason.REFERRAL)
    )
    invited = [
        {
            "email_masked": _mask_email(r.invited_email),
            "status": r.status,
            "status_text": STATUS_TEXT.get(r.status, str(r.status)),
            "created_at": r.created_at,
            "rewarded_at": r.rewarded_at,
        }
        for r in rows
    ]
    return {
        "code": code,
        "invited": invited,
        "stats": {
            "invited": len(rows),
            "rewarded": sum(1 for r in rows if r.status == int(ReferralStatus.REWARDED)),
            "points_earned": earned,
        },
    }


def simulate_invite(db: Session, user: User, body: SimulateInviteIn) -> dict:
    """手动登记邀请（滥用收紧）：
    - 环境门禁：仅 dev 开放（与 trade 域 mock-pay 同款，非 dev 一律 404）；
    - 目标邮箱已是注册用户 → 409（不允许把已注册邮箱直接置 REGISTERED 冒领奖励）；
    - 已有 (code, email) 行 → 409 already invited（uk_code_email 也不允许重复建行）；
    - 仅目标邮箱未注册且无既有行时创建，状态为 CLICKED（邀请待注册），
      待被邀人经 /register?ref= 真实注册后由 bind_referral_on_register 流转为 REGISTERED。"""
    if settings.env != "dev":
        raise HTTPException(status_code=404, detail="not_found")
    code = derive_code(user.id)
    if repo.find_referral(db, code, body.email):
        raise HTTPException(status_code=409, detail="already invited")
    if repo.user_id_by_email(db, body.email) is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    repo.add_referral(db, Referral(
        code=code,
        referrer_user_id=user.id,
        invited_email=body.email,
        invited_user_id=None,
        status=int(ReferralStatus.CLICKED),
    ))
    db.commit()
    return {"code": code}


def bind_referral_on_register(db: Session, ref_code: str | None, new_user: User) -> None:
    """/register?ref= 落地承诺的绑定闭环：注册时 ref_code 有效（存在且属于其它用户）则落
    Referral 记录。复用 invite→REGISTERED 既有流转：已有 CLICKED 行（如 simulate-invite
    预登记）就升级并回填 invited_user_id；无行则直接建 REGISTERED 行。幂等：状态已
    >= REGISTERED 的行不动。发放仍在 trade 域 on_order_paid（首单支付时按本记录发分）。"""
    code = (ref_code or "").strip().upper()
    if not code:
        return
    referrer_id = next(
        (uid for uid in repo.all_user_ids(db) if derive_code(uid) == code), None
    )
    if referrer_id is None or referrer_id == new_user.id:
        return  # 无效码 / 自邀：静默忽略，不阻断注册
    row = repo.find_referral(db, code, new_user.email)
    if row is None:
        repo.add_referral(db, Referral(
            code=code,
            referrer_user_id=referrer_id,
            invited_email=new_user.email,
            invited_user_id=new_user.id,
            status=int(ReferralStatus.REGISTERED),
        ))
    elif row.status == int(ReferralStatus.CLICKED):
        row.status = int(ReferralStatus.REGISTERED)
        row.invited_user_id = new_user.id


# ---------- 支付钩子 ----------

def _grant(db: Session, user: User, points: int, order_id: int) -> None:
    user.points += points
    db.add(PointsLedger(
        user_id=user.id, change=points, reason=int(PointsReason.REFERRAL),
        balance_after=user.points, ref_type="referral", ref_id=order_id,
        frozen=0, created_at=utcnow(),
    ))


def on_order_paid(db: Session, order: Order) -> None:
    rows = repo.pending_referrals_for_email(db, order.email)
    now = utcnow()
    for ref in rows:
        if ref.referrer_user_id == order.user_id:
            ref.status = int(ReferralStatus.INVALID)
            continue
        referrer = db.get(User, ref.referrer_user_id)
        if referrer is None:
            ref.status = int(ReferralStatus.INVALID)
            continue
        _grant(db, referrer, ref.reward_referrer, order.id)
        invitee_points = 0
        if ref.invited_user_id:
            invitee = db.get(User, ref.invited_user_id)
            if invitee:
                _grant(db, invitee, ref.reward_invitee, order.id)
                invitee_points = ref.reward_invitee
        ref.status = int(ReferralStatus.REWARDED)
        ref.rewarded_at = now
        ref.first_order_no = order.order_no
        repo.add_order_timeline(db, OrderTimeline(
            order_id=order.id, event="points_granted", actor="system",
            detail={
                "source": "referral", "referral_id": ref.id,
                "referrer_user_id": ref.referrer_user_id,
                "referrer_points": ref.reward_referrer,
                "invitee_points": invitee_points,
            },
        ))
