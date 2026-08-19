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


@router.post("/giftcard/purchase", status_code=201)
def purchase_giftcard(body: GiftcardPurchaseIn, db: Session = Depends(get_db)):
    return service.purchase_giftcard(db, body)
