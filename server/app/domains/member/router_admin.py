"""会员域后台路由 —— /api/admin/member 下订阅盒管理（列表分页 + 代操作暂停/恢复/取消）。

代操作完全复用 service_subscriptions 的用户侧状态机（错误码一致），仅补管理端审计。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.models import User
from app.domains.member import service_subscriptions
from app.domains.member.schemas import (
    SubscriptionCancelIn, SubscriptionPauseIn,
)

router = APIRouter(prefix="/api/admin/member", tags=["admin-member"])


@router.get("/subscriptions")
def admin_subscriptions(
    status: int | None = Query(None, description="按订阅状态过滤（1生效中 2已暂停 5已取消）"),
    q: str | None = Query(None, description="按用户 email 模糊搜索"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_subscriptions.admin_list(db, status, page, size, q)


@router.post("/subscriptions/{sub_id}/pause")
def admin_pause_subscription(
    sub_id: int,
    body: SubscriptionPauseIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_subscriptions.admin_pause(db, admin, sub_id, body)


@router.post("/subscriptions/{sub_id}/resume")
def admin_resume_subscription(
    sub_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_subscriptions.admin_resume(db, admin, sub_id)


@router.post("/subscriptions/{sub_id}/cancel")
def admin_cancel_subscription(
    sub_id: int,
    body: SubscriptionCancelIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service_subscriptions.admin_cancel(db, admin, sub_id, body)
