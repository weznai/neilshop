"""GLOWMAG FastAPI 单体入口 —— 域模块即未来微服务边界

前后台前端物理分离（web/client + web/admin 两个独立静态站），暂同进程挂载：
  /       → web/client  （C 端门店）
  /admin  → web/admin   （管理控制台，可整体搬独立域名，仅改静态托管 + GM_ALLOWED_ORIGINS）
拆分缝：后台前端 API 基址可配置（assets/api.js 的 window.GM_ADMIN_API_BASE），
后台会话独立 Cookie gm_admin_token（SameSite=Strict + 短时效）。
"""

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI

from app.core.config import settings
from app.core.db import init_db

# 域路由直连（routers/ 单行重导出层已裁撤，domains 即装配面）
from app.domains.member import (
    router_account as account, router_points as points,
    router_referrals as referrals, router_subscriptions as subscriptions,
)
from app.domains.catalog import router as catalog, router_admin as admin_catalog
from app.domains.trade import (
    router_admin as admin_trade, router_cart as cart, router_checkout as checkout,
    router_exchanges as exchanges, router_orders as orders, router_payments as payments,
    router_returns as returns,
)
from app.domains.promo import router as promo, router_admin as admin_promo
from app.domains.content import router as content, router_admin as admin_content
from app.domains.support import router as support, router_admin as admin_support
from app.domains.ops import router as admin_ops
from app.domains.ai import router as ai

# 后台聚合：ops + promo/content/support 三域 admin 端点（原 routers/admin_ops.py 的组装逻辑内联至此）
_admin_combined = APIRouter()
for _r in (admin_ops.router, admin_promo.router, admin_content.router, admin_support.router):
    _admin_combined.include_router(_r)
admin_ops_all = SimpleNamespace(router=_admin_combined)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="GLOWMAG API",
    version="0.2.0",
    description="指甲电商独立站 · FastAPI 单体（按域分包，对齐微服务演进蓝图）",
    lifespan=lifespan,
)

# CORS：同源部署（默认）不加中间件最安全；前后台拆域时 GM_ALLOWED_ORIGINS 配白名单
_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
if _origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Cart-Token"],
    )


_ROUTERS = (
    account, catalog, cart, checkout, orders, payments, returns,
    promo, points, content, support, admin_catalog, admin_trade, admin_ops_all, ai,
    referrals, subscriptions, exchanges,
)
for module in _ROUTERS:
    app.include_router(module.router)


try:
    from app.core.observability import setup as _setup_observability

    _setup_observability(app)
except ImportError:
    pass


@app.get("/api/health")
def health():
    return {"ok": True, "service": "glowmag-api", "version": "0.3.0"}


# 旧静态站入口重定向（书签/外链兼容 → 后台 SPA）
from fastapi.responses import RedirectResponse  # noqa: E402


@app.get("/admin-login.html", include_in_schema=False)
def legacy_admin_login():
    return RedirectResponse("/admin/")


# 静态站挂载（放最后，/api 优先匹配）：单一发布目录 web/dist（client 产物在根、admin 在 /admin）
# 前后台为 Vite+Vue SPA：未命中路径回落各自 index.html（history 路由）
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    """SPA 静态托管：未命中（404 异常或响应）按路径前缀回落 index.html。
    /admin* → admin/index.html，其余 → /index.html；/api/* 一律不回落（保 API 404 JSON 语义）。"""

    async def get_response(self, path: str, scope):
        # Starlette get_path() 经 os.path.normpath：Windows 下分隔符为 "\"，统一归一后再做前缀判断
        p = path.replace("\\", "/").lstrip("/")
        try:
            response = await super().get_response(path, scope)
            if response.status_code != 404:
                return response
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or p.startswith("api"):
                raise
        if p.startswith("api"):
            raise StarletteHTTPException(status_code=404)
        index = "admin/index.html" if p == "admin" or p.startswith("admin/") else "index.html"
        return await super().get_response(index, scope)


_WEB = Path(__file__).resolve().parents[2] / "web" / "dist"
if (_WEB / "index.html").exists():
    app.mount("/", SPAStaticFiles(directory=str(_WEB), html=True), name="spa")
