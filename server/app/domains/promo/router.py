"""营销域用户侧路由 —— /api/promo/*（HTTP 编排，业务在 service）"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, get_current_user_optional
from app.domains.promo import service
from app.domains.promo.schemas import GiftcardIn, GiftcardPurchaseIn, ValidateIn
from app.models import User

router = APIRouter(prefix="/api/promo", tags=["promo"])


@router.post("/validate")
def validate_discount_code(body: ValidateIn, db: Session = Depends(get_db)):
    return service.validate_code(db, body)


@router.post("/giftcard")
def check_giftcard(body: GiftcardIn, db: Session = Depends(get_db)):
    return service.check_giftcard(db, body)


@router.get("/popup")
def get_popup(scene: str = Query(...), db: Session = Depends(get_db)):
    popup = service.active_popup(db, scene)
    if popup is None:
        return Response(status_code=204)
    return service.popup_payload(popup)


# 公开上报（无鉴权）：曝光/转化由前台投放页直接调用，频控由前端负责；
# 不存在/已停用 404，前端静默忽略即可
@router.post("/popup/{popup_id}/shown")
def popup_shown(popup_id: int, db: Session = Depends(get_db)):
    return service.track_popup_shown(db, popup_id)


@router.post("/popup/{popup_id}/convert")
def popup_convert(popup_id: int, db: Session = Depends(get_db)):
    return service.track_popup_convert(db, popup_id)


@router.post("/giftcard/purchase", status_code=201)
def purchase_giftcard(
    body: GiftcardPurchaseIn,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    # 登录用户购卡：user_id 关联订单（账户订单列表可见）+ 黑名单风控
    return service.purchase_giftcard(db, body, user)


# ===== 券包（领取制优惠券） =====


@router.get("/coupons")
def list_coupons(
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """领券中心（公开）：可领券列表；登录时回填 claimed 标记"""
    return service.list_coupons(db, user)


@router.get("/coupons/mine")
def my_coupons(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """我的券包：三态（0可用 1已用 2已过期惰性判定），领取时间倒序"""
    return service.my_coupons(db, user)


@router.post("/coupons/{coupon_id}/claim")
def claim_coupon(
    coupon_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.claim_coupon(db, user, coupon_id)
