"""结算路由（薄路由）—— preview 试算 / place 下单；定价/用分/礼品卡业务在 service_checkout。"""

from typing import Optional

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_cart, get_current_user_optional
from app.domains.trade import service_checkout
from app.domains.trade.schemas import PlaceRequest, PreviewRequest
from app.models import User
from app.services.pricing import shipping_methods

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


@router.get("/shipping-methods")
def get_shipping_methods(country: str = "US", db: Session = Depends(get_db)):
    """公开：可用配送方式（运费模板聚合，checkout 页展示）+ 免邮门槛（settings 回退）
    + 捆绑折扣率（pricing 同 key 同默认值，前端进度条/文案消费）。"""
    from app.services.pricing import DEFAULT_FREE_SHIPPING_THRESHOLD, _setting
    threshold = int(_setting(db, "free_shipping_threshold", DEFAULT_FREE_SHIPPING_THRESHOLD))
    bundle_discounts = {
        "bundle_2_off": int(_setting(db, "bundle_2_off", 15)),
        "bundle_3_off": int(_setting(db, "bundle_3_off", 20)),
    }
    return {
        "items": shipping_methods(db, country),
        "free_shipping_threshold": threshold,
        "bundle_discounts": bundle_discounts,
    }


@router.post("/preview")
def preview(
    body: Optional[PreviewRequest] = None,
    pack=Depends(get_cart),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    response: Response = None,
):
    cart, token = pack
    if token:
        response.headers["X-Cart-Token"] = token
    result = service_checkout.preview(db, cart, body, user)
    result["cart_token"] = token
    return result


@router.post("/place", status_code=201)
def place(
    body: PlaceRequest,
    pack=Depends(get_cart),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    response: Response = None,
):
    cart, token = pack
    if token:
        response.headers["X-Cart-Token"] = token
    return service_checkout.place(db, cart, body, user)
