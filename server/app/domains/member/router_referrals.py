"""推荐有礼路由（薄层）：我的推荐/模拟邀请。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import User

from app.domains.member import service_referrals
from app.domains.member.schemas import SimulateInviteIn

router = APIRouter(prefix="/api/referrals", tags=["referrals"])


@router.get("/me")
def my_referrals(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_referrals.my_referrals(db, user)


@router.post("/simulate-invite", status_code=201)
def simulate_invite(
    body: SimulateInviteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_referrals.simulate_invite(db, user, body)
