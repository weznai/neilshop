"""FastAPI 通用依赖：鉴权 / 购物车解析（契约层，路由只许使用不许重写）

鉴权三来源（优先级从高到低）：
  1. Authorization: Bearer <jwt>     —— API 客户端/测试套件
  2. Cookie gm_token                 —— 前台浏览器会话（HttpOnly）
  3. Cookie gm_admin_token           —— 后台浏览器会话（HttpOnly，独立短时效）
后台拆独立域名后，admin 站点只携带 gm_admin_token，与前台会话天然隔离。
"""

import uuid
from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.security import decode_token
from app.models import Cart, User

STORE_COOKIE = "gm_token"
ADMIN_COOKIE = "gm_admin_token"


def _user_from_token(db: Session, token: str) -> Optional[User]:
    payload = decode_token(token)
    if not payload:
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
        for cookie_val in (gm_token, gm_admin_token):
            if cookie_val:
                user = _user_from_token(db, cookie_val)
                if user:
                    return user
    return None


def set_auth_cookie(response: Response, token: str, admin: bool = False) -> None:
    """登录成功后写会话 Cookie（HttpOnly 防 XSS 窃取；后台会话 SameSite=Strict 更严）。"""
    response.set_cookie(
        ADMIN_COOKIE if admin else STORE_COOKIE,
        token,
        httponly=True,
        samesite="strict" if admin else "lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_auth_cookie(response: Response, admin: bool = False) -> None:
    response.delete_cookie(ADMIN_COOKIE if admin else STORE_COOKIE, path="/")


def get_current_user(user: Optional[User] = Depends(get_current_user_optional)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """后台接口守卫：role >= 2（运营/仓库/超管）"""
    if user.role < 2:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


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
        token = token or uuid.uuid4().hex
        cart = Cart(user_id=user.id, session_id=token, items=[])
        db.add(cart)
        db.commit()
        return cart, token

    if token:
        cart = db.query(Cart).filter(Cart.session_id == token, Cart.user_id.is_(None)).first()
        if cart:
            return cart, token
    token = uuid.uuid4().hex
    cart = Cart(session_id=token, items=[])
    db.add(cart)
    db.commit()
    return cart, token


def get_cart(
    x_cart_token: Optional[str] = Header(None, alias="X-Cart-Token"),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    cart, token = resolve_cart(db, user, x_cart_token)
    return cart, token
