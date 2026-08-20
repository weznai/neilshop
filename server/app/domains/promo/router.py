"""营销域用户侧路由 —— /api/promo/*（HTTP 编排，业务在 service）"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.promo import service
from app.domains.promo.schemas import GiftcardIn, GiftcardPurchaseIn, ValidateIn

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
def purchase_giftcard(body: GiftcardPurchaseIn, db: Session = Depends(get_db)):
    return service.purchase_giftcard(db, body)
