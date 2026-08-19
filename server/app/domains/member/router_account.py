"""账户路由（薄层）：注册/登录/资料/地址簿/心愿单/订阅/隐私/退订/改密。

鉴权双通道：响应体保留 token（API 客户端/测试），同时写 HttpOnly Cookie（浏览器）。
后台专用 /admin/login 签发独立 gm_admin_token Cookie（短时效 + SameSite=Strict），
为前后台拆独立域名铺路 —— 拆分后 admin 站点只携带 gm_admin_token。
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import (
    clear_auth_cookie, get_admin_session_user, get_current_user,
    get_current_user_optional, set_auth_cookie,
)
from app.models import User

from app.domains.member import service_account
from app.domains.member.schemas import (
    AddressIn, ConsentIn, EmailPreferencesUpdateIn, LoginIn, NewsletterIn,
    PasswordResetConfirmIn, PasswordResetRequestIn, ProfileUpdateIn, RegisterIn,
    UnsubscribeIn,
)

router = APIRouter(prefix="/api/account", tags=["account"])


@router.post("/register", status_code=201)
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    data = service_account.register(db, body)
    set_auth_cookie(response, data["token"])
    return data


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    data = service_account.login(db, body)
    set_auth_cookie(response, data["token"])
    return data


@router.post("/logout")
def logout(response: Response, user: User = Depends(get_current_user_optional)):
    """登出：清前台会话 Cookie（幂等，未登录也 200）。"""
    clear_auth_cookie(response)
    return {"ok": True}


@router.post("/admin/login")
def admin_login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    """后台专用登录：role>=2 才放行，签发短时效 gm_admin_token（SameSite=Strict）。"""
    data = service_account.login(db, body, admin=True)
    set_auth_cookie(response, data["token"], admin=True)
    return data


@router.get("/admin/me")
def admin_me(user: User = Depends(get_admin_session_user)):
    """后台会话探测：严格只认 gm_admin_token（与前台 gm_token 隔离，双 Cookie 并存不串台）。"""
    return service_account.profile(user)


@router.post("/admin/logout")
def admin_logout(response: Response, user: User = Depends(get_current_user_optional)):
    clear_auth_cookie(response, admin=True)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return service_account.profile(user)


@router.put("/me")
def update_me(
    body: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.update_profile(db, user, body)


@router.get("/addresses")
def list_addresses(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.list_addresses(db, user)


@router.post("/addresses", status_code=201)
def create_address(
    body: AddressIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.create_address(db, user, body)


@router.put("/addresses/{address_id}")
def update_address(
    address_id: int,
    body: AddressIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.update_address(db, user, address_id, body)


@router.delete("/addresses/{address_id}")
def delete_address(
    address_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.delete_address(db, user, address_id)


@router.get("/wishlist")
def wishlist(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.wishlist(db, user)


@router.post("/wishlist/{product_id}")
def add_wishlist(
    product_id: int,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data, created = service_account.add_to_wishlist(db, user, product_id)
    if created:
        response.status_code = 201
    return data


@router.delete("/wishlist/{product_id}")
def remove_wishlist(
    product_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.remove_from_wishlist(db, user, product_id)


@router.post("/newsletter")
def newsletter(
    body: NewsletterIn,
    user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return service_account.newsletter(db, user, body)


@router.post("/consent", status_code=201)
def consent(
    body: ConsentIn,
    user=Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return service_account.consent(db, user, body)


@router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeIn, db: Session = Depends(get_db),
                user=Depends(get_current_user_optional)):
    return service_account.unsubscribe(db, user, body)


@router.post("/password-reset/request")
def password_reset_request(body: PasswordResetRequestIn, db: Session = Depends(get_db)):
    return service_account.password_reset_request(db, body)


@router.post("/password-reset/confirm")
def password_reset_confirm(body: PasswordResetConfirmIn, db: Session = Depends(get_db)):
    return service_account.password_reset_confirm(db, body)


@router.get("/export")
def export_data(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.export_my_data(db, user)


@router.post("/delete-request", status_code=202)
def create_delete_request(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.request_delete(db, user)


@router.delete("/delete-request")
def cancel_delete_request(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.cancel_delete(db, user)


@router.get("/email-preferences")
def get_email_preferences(
    email: str | None = None,
    token: str | None = None,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """偏好中心读取：登录 → 自身邮箱；或 ?email=&token=（us_ HMAC）。"""
    return service_account.get_email_preferences(db, user, email, token)


@router.put("/email-preferences")
def update_email_preferences(
    body: EmailPreferencesUpdateIn,
    email: str | None = None,
    token: str | None = None,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """偏好中心部分更新：任一开关为 1 → 复订（清 unsubscribed_at）；全 0 → 等价全退。"""
    return service_account.update_email_preferences(db, user, body, email, token)
