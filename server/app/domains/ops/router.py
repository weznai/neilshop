"""运营域后台路由 —— /api/admin/ops 下 dashboard/members/logs + 评价/UGC 审核扩展
+ 运营队列（弃购/对账/GDPR 数据请求/Newsletter）+ 管理员账号管理（仅超管）
（绝对路径，由 admin_ops shim 组装；本 router 先于 content/support 注册，故同名
reviews 列表路由在此扩展 rating/product_id 过滤并以本域实现命中）"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_perm, require_superadmin
from app.domains.ops import service
from app.domains.ops.schemas import (
    AdminCreateIn, AdminUpdateIn, PointsAdjustIn, ReviewBulkIn, RiskIn, UgcBulkIn,
)
from app.models import User

router = APIRouter(tags=["admin-ops"])


@router.get("/api/admin/ops/dashboard")
def dashboard(admin: User = Depends(require_perm("dashboard:read")), db: Session = Depends(get_db)):
    return service.dashboard(db)


@router.get("/api/admin/ops/members")
def list_members(
    q: str | None = Query(None),
    tier: int | None = Query(None),
    risk: int | None = Query(None, description="按 risk_flag 过滤（0正常 1关注 2黑名单）"),
    sort: str | None = Query(None, description="points/-points/total_spent/-total_spent，非法值走默认排序"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_perm("member:read")),
    db: Session = Depends(get_db),
):
    return service.list_members(db, q, tier, page, size, sort, risk)


@router.get("/api/admin/ops/members/{user_id}")
def member_detail(user_id: int, admin: User = Depends(require_perm("member:read")), db: Session = Depends(get_db)):
    return service.member_detail(db, user_id)


@router.post("/api/admin/ops/members/{user_id}/risk")
def member_risk(user_id: int, body: RiskIn, admin: User = Depends(require_perm("member:manage")), db: Session = Depends(get_db)):
    return service.member_risk(db, admin, user_id, body)


@router.get("/api/admin/ops/admins")
def list_admins(admin: User = Depends(require_perm("admin:read")), db: Session = Depends(get_db)):
    return service.list_admins(db)


@router.post("/api/admin/ops/members/{user_id}/points")
def member_points_adjust(
    user_id: int, body: PointsAdjustIn,
    admin: User = Depends(require_perm("member:manage")), db: Session = Depends(get_db),
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
    admin: User = Depends(require_perm("log:read")),
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
    admin: User = Depends(require_perm("content:manage")),
    db: Session = Depends(get_db),
):
    # 覆盖 content 域同名路由（本 router 先注册）：响应结构一致，仅增加过滤维度
    return service.admin_reviews(db, status, rating, product_id, page, size)


@router.post("/api/admin/ops/reviews/bulk")
def bulk_reviews(
    body: ReviewBulkIn,
    admin: User = Depends(require_perm("content:manage")), db: Session = Depends(get_db),
):
    return service.bulk_reviews(db, admin, body)


@router.post("/api/admin/ops/reviews/{review_id}/unapprove")
def unapprove_review(
    review_id: int,
    admin: User = Depends(require_perm("content:manage")), db: Session = Depends(get_db),
):
    return service.unapprove_review(db, admin, review_id)


@router.post("/api/admin/ops/ugc/bulk")
def bulk_ugc(
    body: UgcBulkIn,
    admin: User = Depends(require_perm("content:manage")), db: Session = Depends(get_db),
):
    return service.bulk_ugc(db, admin, body)


@router.post("/api/admin/ops/ugc/{ugc_id}/unapprove")
def unapprove_ugc(
    ugc_id: int,
    admin: User = Depends(require_perm("content:manage")), db: Session = Depends(get_db),
):
    return service.unapprove_ugc(db, admin, ugc_id)


# ---------- 运营队列：弃购 / 对账历史 / GDPR 数据请求 / Newsletter ----------

@router.get("/api/admin/ops/abandoned-carts")
def abandoned_carts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_perm("ops:queue")),
    db: Session = Depends(get_db),
):
    """弃购队列：口径对齐 worker（有商品 + 最后活跃超 1 小时未下单），按最后活跃倒序"""
    return service.abandoned_carts(db, page, size)


@router.get("/api/admin/ops/reconciliations")
def reconciliations(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    admin: User = Depends(require_perm("ops:queue")),
    db: Session = Depends(get_db),
):
    return service.reconciliations(db, page, size, date_from, date_to)


@router.post("/api/admin/ops/reconciliations/{rec_id}/resolve")
def resolve_reconciliation(
    rec_id: int,
    admin: User = Depends(require_perm("ops:queue")), db: Session = Depends(get_db),
):
    """差异人工核销：置 status=2 已处理（已处理 → 409）"""
    return service.resolve_reconciliation(db, admin, rec_id)


@router.get("/api/admin/ops/data-requests")
def data_requests(
    type: int | None = Query(None, ge=1, le=2, description="1导出 2删除"),
    status: int | None = Query(None, ge=0, le=2),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_perm("ops:queue")),
    db: Session = Depends(get_db),
):
    return service.data_requests(db, page, size, type, status)


@router.post("/api/admin/ops/data-requests/{req_id}/reject")
def reject_data_request(
    req_id: int,
    admin: User = Depends(require_perm("ops:queue")), db: Session = Depends(get_db),
):
    return service.reject_data_request(db, admin, req_id)


@router.post("/api/admin/ops/data-requests/{req_id}/execute")
def execute_data_request(
    req_id: int,
    admin: User = Depends(require_perm("ops:queue")), db: Session = Depends(get_db),
):
    """立即执行（删除类与 worker 共用 anonymize_user）；仅受理中(0)可执行"""
    return service.execute_data_request(db, admin, req_id)


@router.get("/api/admin/ops/newsletters")
def newsletters(
    q: str | None = Query(None, description="email 模糊搜索"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_perm("ops:queue")),
    db: Session = Depends(get_db),
):
    return service.newsletters(db, page, size, q)


# ---------- 管理员账号管理（仅超管） ----------

@router.post("/api/admin/ops/admins")
def create_admin(
    body: AdminCreateIn,
    admin: User = Depends(require_superadmin), db: Session = Depends(get_db),
):
    return service.create_admin(db, admin, body)


@router.put("/api/admin/ops/admins/{admin_id}")
def update_admin(
    admin_id: int,
    body: AdminUpdateIn,
    admin: User = Depends(require_superadmin), db: Session = Depends(get_db),
):
    return service.update_admin(db, admin, admin_id, body)


@router.get("/api/admin/ops/admins/{admin_id}")
def admin_detail(
    admin_id: int,
    admin: User = Depends(require_superadmin), db: Session = Depends(get_db),
):
    return service.admin_detail(db, admin_id)
