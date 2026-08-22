"""营销域后台路由 —— /api/admin/ops 下 discounts/popups/settings + /api/admin/promo 下礼品卡/折扣码明细（绝对路径，由 admin_ops shim 组装）"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_admin
from app.domains.promo import service
from app.domains.promo.schemas import (
    DiscountCreateIn, DiscountUpdateIn, GiftcardAdminCreateIn, PopupCreateIn,
    PopupUpdateIn, SettingIn,
)
from app.models import User

router = APIRouter(tags=["admin-ops"])


@router.get("/api/admin/ops/discounts")
def list_discounts(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.list_discounts(db, page, size, q)


@router.post("/api/admin/ops/discounts")
def create_discount(body: DiscountCreateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_discount(db, admin, body)


@router.put("/api/admin/ops/discounts/{discount_id}")
def update_discount(discount_id: int, body: DiscountUpdateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.update_discount(db, admin, discount_id, body)


@router.post("/api/admin/ops/discounts/{discount_id}/toggle")
def toggle_discount(discount_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.toggle_discount(db, admin, discount_id)


# ----- 礼品卡后台（/api/admin/promo） -----


@router.get("/api/admin/promo/giftcards")
def list_giftcards(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = None,
    status: int | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.list_giftcards(db, page, size, q, status)


@router.post("/api/admin/promo/giftcards")
def create_giftcard(body: GiftcardAdminCreateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_giftcard(db, admin, body)


@router.put("/api/admin/promo/giftcards/{gift_card_id}/freeze")
def freeze_giftcard(gift_card_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.freeze_giftcard(db, admin, gift_card_id)


@router.put("/api/admin/promo/giftcards/{gift_card_id}/unfreeze")
def unfreeze_giftcard(gift_card_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.unfreeze_giftcard(db, admin, gift_card_id)


@router.get("/api/admin/promo/giftcards/{gift_card_id}/ledger")
def giftcard_ledger(
    gift_card_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.giftcard_ledger(db, gift_card_id, page, size)


# ----- 折扣码使用明细/删除（/api/admin/promo） -----


@router.get("/api/admin/promo/discounts/{discount_id}/usages")
def discount_usages(
    discount_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.discount_usages(db, discount_id, page, size)


@router.delete("/api/admin/promo/discounts/{discount_id}")
def delete_discount(discount_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.delete_discount(db, admin, discount_id)


@router.get("/api/admin/ops/popups")
def list_popups(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_popups(db)


@router.post("/api/admin/ops/popups")
def create_popup(body: PopupCreateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.create_popup(db, admin, body)


@router.put("/api/admin/ops/popups/{popup_id}")
def update_popup(popup_id: int, body: PopupUpdateIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.update_popup(db, admin, popup_id, body)


@router.post("/api/admin/ops/popups/{popup_id}/toggle")
def toggle_popup(popup_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.toggle_popup(db, admin, popup_id)


@router.get("/api/admin/ops/settings")
def list_settings(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.list_settings(db)


@router.put("/api/admin/ops/settings")
def upsert_setting(body: SettingIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return service.upsert_setting(db, admin, body)


@router.get("/api/admin/ops/email-templates")
def list_email_templates(admin: User = Depends(require_admin)):
    """邮件模板运营预览：8 个自动化邮件 × 固定示例数据渲染（只读 emails.py）"""
    return service.email_template_previews()
