"""FastAPI 通用依赖：鉴权 / 购物车解析（契约层，路由只许使用不许重写）

鉴权三来源（优先级从高到低）：
  1. Authorization: Bearer <jwt>     —— API 客户端/测试套件
  2. Cookie gm_token                 —— 前台浏览器会话（HttpOnly）
  3. Cookie gm_admin_token           —— 后台浏览器会话（HttpOnly，独立短时效）
后台拆独立域名后，admin 站点只携带 gm_admin_token，与前台会话天然隔离。
"""

import secrets
from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.enums import UserRole
from app.core.permissions import permissions_of, role_has_perms
from app.core.security import decode_token
from app.models import Cart, User

STORE_COOKIE = "gm_token"
ADMIN_COOKIE = "gm_admin_token"


def _user_from_token(db: Session, token: str) -> Optional[User]:
    payload = decode_token(token)
    if not payload:
        return None
    # 会话 token 专用：显携带 purpose 但非 'session'（如密码重置 pwreset）一律拒收，
    # 防重置 JWT 被当登录会话用；历史 token 无 purpose 字段仍放行（签发过渡兼容）
    purpose = payload.get("purpose")
    if purpose is not None and purpose != "session":
        return None
    user = db.get(User, int(payload["sub"]))
    if not user or user.status != 1:
        return None
    return user


def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    gm_token: Optional[str] = Cookie(None),
    gm_admin_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if authorization and authorization.startswith("Bearer "):
        return _user_from_token(db, authorization[7:])
    if settings.cookie_auth:
        # 管理会话优先：前后台双 Cookie 并存时（运营先逛前台再登后台），
        # admin 身份是前台身份的超集，优先解析避免后台守卫误判为普通会员
        for cookie_val in (gm_admin_token, gm_token):
            if cookie_val:
                user = _user_from_token(db, cookie_val)
                if user:
                    return user
    return None


def get_admin_session_user(
    gm_admin_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> User:
    """后台专用会话解析：严格只认 gm_admin_token（与前台会话完全隔离）；
    无 Cookie / 解析失败一律 401（与 get_current_user 同构，未登录不再返回 None）。"""
    if not settings.cookie_auth or not gm_admin_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = _user_from_token(db, gm_admin_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def set_auth_cookie(response: Response, token: str, admin: bool = False) -> None:
    """登录成功后写会话 Cookie。

    - HttpOnly 防 XSS 窃取；MaxAge 与 token 签发时效对齐（前台 token_days 天 / 后台 admin_token_hours 小时）
    - 后台会话 SameSite=Strict 更严；前后台拆独立域名（GM_ALLOWED_ORIGINS 非空）时
      跨站请求 Strict/Lax 均不携带，需 SameSite=None —— None 缺 Secure 会被浏览器丢弃，故强制开
    """
    cross_site = bool(settings.allowed_origins.strip())
    if admin:
        max_age = settings.admin_token_hours * 3600
        samesite = "none" if cross_site else "strict"
    else:
        max_age = settings.token_days * 86400
        samesite = "lax"
    response.set_cookie(
        ADMIN_COOKIE if admin else STORE_COOKIE,
        token,
        httponly=True,
        samesite=samesite,
        secure=True if samesite == "none" else settings.cookie_secure,
        path="/",
        max_age=max_age,
    )


def clear_auth_cookie(response: Response, admin: bool = False) -> None:
    response.delete_cookie(ADMIN_COOKIE if admin else STORE_COOKIE, path="/")


def get_current_user(user: Optional[User] = Depends(get_current_user_optional)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_perm(*perms: str):
    """后台细粒度权限守卫工厂（角色 → 权限见 core/permissions.py 矩阵）：
    require_perm("trade:refund") —— 全部权限点命中才放行。
    拒绝语义：顾客/未知角色 → 403 "Admin only"；
    美甲师越面（非 chat）→ 403 "artist scope"；其余缺权限 → 403 "permission denied: <perms>"。"""
    def _guard(user: User = Depends(get_current_user)) -> User:
        if role_has_perms(user.role, perms):
            return user
        if user.role == int(UserRole.ARTIST):
            raise HTTPException(status_code=403, detail="artist scope")
        if not permissions_of(user.role):
            raise HTTPException(status_code=403, detail="Admin only")
        raise HTTPException(
            status_code=403, detail="permission denied: " + ", ".join(perms)
        )
    return _guard


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    """超管专属守卫：role == 9（管理员账号/支付凭据等高危面）"""
    if user.role != int(UserRole.SUPER):
        raise HTTPException(status_code=403, detail="superadmin required")
    return user


def _create_cart(db: Session, *, user_id: Optional[int]) -> tuple[Cart, str]:
    """建车：session token 一律服务端 secrets 生成，不信任请求头值
    （防伪造 X-Cart-Token 撞 carts.session_id 唯一索引导致 500）；
    极小概率撞唯一索引时换新 token 重试一次。"""
    for _ in range(2):
        token = secrets.token_hex(16)
        cart = Cart(user_id=user_id, session_id=token, items=[])
        db.add(cart)
        try:
            db.commit()
            return cart, token
        except IntegrityError:
            db.rollback()
    raise HTTPException(status_code=503, detail="cart token conflict, retry")


def resolve_cart(
    db: Session,
    user: Optional[User],
    token: Optional[str],
):
    """购物车解析：登录用户按 user_id，游客按 X-Cart-Token；没有则创建。
    返回 (cart, token)。登录后首次访问会以 token 车合并进用户车（cart 模块负责）。"""
    if user:
        cart = db.query(Cart).filter(Cart.user_id == user.id).first()
        if cart:
            return cart, token
        return _create_cart(db, user_id=user.id)

    if token:
        cart = db.query(Cart).filter(Cart.session_id == token, Cart.user_id.is_(None)).first()
        if cart:
            return cart, token
    return _create_cart(db, user_id=None)


def get_cart(
    x_cart_token: Optional[str] = Header(None, alias="X-Cart-Token"),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    cart, token = resolve_cart(db, user, x_cart_token)
    return cart, token
