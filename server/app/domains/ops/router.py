"""运营域后台路由 —— /api/admin/ops 下 dashboard/members/logs + 评价/UGC 审核扩展
（绝对路径，由 admin_ops shim 组装；本 router 先于 content/support 注册，故同名
reviews 列表路由在此扩展 rating/product_id 过滤并以本域实现命中）"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.domains.ops import service
from app.domains.ops.schemas import PointsAdjustIn, ReviewBulkIn, RiskIn, UgcBulkIn
from app.models import User

router = APIRouter(tags=["admin-ops"])


@router.get("/api/admin/ops/dashboard")
def dashboard(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.dashboard(db)


@router.get("/api/admin/ops/members")
def list_members(
    q: str | None = Query(None),
    tier: int | None = Query(None),
    risk: int | None = Query(None, description="按 risk_flag 过滤（0正常 1关注 2黑名单）"),
    sort: str | None = Query(None, description="points/-points/total_spent/-total_spent，非法值走默认排序"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.list_members(db, q, tier, page, size, sort, risk)


@router.get("/api/admin/ops/members/{user_id}")
def member_detail(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.member_detail(db, user_id)


@router.post("/api/admin/ops/members/{user_id}/risk")
def member_risk(user_id: int, body: RiskIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.member_risk(db, admin, user_id, body)


@router.get("/api/admin/ops/admins")
def list_admins(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_admins(db)


@router.post("/api/admin/ops/members/{user_id}/points")
def member_points_adjust(
    user_id: int, body: PointsAdjustIn,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service.member_points_adjust(db, admin, user_id, body)


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


# ---------- 评价/UGC 审核扩展（bulk/unapprove；列表路由扩展 rating/product_id） ----------

@router.get("/api/admin/ops/reviews")
def admin_reviews(
    status: int | None = Query(None),
    rating: int | None = Query(None, ge=1, le=5),
    product_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # 覆盖 content 域同名路由（本 router 先注册）：响应结构一致，仅增加过滤维度
    return service.admin_reviews(db, status, rating, product_id, page, size)


@router.post("/api/admin/ops/reviews/bulk")
def bulk_reviews(
    body: ReviewBulkIn,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service.bulk_reviews(db, admin, body)


@router.post("/api/admin/ops/reviews/{review_id}/unapprove")
def unapprove_review(
    review_id: int,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service.unapprove_review(db, admin, review_id)


@router.post("/api/admin/ops/ugc/bulk")
def bulk_ugc(
    body: UgcBulkIn,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service.bulk_ugc(db, admin, body)


@router.post("/api/admin/ops/ugc/{ugc_id}/unapprove")
def unapprove_ugc(
    ugc_id: int,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return service.unapprove_ugc(db, admin, ugc_id)
