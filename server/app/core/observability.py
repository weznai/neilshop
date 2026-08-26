"""轻量可观测性：统一 X-Request-Id / 结构化访问日志 / 进程内 Prometheus 文本指标 / 应用级滑动窗限流。"""

import json
import logging
import math
import os
import threading
import time
import uuid
from collections import deque
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger("glowmag.access")
logger.setLevel(logging.INFO)

_RID_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._"
)
_RID_VAR: ContextVar[str] = ContextVar("glowmag_request_id", default="")

_LOCK = threading.Lock()
_COUNTERS: dict[tuple[str, str, int], int] = {}
_SAMPLES: deque[tuple[str, float]] = deque(maxlen=10000)

RATE_WINDOW = 60.0
# 前缀匹配（startswith）且先命中先生效：更具体的前缀必须排在更宽的前缀之前；
# /api/ai 前缀刻意不加（ai/router.py 域内 30/min 滑动窗自治，避免双重 429）；
# /api/chat/ 前缀 60/min：公开会话创建/发消息/轮询（前台 4s 轮询 ≈15/min，留发送余量）；
# /api/orders/track 用全路径形式，避免 /api/orders 宽前缀覆盖订单列表端点；
# /api/orders/ 前缀（排在 track 之后）覆盖 /api/orders/{order_no} 详情与子动作，
# 防订单号+邮箱撞库枚举泄露收货地址（track 同款阈值）
RATE_RULES: list[tuple[str, int]] = [
    ("/api/account/admin/login", 20),
    ("/api/account/login", 60),
    ("/api/account/register", 30),
    ("/api/account/password-reset", 20),
    # OAuth 登录链低频（authorize/dev-login 更具体前缀在前，callback 走宽前缀兜底）
    ("/api/account/oauth/authorize", 20),
    ("/api/account/oauth/dev-login", 10),
    ("/api/account/oauth/", 20),
    ("/api/account/newsletter", 30),
    ("/api/account/consent", 10),
    # GDPR 导出全量扫描订单/工单/流水，重操作低频 → 3/min
    ("/api/account/export", 3),
    ("/api/promo/giftcard/purchase", 20),
    ("/api/promo/giftcard", 20),
    ("/api/promo/popup", 60),
    ("/api/promo/validate", 60),
    ("/api/checkout/place", 10),
    ("/api/payments/mock-pay", 120),
    ("/api/payments/webhook", 120),
    ("/api/payments/create-intent", 30),
    # items-batch 批量加购更敏感（30/min），须排在 /api/cart 宽前缀之前；
    # /api/cart 前缀兜底全部车端点（含 GET /api/cart 与 /api/cart/items 子路径）——
    # 未鉴权请求也会触发建车写库，60/min per IP 防无限建车刷库
    ("/api/cart/items-batch", 30),
    ("/api/cart", 60),
    ("/api/returns", 20),
    ("/api/exchanges", 20),
    ("/api/orders/track", 30),
    ("/api/orders/", 30),
    ("/api/catalog/stock-notify", 10),
    ("/api/catalog/search", 30),
    ("/api/support/tickets", 30),
    ("/api/chat/", 60),
    # /api/content/ 前缀兜底全部内容端点（faqs/articles/reviews/ugc，读写同桶）
    ("/api/content/", 30),
]

# 测试/压测可调：GM_RATE_RULES='{"/api/checkout/place": 120}' 覆盖已有规则的阈值
# （仅允许调整既有前缀的 limit，不新增/删除规则；缺省完全按上表生效）
_override_raw = os.getenv("GM_RATE_RULES", "").strip()
if _override_raw:
    try:
        _override = {str(k): int(v) for k, v in json.loads(_override_raw).items()}
        RATE_RULES = [(p, _override.get(p, n)) for p, n in RATE_RULES]
    except (ValueError, TypeError):
        logger.warning("GM_RATE_RULES is not a valid {prefix: limit} JSON, ignored")
_RATE_BUCKETS: dict[tuple[str, str], deque[float]] = {}


def get_request_id() -> str:
    return _RID_VAR.get()


def _sanitize_rid(value: str) -> str:
    return "".join(c for c in value if c in _RID_CHARS)[:32]


def path_group(path: str) -> str:
    if path == "/api/health":
        return "/api/health"
    if path in ("/docs", "/redoc", "/openapi.json"):
        return "openapi"
    if not path.startswith("/api/"):
        return "static"
    segments = [
        seg if not any(c.isdigit() for c in seg) else "{id}"
        for seg in path.rstrip("/").split("/")
    ]
    return "/".join(segments)


def _record(method: str, group: str, status: int, ms: float) -> None:
    with _LOCK:
        _COUNTERS[(method, group, status)] = _COUNTERS.get((method, group, status), 0) + 1
        _SAMPLES.append((group, ms))


def get_metrics_snapshot() -> dict:
    with _LOCK:
        return {"requests": dict(_COUNTERS), "durations": list(_SAMPLES)}


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    idx = min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))
    return values[idx]


def render_metrics() -> str:
    with _LOCK:
        counters = dict(_COUNTERS)
        samples = list(_SAMPLES)
    lines = [
        "# HELP glowmag_http_requests_total Total HTTP requests",
        "# TYPE glowmag_http_requests_total counter",
    ]
    for method, group, status in sorted(counters):
        lines.append(
            'glowmag_http_requests_total{method="%s",path="%s",status="%s"} %d'
            % (method, group, status, counters[(method, group, status)])
        )
    by_path: dict[str, list[float]] = {}
    for group, ms in samples:
        by_path.setdefault(group, []).append(ms)
    lines += [
        "# HELP glowmag_http_request_duration_ms Request duration",
        "# TYPE glowmag_http_request_duration_ms summary",
    ]
    for group in sorted(by_path):
        vals = sorted(by_path[group])
        lines.append(
            'glowmag_http_request_duration_ms{path="%s",quantile="0.5"} %.1f'
            % (group, _quantile(vals, 0.5))
        )
        lines.append(
            'glowmag_http_request_duration_ms{path="%s",quantile="0.95"} %.1f'
            % (group, _quantile(vals, 0.95))
        )
        lines.append(
            'glowmag_http_request_duration_ms_count{path="%s"} %d' % (group, len(vals))
        )
    return "\n".join(lines) + "\n"


def _check_rate_limit(ip: str, path: str) -> tuple[str | None, int]:
    for prefix, limit in RATE_RULES:
        if path.startswith(prefix):
            now = time.monotonic()
            key = (ip, prefix)
            with _LOCK:
                bucket = _RATE_BUCKETS.setdefault(key, deque())
                while bucket and bucket[0] <= now - RATE_WINDOW:
                    bucket.popleft()
                if len(bucket) >= limit:
                    return prefix, max(1, math.ceil(bucket[0] + RATE_WINDOW - now))
                bucket.append(now)
            return prefix, 0
    return None, 0


def setup(app: FastAPI) -> None:
    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        rid = _sanitize_rid(request.headers.get("x-request-id", "")) or uuid.uuid4().hex[:12]
        token = _RID_VAR.set(rid)
        method = request.method
        path = request.url.path
        ip = request.client.host if request.client else "unknown"
        start = time.perf_counter()
        try:
            prefix, retry = _check_rate_limit(ip, path)
            if retry:
                logger.warning(
                    "rid=%s rate_limited ip=%s path=%s rule=%s retry_after=%s",
                    rid, ip, path, prefix, retry,
                )
                response = JSONResponse(
                    {"detail": "rate_limited", "retry_after": retry},
                    status_code=429,
                    headers={"Retry-After": str(retry)},
                )
            else:
                try:
                    response = await call_next(request)
                except Exception:
                    ms = (time.perf_counter() - start) * 1000
                    if path != "/metrics":
                        _record(method, path_group(path), 500, ms)
                    logger.info(
                        "rid=%s method=%s path=%s status=500 ms=%s",
                        rid, method, path, int(ms),
                    )
                    raise
            ms = (time.perf_counter() - start) * 1000
            if path != "/metrics":
                _record(method, path_group(path), response.status_code, ms)
            logger.info(
                "rid=%s method=%s path=%s status=%s ms=%s",
                rid, method, path, response.status_code, int(ms),
            )
            response.headers["X-Request-Id"] = rid
            _apply_security_headers(path, method, response)
            return response
        finally:
            _RID_VAR.reset(token)

    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint():
        return Response(
            content=render_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )


SECURITY_HEADERS: list[tuple[str, str]] = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    (
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' https: data:; "
        "style-src 'self' 'unsafe-inline' https:; script-src 'self' 'unsafe-inline' https:; "
        "connect-src 'self' https:; font-src 'self' https: data:",
    ),
]

_CACHEABLE_EXT = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".woff", ".woff2", ".ttf", ".otf", ".map",
}


def _apply_security_headers(path: str, method: str, response: Response) -> None:
    for name, value in SECURITY_HEADERS:
        if name not in response.headers:
            response.headers[name] = value
    if not path.startswith("/api/") and method in ("GET", "HEAD") \
            and "Cache-Control" not in response.headers:
        ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
        if "." + ext in _CACHEABLE_EXT:
            response.headers["Cache-Control"] = "public, max-age=604800"
        else:
            response.headers["Cache-Control"] = "no-cache"
