"""订阅月盒路由（薄层）：我的订阅/创建/暂停/恢复/取消/跳过。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import User

from app.domains.member import service_subscriptions
from app.domains.member.schemas import (
    SubscriptionCancelIn, SubscriptionCreateIn, SubscriptionPauseIn, SubscriptionSkipIn,
)

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


@router.get("/me")
def my_subscriptions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_subscriptions.my_subscriptions(db, user)


@router.post("", status_code=201)
def create_subscription(
    body: SubscriptionCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_subscriptions.create(db, user, body)


@router.post("/{sub_id}/pause")
def pause_subscription(
    sub_id: int,
    body: SubscriptionPauseIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_subscriptions.pause(db, user, sub_id, body)


@router.post("/{sub_id}/resume")
def resume_subscription(
    sub_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_subscriptions.resume(db, user, sub_id)


@router.post("/{sub_id}/cancel")
def cancel_subscription(
    sub_id: int,
    body: SubscriptionCancelIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_subscriptions.cancel(db, user, sub_id, body)


@router.post("/{sub_id}/skip")
def skip_subscription(
    sub_id: int,
    body: SubscriptionSkipIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_subscriptions.skip(db, user, sub_id, body)
