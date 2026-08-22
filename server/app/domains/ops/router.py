"""运营域后台路由 —— /api/admin/ops 下 dashboard/members/logs（绝对路径，由 admin_ops shim 组装）"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.domains.ops import service
from app.domains.ops.schemas import RiskIn
from app.models import User

router = APIRouter(tags=["admin-ops"])


@router.get("/api/admin/ops/dashboard")
def dashboard(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.dashboard(db)


@router.get("/api/admin/ops/members")
def list_members(
    q: str | None = Query(None),
    tier: int | None = Query(None),
    sort: str | None = Query(None, description="points/-points/total_spent/-total_spent，非法值走默认排序"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.list_members(db, q, tier, page, size, sort)


@router.get("/api/admin/ops/members/{user_id}")
def member_detail(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.member_detail(db, user_id)


@router.post("/api/admin/ops/members/{user_id}/risk")
def member_risk(user_id: int, body: RiskIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.member_risk(db, admin, user_id, body)


@router.get("/api/admin/ops/logs")
def admin_logs(
    entity: str | None = Query(None),
    action: str | None = Query(None),
    admin_id: int | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.admin_logs(
        db, entity, page, size, action=action, admin_id=admin_id, start=start, end=end
    )
