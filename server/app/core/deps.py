"""FastAPI 通用依赖：鉴权 / 购物车解析（契约层，路由只许使用不许重写）

鉴权来源（前后台完全隔离，互不兜底）：
  1. Authorization: Bearer <jwt>      —— API 客户端/测试套件（前后台端点通吃）
  2. Cookie gm_token                  —— 前台浏览器会话（HttpOnly，path=/）
  3. Cookie gm_admin_token            —— 后台浏览器会话（HttpOnly，独立短时效，
                                         path=/api/admin 圈住后台 API 子树）
同域部署时 Cookie path 隔离保证双 Cookie 物理不并存（前台请求不带 admin Cookie、
后台请求不带会员 Cookie）；后台拆独立域名（admin 域反代 /api 到本服务）后
host-only Cookie 按域天然隔离，本层无需感知。
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
# 后台 Cookie 的 path：圈住后台 API 子树（路由已归一到 /api/admin/**），
# 浏览器只对后台请求携带 —— 与前台 gm_token(path=/) 物理隔离，杜绝串号
ADMIN_COOKIE_PATH = "/api/admin"


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


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    return authorization[7:] if authorization and authorization.startswith("Bearer ") else None


def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    gm_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """前台身份解析：仅认 Bearer 与 gm_token —— 绝不读 gm_admin_token。

    前后台会话物理隔离（Cookie path + 拆域后按域），无需也无法互相兜底；
    即使浏览器残留旧 path=/ 的 admin Cookie，前台也只按游客/会员处理。
    """
    bearer = _bearer_token(authorization)
    if bearer:
        return _user_from_token(db, bearer)
    if settings.cookie_auth and gm_token:
        return _user_from_token(db, gm_token)
    return None


def get_admin_user_optional(
    authorization: Optional[str] = Header(None),
    gm_admin_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """后台身份解析（require_perm/require_superadmin 专用）：仅认 Bearer 与 gm_admin_token。"""
    bearer = _bearer_token(authorization)
    if bearer:
        return _user_from_token(db, bearer)
    if settings.cookie_auth and gm_admin_token:
        return _user_from_token(db, gm_admin_token)
    return None


def get_admin_user(user: Optional[User] = Depends(get_admin_user_optional)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def get_admin_session_user(
    gm_admin_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
) -> User:
    """后台会话探测（/api/admin/session/me）：严格只认 gm_admin_token Cookie
    （不接受 Bearer，与浏览器后台会话语义完全一致）；无 Cookie / 解析失败一律 401。"""
    if not settings.cookie_auth or not gm_admin_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = _user_from_token(db, gm_admin_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def set_auth_cookie(response: Response, token: str, admin: bool = False) -> None:
    """登录成功后写会话 Cookie。

    - HttpOnly 防 XSS 窃取；MaxAge 与 token 签发时效对齐（前台 token_days 天 / 后台 admin_token_hours 小时）
    - 后台会话 path=/api/admin（圈住后台 API 子树，与前台 Cookie 物理隔离不并存），
      同时清掉历史 path=/ 的同名旧 Cookie（升级过渡期残留）；SameSite=Strict 更严；
      前后台拆独立域名（GM_ALLOWED_ORIGINS 非空）时跨站请求 Strict/Lax 均不携带，
      需 SameSite=None —— None 缺 Secure 会被浏览器丢弃，故强制开
    """
    cross_site = bool(settings.allowed_origins.strip())
    if admin:
        max_age = settings.admin_token_hours * 3600
        samesite = "none" if cross_site else "strict"
        path = ADMIN_COOKIE_PATH
        # 历史版本 admin Cookie 为 path=/：登录时显式作废，避免双值并存
        response.delete_cookie(ADMIN_COOKIE, path="/")
    else:
        max_age = settings.token_days * 86400
        # 前台拆域部署（前台与 API 不同域）时 Lax 跨站不携带 → 会话失效，
        # 对齐 admin 的 SameSite=None + 强制 Secure 写法；同源部署保持 lax
        samesite = "none" if cross_site else "lax"
        path = "/"
    response.set_cookie(
        ADMIN_COOKIE if admin else STORE_COOKIE,
        token,
        httponly=True,
        samesite=samesite,
        secure=True if samesite == "none" else settings.cookie_secure,
        path=path,
        max_age=max_age,
    )


def clear_auth_cookie(response: Response, admin: bool = False) -> None:
    if admin:
        # 新旧两个 path 都清（升级过渡期浏览器可能同时持有）
        response.delete_cookie(ADMIN_COOKIE, path=ADMIN_COOKIE_PATH)
        response.delete_cookie(ADMIN_COOKIE, path="/")
    else:
        response.delete_cookie(STORE_COOKIE, path="/")


def get_current_user(user: Optional[User] = Depends(get_current_user_optional)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_perm(*perms: str):
    """后台细粒度权限守卫工厂（角色 → 权限见 core/permissions.py 矩阵）：
    require_perm("trade:refund") —— 全部权限点命中才放行。
    拒绝语义：顾客/未知角色 → 403 "Admin only"；
    美甲师越面（非 chat）→ 403 "artist scope"；其余缺权限 → 403 "permission denied: <perms>"。"""
    def _guard(user: User = Depends(get_admin_user)) -> User:
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


def require_superadmin(user: User = Depends(get_admin_user)) -> User:
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
