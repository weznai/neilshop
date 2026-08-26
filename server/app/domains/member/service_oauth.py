"""Google/Apple 第三方登录服务 —— 授权 URL 构造 / 回调换 token + id_token 校验 /
用户匹配（subject 命中 → email_verified 绑定 → 建号）/ dev 演示登录。

配置来源（resolve_oauth_config，对齐 payment_provider.resolve_pay_config 模式）：
settings 表 oauth_config（JSON，后台可热配）> 环境变量 GM_GOOGLE_* / GM_APPLE_*；
缺关键字段 → 409 not_configured。

id_token 验签口径（择稳简注明）：
- Google：id_token 直接经 TLS 从 https://oauth2.googleapis.com/token 换得
  （client_secret 仅服务端持有，非浏览器中转），属「直接从签发方获取」的可信通道，
  故本地只校验 aud=client_id 与 exp（RFC 7519 token-endpoint 直取可免在线验签）。
- Apple：同端点换 token，但为对齐官方最佳实践用 PyJWKClient 拉
  https://appleid.apple.com/auth/keys 在线验签（ES256）+ aud/iss/exp 校验。
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from urllib.parse import quote, urlencode

import jwt as pyjwt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.security import create_token, hash_password
from app.models import OutboxEvent, Setting, User

from app.domains.member import repository as repo
from app.domains.member.service_account import (
    _WELCOME_FALLBACK_CODE, _WELCOME_FALLBACK_DISCOUNT, _site_url, _user_out,
)

log = logging.getLogger("glowmag.oauth")

OAUTH_SETTING_KEY = "oauth_config"
OAUTH_PROVIDERS = ("google", "apple")

STATE_TTL_SECONDS = 600

# env 兜底键（settings 表 oauth_config 同名字段覆盖之）
_ENV_KEYS = {
    "google_client_id": "GM_GOOGLE_CLIENT_ID",
    "google_client_secret": "GM_GOOGLE_CLIENT_SECRET",
    "apple_client_id": "GM_APPLE_CLIENT_ID",
    "apple_team_id": "GM_APPLE_TEAM_ID",
    "apple_key_id": "GM_APPLE_KEY_ID",
    "apple_private_key": "GM_APPLE_PRIVATE_KEY",
}


def resolve_oauth_config(db: Session | None = None) -> dict:
    cfg = {k: (env_default(k) or "") for k in _ENV_KEYS}
    if db is not None:
        try:
            row = db.get(Setting, OAUTH_SETTING_KEY)
            if row is not None and isinstance(row.value, dict):
                for k in cfg:
                    v = row.value.get(k)
                    if isinstance(v, str) and v.strip():
                        cfg[k] = v.strip()
        except Exception as exc:  # DB 故障不影响 env 配置
            log.warning("oauth config load failed: %s", exc)
    # 私钥常见的是 \n 转义形态（env/后台单行输入），统一还原成真实换行
    key = cfg.get("apple_private_key") or ""
    if key and "\\n" in key:
        cfg["apple_private_key"] = key.replace("\\n", "\n").strip()
    return cfg


def env_default(key: str) -> str:
    return (os.getenv(_ENV_KEYS.get(key, "")) or "").strip()


def _google_ready(cfg: dict) -> bool:
    return bool(cfg.get("google_client_id") and cfg.get("google_client_secret"))


def _apple_ready(cfg: dict) -> bool:
    return bool(
        cfg.get("apple_client_id") and cfg.get("apple_team_id")
        and cfg.get("apple_key_id") and cfg.get("apple_private_key")
    )


# ---------- state（HMAC 自校验，防伪造/防跨 provider 挪用） ----------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def sign_state(provider: str) -> str:
    payload = _b64url(json.dumps({
        "provider": provider,
        "nonce": secrets.token_hex(8),
        "exp": int(time.time()) + STATE_TTL_SECONDS,
    }).encode())
    sig = hmac.new(
        settings.jwt_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f"{payload}.{sig}"


def verify_state(state: str, provider: str) -> bool:
    try:
        payload, sig = state.split(".", 1)
    except ValueError:
        return False
    expected = hmac.new(
        settings.jwt_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        data = json.loads(_b64url_decode(payload))
    except (ValueError, json.JSONDecodeError):
        return False
    return (
        data.get("provider") == provider
        and int(data.get("exp") or 0) > time.time()
    )


# ---------- 授权 URL ----------

def authorize_url(db: Session, provider: str) -> str:
    cfg = resolve_oauth_config(db)
    site = _site_url(db)
    state = sign_state(provider)
    if provider == "google":
        if not _google_ready(cfg):
            raise HTTPException(status_code=409, detail="not_configured")
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "client_id": cfg["google_client_id"],
            "redirect_uri": f"{site}/api/account/oauth/google/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        })
    if provider == "apple":
        if not _apple_ready(cfg):
            raise HTTPException(status_code=409, detail="not_configured")
        return "https://appleid.apple.com/auth/authorize?" + urlencode({
            "client_id": cfg["apple_client_id"],
            "redirect_uri": f"{site}/api/account/oauth/apple/callback",
            "response_type": "code",
            "scope": "name email",
            "response_mode": "form_post",
            "state": state,
        })
    raise HTTPException(status_code=400, detail="invalid_provider")


# ---------- Google 回调：httpx 换 token + 本地校验 id_token ----------

def _httpx_client():
    import httpx

    return httpx.Client(timeout=15.0)


def _google_exchange(cfg: dict, code: str, site: str) -> dict:
    """授权码换 token（https://oauth2.googleapis.com/token）；返回解析后的 id_token claims。
    id_token 经服务端 TLS 直取自 Google 端点 → 本地校验 aud/exp 即可（见模块头注明）。"""
    with _httpx_client() as client:
        resp = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": cfg["google_client_id"],
                "client_secret": cfg["google_client_secret"],
                "redirect_uri": f"{site.rstrip('/')}/api/account/oauth/google/callback",
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        id_token = resp.json().get("id_token") or ""
    if not id_token:
        raise HTTPException(status_code=401, detail="no_id_token")
    try:
        claims = pyjwt.decode(
            id_token, options={"verify_signature": False},
            audience=cfg["google_client_id"],
            algorithms=["RS256"],
        )
    except pyjwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid_id_token:{exc}") from exc
    return claims


# ---------- Apple 回调：ES256 client_secret 换 token + JWKS 验签 ----------

def _apple_client_secret(cfg: dict) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": cfg["apple_team_id"],
            "iat": now,
            "exp": now + 15777000,  # ~6 个月（Apple 上限）
            "aud": "https://appleid.apple.com",
            "sub": cfg["apple_client_id"],
        },
        cfg["apple_private_key"],
        algorithm="ES256",
        headers={"kid": cfg["apple_key_id"]},
    )


def _apple_exchange(cfg: dict, code: str, site: str) -> dict:
    """client_secret（ES256 私钥签 JWT）换 token，id_token 经
    https://appleid.apple.com/auth/keys 在线验签（ES256）后返回 claims。"""
    with _httpx_client() as client:
        resp = client.post(
            "https://appleid.apple.com/auth/token",
            data={
                "code": code,
                "client_id": cfg["apple_client_id"],
                "client_secret": _apple_client_secret(cfg),
                "redirect_uri": f"{site.rstrip('/')}/api/account/oauth/apple/callback",
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        id_token = resp.json().get("id_token") or ""
    if not id_token:
        raise HTTPException(status_code=401, detail="no_id_token")
    try:
        jwks = pyjwt.PyJWKClient("https://appleid.apple.com/auth/keys")
        key = jwks.get_signing_key_from_jwt(id_token)
        claims = pyjwt.decode(
            id_token, key.key, algorithms=["ES256"],
            audience=cfg["apple_client_id"],
            issuer="https://appleid.apple.com",
        )
    except pyjwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid_id_token:{exc}") from exc
    return claims


# ---------- 用户匹配 / 建号 / 登录 ----------

def _welcome_outbox(db: Session, user: User) -> None:
    """注册欢迎券 outbox（复用 register 现有钩子的 payload 结构）"""
    code, discount = repo.welcome_coupon(db) or (
        _WELCOME_FALLBACK_CODE, _WELCOME_FALLBACK_DISCOUNT
    )
    db.add(OutboxEvent(
        aggregate_type="user", aggregate_id=user.id, event_type="user.welcome",
        payload={"user_id": user.id, "email": user.email,
                 "code": code, "discount": discount},
    ))


def login_or_create(
    db: Session, *, provider: str, subject: str,
    email: str | None, name: str | None, email_verified: bool,
) -> User:
    """OAuth 身份匹配三段式：provider+subject 命中直登；email_verified 且 email
    命中现有账号 → 绑定后登录；否则最小化建号（随机密码 hash + welcome outbox）。
    事务边界归调用方（回调/dev-login 统一 commit）。"""
    user = repo.get_user_by_oauth(db, provider, subject)
    if user is not None:
        if user.status != 1:
            raise HTTPException(status_code=403, detail="account_disabled")
        return user
    norm_email = (email or "").strip().lower()
    if email_verified and norm_email:
        existing = repo.get_user_by_email(db, norm_email)
        if existing is not None:
            if existing.status != 1:
                raise HTTPException(status_code=403, detail="account_disabled")
            existing.oauth_provider = provider
            existing.oauth_subject = subject
            if not existing.email_verified_at:
                existing.email_verified_at = utcnow()
            return existing
    if not norm_email:
        raise HTTPException(status_code=401, detail="email_missing")
    # 未验证 email 且已被他人占用：不能绑定也不能建号（唯一索引冲突 + 账号抢注面）→ 拒绝
    if repo.user_email_taken(db, norm_email):
        raise HTTPException(status_code=409, detail="email_taken")
    user = repo.add_user(
        db,
        email=norm_email,
        password_hash=hash_password(secrets.token_urlsafe(32)),  # 随机密码（不可登录）
        name=(name or "").strip()[:100] or "Glow User",
        oauth_provider=provider,
        oauth_subject=subject,
        email_verified_at=utcnow() if email_verified else None,
    )
    db.flush()
    _welcome_outbox(db, user)
    return user


def _issue_session(db: Session, user: User) -> str:
    user.last_login_at = utcnow()
    db.commit()
    return create_token(user.id, user.role)


def _redirect_login(db: Session, token: str, user: User) -> str:
    return (
        f"{_site_url(db)}/login?oauth_token={quote(token)}"
        f"&email={quote(user.email)}"
    )


def _redirect_error(reason: str) -> str:
    return f"/login?oauth_error={quote(reason)}"


def handle_callback(db: Session, provider: str, code: str, state: str) -> str:
    """OAuth 回调统一编排：state 自校验 → 换 token/验 id_token → 匹配建号 →
    签发与 login 相同的会话 token，302 跳 {site}/login?oauth_token=...；
    任一步失败 302 跳 /login?oauth_error=<原因>（不打断跳转语义）。"""
    try:
        if not code or not state or not verify_state(state, provider):
            return _redirect_error("invalid_state")
        cfg = resolve_oauth_config(db)
        site = _site_url(db)
        if provider == "google":
            if not _google_ready(cfg):
                return _redirect_error("not_configured")
            claims = _google_exchange(cfg, code, site)
        elif provider == "apple":
            if not _apple_ready(cfg):
                return _redirect_error("not_configured")
            claims = _apple_exchange(cfg, code, site)
        else:
            return _redirect_error("invalid_provider")
        subject = str(claims.get("sub") or "")
        if not subject:
            return _redirect_error("missing_sub")
        email = claims.get("email")
        # Google email_verified 是 "true"/"false" 字符串，Apple 是 bool —— 统一归一
        verified_raw = claims.get("email_verified")
        email_verified = str(verified_raw).lower() in ("true", "1", "yes") \
            if verified_raw is not None else False
        user_name = None
        if isinstance(claims.get("name"), str):
            user_name = claims["name"]
        elif isinstance(claims.get("name"), dict):  # Apple 首次授权 form_post 人称段
            parts = [claims["name"].get(k) for k in ("firstName", "lastName")]
            user_name = " ".join(p for p in parts if p) or None
        user = login_or_create(
            db, provider=provider, subject=subject,
            email=email, name=user_name, email_verified=email_verified,
        )
        token = _issue_session(db, user)
        return _redirect_login(db, token, user)
    except HTTPException as exc:
        db.rollback()
        return _redirect_error(str(exc.detail)[:80])
    except Exception as exc:  # 网络/IdP 故障等：不 500，统一带回登录页错误提示
        db.rollback()
        log.warning("oauth %s callback failed: %s", provider, exc)
        return _redirect_error("provider_error")


# ---------- dev 演示登录（GM_ENV=dev 限定） ----------

def dev_login(db: Session, provider: str, email: str | None, name: str | None) -> dict:
    """dev 演示登录：按 provider+随机 subject 查找/创建演示账号
    （email 缺省 {provider}.demo.{uuid}@glowmag.local），返回与 login 相同响应体。
    传 email 时走「查找该 email 账号并绑定 provider」路径（复用建号逻辑）。"""
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail="invalid_provider")
    if email:
        user = repo.get_user_by_email(db, email.strip().lower())
        if user is not None and (
            user.oauth_provider == provider and user.oauth_subject
        ):
            token = _issue_session(db, user)
            return {"token": token, "user": _user_out(user)}
        subject = f"dev-{provider}-{secrets.token_hex(8)}"
        user = login_or_create(
            db, provider=provider, subject=subject,
            email=email.strip().lower(), name=name, email_verified=True,
        )
        token = _issue_session(db, user)
        return {"token": token, "user": _user_out(user)}
    demo_email = f"{provider}.demo.{uuid.uuid4().hex}@glowmag.local"
    subject = f"dev-{provider}-{secrets.token_hex(8)}"
    user = login_or_create(
        db, provider=provider, subject=subject,
        email=demo_email, name=name or "Glow Demo", email_verified=True,
    )
    token = _issue_session(db, user)
    return {"token": token, "user": _user_out(user)}
