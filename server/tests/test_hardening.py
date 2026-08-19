"""智能体 B 自测 —— 安全响应头（nosniff/DENY/Referrer/Permissions/CSP）+ 静态缓存头
（GM_DB=sqlite:///test_h.sqlite 独立库；BigInteger 垫片同 test_payments.py 写法）"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_h.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.responses import Response
from fastapi.testclient import TestClient

from app.core import observability as obs
from app.main import app

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


PERM_EXPECT = "camera=(), microphone=(), geolocation=()"
CSP_EXPECT = (
    "default-src 'self'; img-src 'self' https: data:; "
    "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' https:; "
    "connect-src 'self' https:; font-src 'self' https: data:"
)
FIVE = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": PERM_EXPECT,
    "content-security-policy": CSP_EXPECT,
}


def five_ok(r):
    bad = {k: r.headers.get(k) for k, v in FIVE.items() if r.headers.get(k) != v}
    return not bad, bad


cap = None
try:
    with TestClient(app) as client:
        r = client.get("/api/health")
        check("/api/health 200 JSON", r.status_code == 200
              and r.headers.get("content-type", "").startswith("application/json"), r.status_code)
        for k, v in FIVE.items():
            ok, bad = five_ok(r)
            check(f"/api/health {k} 值正确", r.headers.get(k) == v,
                  {k: r.headers.get(k)})
        ok, bad = five_ok(r)
        check("/api/health X-Request-Id 与五类安全头共存",
              bool(r.headers.get("x-request-id")) and ok, (r.headers.get("x-request-id"), bad))

        r = client.get("/")
        ok, bad = five_ok(r)
        check("静态页 / 五类安全头齐全且值正确", r.status_code == 200 and ok, bad)
        csp = r.headers.get("content-security-policy", "")
        check("静态页 CSP 含 unsafe-inline（内联脚本/样式可用）",
              "'unsafe-inline'" in csp and "script-src 'self' 'unsafe-inline'" in csp, csp)
        check("静态页 Cache-Control no-cache（HTML 不长缓存）",
              r.headers.get("cache-control") == "no-cache", r.headers.get("cache-control"))

        r = client.get("/assets/app.js")
        ok, bad = five_ok(r)
        check("静态资产 /assets/app.js 200 + 五类安全头", r.status_code == 200 and ok, bad)
        check("静态资产 Cache-Control public max-age 长缓存",
              r.headers.get("cache-control") == "public, max-age=604800",
              r.headers.get("cache-control"))

        r = client.get("/api/catalog/products/no-such-slug")
        ok, bad = five_ok(r)
        check("API 404 JSON 响应同带头", r.status_code == 404
              and r.headers.get("content-type", "").startswith("application/json") and ok, bad)

        r = client.get("/api/no-such-endpoint")
        ok, bad = five_ok(r)
        check("静态兜底 404 页同带头", r.status_code == 404 and ok, bad)

        r = client.get("/metrics")
        ok, bad = five_ok(r)
        check("/metrics 响应同带头", r.status_code == 200 and ok, bad)

        obs.RATE_RULES[:] = [("/api/account/login", 1)]
        obs._RATE_BUCKETS.clear()
        client.post("/api/account/login", json={"email": "x@glow.test", "password": "x"})
        r429 = client.post("/api/account/login", json={"email": "x@glow.test", "password": "x"})
        ok, bad = five_ok(r429)
        check("429 限流响应同带头（Retry-After 不受影响）",
              r429.status_code == 429 and ok
              and int(r429.headers.get("retry-after", "0")) >= 1, bad)

        resp = Response(content="ok")
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Content-Security-Policy"] = "default-src 'none'"
        obs._apply_security_headers("/", "GET", resp)
        check("已有同名头不被覆盖（XFO/CSP 保留原值，其余补齐）",
              resp.headers.get("x-frame-options") == "SAMEORIGIN"
              and resp.headers.get("content-security-policy") == "default-src 'none'"
              and resp.headers.get("x-content-type-options") == "nosniff"
              and resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin",
              dict(resp.headers))
finally:
    obs.RATE_RULES[:] = [
        ("/api/account/login", 60),
        ("/api/account/register", 30),
        ("/api/account/password-reset", 20),
        ("/api/payments/mock-pay", 120),
        ("/api/support/tickets", 30),
    ]

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
