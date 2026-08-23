"""安全纵深自测（智能体 B）—— 限流覆盖（新 RATE_RULES 真 429）/ Cookie 属性 / 注入面静态回归。
（GM_DB=sqlite:///test_s_ext.sqlite 独立库；GM_COOKIE_SECURE=1 断言 Secure 标记）"""

import os
import re
import sys

import jwt as pyjwt

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_s_ext.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_SECURE"] = "1"
os.environ["GM_TOKEN_DAYS"] = "7"
os.environ["GM_ADMIN_TOKEN_HOURS"] = "12"
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi import Response
from fastapi.testclient import TestClient

from app.core import deps, observability as obs
from app.core.config import settings
from app.core.db import SessionLocal, init_db
from app.core.security import hash_password
from app.main import app
from app.models import User

PASSED = 0
FAILED = []


def check(name, cond, info=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok  {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}  {info}")


def build_fixtures():
    init_db()
    db = SessionLocal()
    try:
        alice = User(email="alice@glowmail.dev",
                     password_hash=hash_password("alicepass123"), name="Alice", role=1)
        root = User(email="root@glowmail.dev",
                    password_hash=hash_password("rootpass1234"), name="Root", role=9)
        db.add_all([alice, root])
        db.commit()
        ids = {"alice": alice.id, "root": root.id}
        db.close()
        return ids
    except Exception:
        db.close()
        raise


IDS = build_fixtures()
client = TestClient(app)


def cookie_attrs(raw: str) -> tuple[str, dict[str, str]]:
    parts = [p.strip() for p in raw.split(";")]
    name = parts[0].split("=", 1)[0]
    attrs: dict[str, str] = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        attrs[k.lower()] = v.lower()
    return name, attrs


def find_cookie(res, cname: str) -> dict[str, str]:
    headers = res.headers
    raws = headers.getlist("set-cookie") if hasattr(headers, "getlist") \
        else headers.get_list("set-cookie")
    for raw in raws:
        name, attrs = cookie_attrs(raw)
        if name == cname:
            return attrs
    return {}


def drain(path: str, limit: int, body: dict) -> None:
    obs._RATE_BUCKETS.clear()
    statuses = [client.post(path, json=body).status_code for _ in range(limit)]
    r = client.post(path, json=body)
    check(f"{path} 前 {limit} 次放行、第 {limit + 1} 次 429",
          all(s != 429 for s in statuses) and r.status_code == 429,
          (statuses[-3:], r.status_code))
    check(f"{path} 429 带 Retry-After 头 + detail=rate_limited",
          r.status_code == 429 and int(r.headers.get("retry-after", "0")) >= 1
          and r.json().get("detail") == "rate_limited",
          (r.headers.get("retry-after"), r.text[:80]))


print("== RATE_RULES：规则表完整性 ==")
_expected = {
    "/api/account/admin/login": 20,
    "/api/account/login": 60,
    "/api/account/register": 30,
    "/api/account/password-reset": 20,
    "/api/account/newsletter": 30,
    "/api/account/consent": 10,
    "/api/promo/giftcard/purchase": 20,
    "/api/promo/giftcard": 20,
    "/api/promo/popup": 60,
    "/api/promo/validate": 60,
    "/api/checkout/place": 10,
    "/api/payments/mock-pay": 120,
    "/api/payments/webhook": 120,
    "/api/payments/create-intent": 30,
    "/api/cart/items-batch": 30,
    "/api/returns": 20,
    "/api/exchanges": 20,
    "/api/orders/track": 30,
    "/api/orders/": 30,
    "/api/catalog/stock-notify": 10,
    "/api/support/tickets": 30,
    "/api/chat/": 60,
}
_rules = dict(obs.RATE_RULES)
check("22 条规则齐全且阈值符合保守基线", _rules == _expected, _rules)
check("全局规则不含 /api/ai（域内 30/min 自治，避免双重 429）",
      not any(p.startswith("/api/ai") for p, _ in obs.RATE_RULES))
check("admin/login 规则排在宽前缀 login 之前",
      [p for p, _ in obs.RATE_RULES].index("/api/account/admin/login")
      < [p for p, _ in obs.RATE_RULES].index("/api/account/login"))

print("== RATE_RULES：前缀匹配语义（不误伤近邻路径）==")
check("/api/account/admin/logout 不被 admin/login 规则误伤",
      obs._check_rate_limit("u1", "/api/account/admin/logout") == (None, 0))
check("/api/account/logout 不被 login 规则误伤",
      obs._check_rate_limit("u2", "/api/account/logout") == (None, 0))
check("/api/promo/giftcard（查询）命中专属 giftcard 规则而非 purchase 规则",
      obs._check_rate_limit("u3", "/api/promo/giftcard")[0] == "/api/promo/giftcard")
check("/api/promo/giftcard/purchase 先命中 purchase 规则（更具体前缀在前）",
      obs._check_rate_limit("u3b", "/api/promo/giftcard/purchase")[0]
      == "/api/promo/giftcard/purchase")
check("/api/orders/track 全路径规则不覆盖 /api/orders 列表端点",
      obs._check_rate_limit("u3c", "/api/orders") == (None, 0))
check("/api/orders/{order_no} 详情命中 /api/orders/ 前缀规则（防撞库枚举泄露地址）",
      obs._check_rate_limit("u3d", "/api/orders/NS123")[0] == "/api/orders/"
      and obs._check_rate_limit("u3e", "/api/orders/NS456/cancel")[0] == "/api/orders/")
check("/api/account/password-reset 覆盖 /request 与 /confirm 两子路径",
      obs._check_rate_limit("u4", "/api/account/password-reset/request")[0]
      == "/api/account/password-reset"
      and obs._check_rate_limit("u5", "/api/account/password-reset/confirm")[0]
      == "/api/account/password-reset")

print("== 限流：新规则逐条真 429 ==")
drain("/api/account/admin/login", 20,
      {"email": "ghost@glowmail.dev", "password": "whatever123"})
drain("/api/promo/giftcard/purchase", 20,
      {"amount_cents": 999, "purchaser_email": "x@glowmail.dev"})
drain("/api/account/newsletter", 30,
      {"email": "flood@glowmail.dev", "source": "footer"})
drain("/api/promo/validate", 60,
      {"code": "GUESS123", "subtotal_cents": 1000})
obs._RATE_BUCKETS.clear()

print("== 后台会话探测：未登录 401（而非 500）==")
r = client.get("/api/account/admin/me")
check("admin/me 无 Cookie → 401 Not authenticated",
      r.status_code == 401 and r.json().get("detail") == "Not authenticated", r.text[:120])

print("== Cookie：前台 gm_token 属性 ==")
r = client.post("/api/account/login",
                json={"email": "alice@glowmail.dev", "password": "alicepass123"})
check("alice 登录 200", r.status_code == 200, r.text[:120])
attrs = find_cookie(r, "gm_token")
check("gm_token HttpOnly", "httponly" in attrs, attrs)
check("gm_token SameSite=lax（同源够用）", attrs.get("samesite") == "lax", attrs)
check("gm_token Secure（GM_COOKIE_SECURE=1）", "secure" in attrs, attrs)
check("gm_token Path=/", attrs.get("path") == "/", attrs)
check("gm_token Max-Age=604800 与 token_days=7 对齐",
      attrs.get("max-age") == "604800", attrs)
_iat = pyjwt.decode(r.json()["token"], settings.jwt_secret, algorithms=["HS256"])
check("JWT 时效与 Max-Age 一致（exp-iat=604800）",
      _iat["exp"] - _iat["iat"] == 604800, _iat["exp"] - _iat["iat"])

print("== Cookie：登出清 Cookie ==")
r = client.post("/api/account/logout")
attrs = find_cookie(r, "gm_token")
check("logout 下发 gm_token 删除指令（Max-Age=0）",
      r.status_code == 200 and attrs.get("max-age") == "0", attrs)

print("== Cookie：后台 gm_admin_token 属性 ==")
r = client.post("/api/account/admin/login",
                json={"email": "root@glowmail.dev", "password": "rootpass1234"})
check("root 后台登录 200", r.status_code == 200, r.text[:120])
attrs = find_cookie(r, "gm_admin_token")
check("gm_admin_token HttpOnly", "httponly" in attrs, attrs)
check("gm_admin_token SameSite=strict（同源部署）", attrs.get("samesite") == "strict", attrs)
check("gm_admin_token Secure", "secure" in attrs, attrs)
check("gm_admin_token Max-Age=43200 与 admin_token_hours=12 对齐",
      attrs.get("max-age") == "43200", attrs)
_adm = pyjwt.decode(r.json()["token"], settings.jwt_secret, algorithms=["HS256"])
check("后台 JWT 时效与 Max-Age 一致（exp-iat=43200）",
      _adm["exp"] - _adm["iat"] == 43200, _adm["exp"] - _adm["iat"])

print("== Cookie：跨域部署（GM_ALLOWED_ORIGINS 非空）后台改 SameSite=None+Secure ==")
_orig_origins = settings.allowed_origins
settings.allowed_origins = "https://admin.glow.example"
try:
    resp = Response()
    deps.set_auth_cookie(resp, "tok-admin", admin=True)
    _a = find_cookie(resp, "gm_admin_token")
    check("跨域后台 gm_admin_token SameSite=none", _a.get("samesite") == "none", _a)
    check("SameSite=None 强制 Secure（缺 Secure 会被浏览器丢弃）", "secure" in _a, _a)
    check("跨域后台 Max-Age 仍对齐 43200", _a.get("max-age") == "43200", _a)
    resp2 = Response()
    deps.set_auth_cookie(resp2, "tok-user")
    _u = find_cookie(resp2, "gm_token")
    check("前台 gm_token 跨域配置下仍 lax（前台与 API 同源）",
          _u.get("samesite") == "lax" and "secure" in _u, _u)
finally:
    settings.allowed_origins = _orig_origins

print("== 注入面：静态扫描（f-string/format 拼 SQL 回归哨兵）==")
_patterns = [
    re.compile(r"execute\(f[\"']"),
    re.compile(r"f[\"'](?:SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE),
    re.compile(r"[\"'](?:SELECT|INSERT|UPDATE|DELETE)\b[^\"']*[\"']\.format\(", re.IGNORECASE),
]
_hits = []
for _dir, _, _files in os.walk(os.path.join(_ROOT, "app")):
    for _f in _files:
        if not _f.endswith(".py"):
            continue
        _fp = os.path.join(_dir, _f)
        with open(_fp, encoding="utf-8") as _fh:
            for _ln, _line in enumerate(_fh, 1):
                if any(p.search(_line) for p in _patterns):
                    _hits.append(f"{_fp}:{_ln}: {_line.strip()[:100]}")
check("全 app 无 f-string/format SQL 拼接（text() 常量均参数化）", not _hits, _hits[:5])

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
