"""积分路由（薄层）：余额/流水/即将过期。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import User

from app.domains.member import service_points

router = APIRouter(prefix="/api/points", tags=["points"])


@router.get("")
def my_points(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service_points.summary(db, user)


@router.get("/ledger")
def my_ledger(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_points.ledger(db, user, page, size)


@router.get("/expiring")
def my_expiring(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service_points.expiring(db, user)
