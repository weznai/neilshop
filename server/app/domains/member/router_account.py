"""账户路由（薄层）：注册/登录/资料/地址簿/心愿单/订阅/隐私/退订/改密/
邮箱修改（双步验证）/Google·Apple 第三方登录。

鉴权双通道：响应体保留 token（API 客户端/测试），同时写 HttpOnly Cookie（浏览器）。
后台专用 /admin/login 签发独立 gm_admin_token Cookie（短时效 + SameSite=Strict），
为前后台拆独立域名铺路 —— 拆分后 admin 站点只携带 gm_admin_token。
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import (
    clear_auth_cookie, get_admin_session_user, get_current_user,
    get_current_user_optional, set_auth_cookie,
)
from app.core.security import create_token
from app.models import User

from app.domains.member import service_account, service_oauth
from app.domains.member.schemas import (
    AddressIn, ConsentIn, EmailChangeConfirmIn, EmailChangeIn,
    EmailPreferencesUpdateIn, LoginIn, NewsletterIn, OAuthDevLoginIn,
    PasswordChangeIn, PasswordResetConfirmIn, PasswordResetRequestIn,
    ProfileUpdateIn, RegisterIn, UnsubscribeIn,
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
    """后台专用登录：后台角色（客服/运营/仓库/美甲师/超管）才放行，签发短时效 gm_admin_token（SameSite=Strict）。"""
    data = service_account.login(db, body, admin=True)
    set_auth_cookie(response, data["token"], admin=True)
    return data


@router.get("/admin/me")
def admin_me(user: User = Depends(get_admin_session_user)):
    """后台会话探测：严格只认 gm_admin_token（与前台 gm_token 隔离，双 Cookie 并存不串台）；
    附实时权限集（前端路由/菜单/按钮权限判定）。"""
    return service_account.admin_profile(user)


@router.post("/admin/logout")
def admin_logout(response: Response, user: User = Depends(get_current_user_optional)):
    clear_auth_cookie(response, admin=True)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service_account.profile_with_delete_request(db, user)


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


@router.get("/wishlist/has")
def wishlist_has(
    product_id: int = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """心愿单是否已含某商品（详情页心形状态轻查询，登录态低频不扩限流）"""
    return service_account.wishlist_has(db, user, product_id)


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


@router.put("/password")
def change_password(
    body: PasswordChangeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service_account.change_password(db, user, body)


# ---------- 邮箱修改（双步验证） ----------

@router.post("/email-change")
def email_change_request(
    body: EmailChangeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """第 1 步：密码验证 + 6 位数字码发往新邮箱（dev 环境响应附 dev_code）。"""
    return service_account.email_change_request(db, user, body)


@router.post("/email-change/confirm")
def email_change_confirm(
    body: EmailChangeConfirmIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """第 2 步：验证码确认 → 更新邮箱；token 基于 user id 签发，无需重签，
    但回写 Cookie 让浏览器会话同步为最新用户资料快照。"""
    data = service_account.email_change_confirm(db, user, body)
    set_auth_cookie(response, create_token(user.id, user.role))
    return data


# ---------- Google / Apple 第三方登录 ----------

@router.get("/oauth/{provider}/authorize")
def oauth_authorize(provider: str, db: Session = Depends(get_db)):
    """构造授权跳转 URL；dev（GM_ENV=dev）不跳真实 IdP，返回 {url:"", dev_mock:true}
    （前端走 /oauth/dev-login 演示流）。未配置凭据 → 409 not_configured。"""
    if provider not in service_oauth.OAUTH_PROVIDERS:
        raise HTTPException(status_code=404, detail="provider not found")
    if settings.env == "dev":
        return {"url": "", "dev_mock": True}
    return {"url": service_oauth.authorize_url(db, provider)}


@router.get("/oauth/google/callback")
def oauth_google_callback(
    code: str = "", state: str = "", db: Session = Depends(get_db),
):
    """Google 回调（query）：换 token + 校验 id_token → 匹配/建号 → 302 前端登录页
    （成功带 oauth_token+email，失败带 oauth_error）。"""
    return RedirectResponse(
        service_oauth.handle_callback(db, "google", code, state), status_code=302,
    )


@router.post("/oauth/apple/callback")
def oauth_apple_callback(
    code: str = Form(""), state: str = Form(""),
    db: Session = Depends(get_db),
):
    """Apple 回调（response_mode=form_post）：ES256 client_secret 换 token +
    JWKS 验 id_token → 匹配/建号 → 302 前端登录页。"""
    return RedirectResponse(
        service_oauth.handle_callback(db, "apple", code, state), status_code=302,
    )


@router.post("/oauth/dev-login")
def oauth_dev_login(body: OAuthDevLoginIn, db: Session = Depends(get_db)):
    """dev 演示登录（GM_ENV=dev 限定，其余环境 404）：查找/创建演示账号，
    返回与 /login 相同的 {token, user}。"""
    if settings.env != "dev":
        raise HTTPException(status_code=404, detail="Not Found")
    return service_oauth.dev_login(db, body.provider, body.email, body.name)


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
