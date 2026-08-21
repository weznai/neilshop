"""退货 RMA 用户侧路由（薄路由）—— 申请/列表/详情；业务在 service_returns。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.domains.trade import service_returns
from app.models import User
from app.schemas.orders import RmaCreateRequest

router = APIRouter(prefix="/api/returns", tags=["returns"])


@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_rma(body: RmaCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service_returns.create_rma(db, user, body)


@router.get("")
@router.get("/")
def list_rmas(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service_returns.list_rmas(db, user)


@router.get("/{rma_no}")
def rma_detail(rma_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service_returns.rma_detail(db, user, rma_no)


@router.post("/{rma_no}/cancel")
def cancel_rma(rma_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service_returns.cancel_rma(db, user, rma_no)
