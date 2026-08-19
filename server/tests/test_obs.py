"""智能体 C 自测 —— 可观测性中间件 / X-Request-Id / 指标 / 限流
（GM_DB=sqlite:///test_o.sqlite 独立库；BigInteger 垫片同 test_payments.py 写法）"""

import logging
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_o.sqlite").replace("\\", "/")
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


class _Cap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


try:
    with TestClient(app) as client:
        # ===== X-Request-Id =====
        rid_in = "trace-abc.123_XYZ"
        r = client.get("/api/health", headers={"X-Request-Id": rid_in})
        check("自带 rid 原样回写", r.status_code == 200
              and r.headers.get("x-request-id") == rid_in, r.headers.get("x-request-id"))

        r = client.get("/api/health", headers={"X-Request-Id": "a" * 40 + " !@#$"})
        check("rid 非法字符过滤 + 32 截断", r.headers.get("x-request-id") == "a" * 32,
              r.headers.get("x-request-id"))

        r = client.get("/api/health")
        rid_gen = r.headers.get("x-request-id", "")
        check("无 rid 头 → 生成 12 hex", re.fullmatch(r"[0-9a-f]{12}", rid_gen) is not None, rid_gen)

        # ===== 访问日志 =====
        cap = _Cap()
        obs.logger.addHandler(cap)
        r = client.get("/api/health")
        msgs = [rec.getMessage() for rec in cap.records]
        check("访问日志单行结构化 rid/method/path/status/ms",
              any(re.fullmatch(
                  r"rid=[0-9a-zA-Z._-]+ method=GET path=/api/health status=200 ms=\d+", m)
                  for m in msgs), msgs[-3:])

        # ===== 指标：health 计数 =====
        snap1 = obs.get_metrics_snapshot()
        c1 = snap1["requests"].get(("GET", "/api/health", 200), 0)
        client.get("/api/health")
        snap2 = obs.get_metrics_snapshot()
        c2 = snap2["requests"].get(("GET", "/api/health", 200), 0)
        check("/api/health 200 且计数 +1", r.status_code == 200 and c2 - c1 == 1, (c1, c2))

        # ===== 动态路径折叠 =====
        for pid in ("999", "888", "123"):
            client.get(f"/api/catalog/products/{pid}")
        snap = obs.get_metrics_snapshot()
        fold_keys = {k: v for k, v in snap["requests"].items()
                     if k[1].startswith("/api/catalog/products")}
        check("数字段折叠为 {id} 不分裂",
              set(fold_keys) == {("GET", "/api/catalog/products/{id}", 404)}
              and fold_keys.get(("GET", "/api/catalog/products/{id}", 404)) == 3,
              fold_keys)

        # ===== 静态路径归 static 组 =====
        r = client.get("/")
        snap = obs.get_metrics_snapshot()
        check("非 /api 路径归 static 组", r.status_code == 200
              and any(k[1] == "static" for k in snap["requests"]),
              [k for k in snap["requests"] if k[1] == "static"])

        # ===== /metrics 文本解析 =====
        r = client.get("/metrics")
        ct = r.headers.get("content-type", "")
        body = r.text
        check("/metrics 200 + Content-Type text version=0.0.4",
              r.status_code == 200 and ct.startswith("text/plain")
              and "version=0.0.4" in ct, ct)
        check("HELP/TYPE 行存在",
              "# TYPE glowmag_http_requests_total counter" in body
              and "# TYPE glowmag_http_request_duration_ms summary" in body, body[:200])
        check("counter 行可解析且 ≥1",
              re.search(r'glowmag_http_requests_total\{method="GET",path="/api/health",status="200"\} \d+', body) is not None,
              body)
        check("quantile 0.5/0.95 与 _count 行存在",
              re.search(r'glowmag_http_request_duration_ms\{path="/api/health",quantile="0\.5"\} [\d.]+', body) is not None
              and re.search(r'glowmag_http_request_duration_ms\{path="/api/health",quantile="0\.95"\} [\d.]+', body) is not None
              and re.search(r'glowmag_http_request_duration_ms_count\{path="/api/health"\} \d+', body) is not None,
              body)
        snap = obs.get_metrics_snapshot()
        check("/metrics 自身不计入指标", not any(k[1] == "/metrics" for k in snap["requests"]),
              [k for k in snap["requests"] if k[1] == "/metrics"])

        # ===== 限流：monkeypatch 阈值 3 =====
        obs.RATE_RULES[:] = [("/api/account/login", 3)]
        obs._RATE_BUCKETS.clear()
        cap.records.clear()
        statuses = [client.post("/api/account/login",
                                json={"email": "nobody@glowmail.com", "password": "x"}).status_code
                    for _ in range(3)]
        r4 = client.post("/api/account/login",
                         json={"email": "nobody@glowmail.com", "password": "x"})
        check("前 3 次不限（正常放行）第 4 次 429",
              all(s != 429 for s in statuses) and r4.status_code == 429,
              (statuses, r4.status_code))
        check("429 响应体 detail/retry_after + Retry-After 头",
              r4.json().get("detail") == "rate_limited"
              and isinstance(r4.json().get("retry_after"), int) and r4.json()["retry_after"] >= 1
              and int(r4.headers.get("retry-after", "0")) >= 1,
              (r4.text, r4.headers.get("retry-after")))
        check("限流命中 warning 日志",
              any(rec.levelno == logging.WARNING and "rate_limited" in rec.getMessage()
                  for rec in cap.records), [rec.getMessage() for rec in cap.records][-3:])
        check("429 访问日志 status=429",
              any(re.fullmatch(r"rid=\S+ method=POST path=/api/account/login status=429 ms=\d+",
                               rec.getMessage()) for rec in cap.records),
              [rec.getMessage() for rec in cap.records][-3:])

        r = client.get("/api/health")
        rr = client.post("/api/account/register",
                         json={"email": "obs@glow.test", "password": "x12345678", "name": "O"})
        check("限流不影响其它路径", r.status_code == 200 and rr.status_code != 429,
              (r.status_code, rr.status_code))
finally:
    obs.logger.removeHandler(cap) if "cap" in dir() else None
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
