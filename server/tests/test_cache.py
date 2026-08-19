"""性能智能体 B —— 热路径只读缓存自测：TTLCache 单元 + 开启态集成（GM_CACHE=1 显式开启）+ 默认关闭子进程。"""

import os
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.chdir(BASE)

DB_FILE = BASE / "test_c2.sqlite"
for suffix in ("", "-shm", "-wal"):
    p = Path(str(DB_FILE) + suffix)
    if p.exists():
        p.unlink()
os.environ["GM_DB"] = f"sqlite:///{DB_FILE.as_posix()}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
os.environ["GM_CACHE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import BigInteger, event  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):
    return "INTEGER"


from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal, engine, init_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.domains.catalog import service as catalog_service  # noqa: E402
from app.domains.catalog.schemas import CategoryCreateIn, VariantUpdateIn  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, Product, User, Variant  # noqa: E402
from app.services.cache import MISS, TTLCache, _cache  # noqa: E402

PASSED = 0
FAILED = []

SQL_COUNT = 0


@event.listens_for(engine, "before_cursor_execute")
def _count_sql(*a, **k):
    global SQL_COUNT
    SQL_COUNT += 1


def check(name, cond, info=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok {PASSED:02d} - {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {PASSED + 1:02d} - {name}  {info}")


def sql_delta(fn):
    global SQL_COUNT
    before = SQL_COUNT
    out = fn()
    return out, SQL_COUNT - before


print("== TTLCache 单元 ==")


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


clock = FakeClock()
c = TTLCache(ttl=30, clock=clock)
c.set("catalog:products|page=1", {"items": [1]})
_v1 = c.get("catalog:products|page=1")
_v2 = c.get("catalog:products|page=1")
check("set/get 返回同引用", _v1 is _v2 and _v1 == {"items": [1]})
check("未知键返回 MISS", c.get("nope") is MISS)
clock.now += 31
check("过期后 MISS 且条目清除", c.get("catalog:products|page=1") is MISS
      and c.stats()["size"] == 0)
c.set("catalog:products|page=1", "a")
c.set("catalog:detail|slug=x", "b")
c.set("ai:hot|size=8", "h")
c.clear("catalog")
check("clear(prefix) 只清匹配前缀", c.get("catalog:products|page=1") is MISS
      and c.get("catalog:detail|slug=x") is MISS and c.get("ai:hot|size=8") == "h")
st = c.stats()
check("stats 汇总 hits/misses/size", st["size"] == 1 and st["hits"] >= 1 and st["misses"] >= 3,
      st)
c.clear()
c0 = TTLCache(ttl=0, clock=clock)
c0.set("k", "v")
check("ttl=0 时 set 不存储", c0.stats()["size"] == 0 and c0.get("k") is MISS)

print("== 配置映射 ==")
check("GM_CACHE=1 → 开启且 ttl 默认 30", settings.cache_enable is True
      and settings.cache_ttl_seconds == 30)

print("== 开启态集成（sqlite test_c2） ==")
init_db()
db = SessionLocal()
admin = User(email="cache-admin@glowmag.test", name="Cache Admin", role=2, status=1,
             password_hash=hash_password("x"))
db.add(admin)
db.flush()
cat = Category(slug="press-on", name="Press-on")
db.add(cat)
db.flush()
p1 = Product(slug="bare-gems", title="Bare Gems", category_id=cat.id, status=1,
             price_min=1599, price_max=1599, hero_image="/img.jpg", sold_count=9,
             is_best_seller=1, published_at=None)
p2 = Product(slug="draft-one", title="Draft One", category_id=cat.id, status=0,
             price_min=999, price_max=999, hero_image="/img2.jpg")
db.add_all([p1, p2])
db.flush()
v1 = Variant(product_id=p1.id, sku="BG-SA-24", option1_value="Short Almond",
             option2_value="24pcs", price=1599, stock=10)
v2 = Variant(product_id=p2.id, sku="DR-01", option1_value="Round",
             option2_value="24pcs", price=999, stock=5)
db.add_all([v1, v2])
db.commit()
db.close()
_cache.clear()

with TestClient(app) as client:
    _, d1 = sql_delta(lambda: client.get("/api/catalog/products",
                                         params={"sort": "new", "page": 1, "size": 12}))
    check("首次列表走 SQL 且入缓存", d1 > 0 and _cache.stats()["size"] >= 1)
    st_before = _cache.stats()
    _, d2 = sql_delta(lambda: client.get("/api/catalog/products",
                                         params={"sort": "new", "page": 1, "size": 12}))
    check("同参列表第二次命中（0 SQL，hits+1）", d2 == 0
          and _cache.stats()["hits"] == st_before["hits"] + 1)
    _, d3 = sql_delta(lambda: client.get("/api/catalog/products",
                                         params={"sort": "best", "page": 1, "size": 12}))
    _, d4 = sql_delta(lambda: client.get("/api/catalog/products",
                                         params={"sort": "best", "page": 1, "size": 12}))
    check("不同参数不串缓存（best 首查走 SQL，重查命中）", d3 > 0 and d4 == 0)

    _, e1 = sql_delta(lambda: client.get("/api/catalog/products/bare-gems"))
    _, e2 = sql_delta(lambda: client.get("/api/catalog/products/bare-gems"))
    check("详情两次：首查 SQL，第二次 0 SQL", e1 > 0 and e2 == 0)

    size_before = _cache.stats()["size"]
    r1 = client.get("/api/catalog/products", params={"sort": "bad"})
    r2 = client.get("/api/catalog/products", params={"sort": "bad"})
    check("无效 sort 两次 400 且不缓存", r1.status_code == 400 and r2.status_code == 400
          and _cache.stats()["size"] == size_before)

    r = client.get("/api/catalog/products", params={"size": 100})
    check("发布前列表不含草稿商品", "draft-one" not in
          [i["slug"] for i in r.json()["items"]])
    db = SessionLocal()
    catalog_service.admin_publish_product(db, admin, p2.id)
    db.close()
    _, d5 = sql_delta(lambda: client.get("/api/catalog/products", params={"size": 100}))
    r = client.get("/api/catalog/products", params={"size": 100})
    check("admin publish 后缓存失效，列表立即含新商品", d5 > 0
          and "draft-one" in [i["slug"] for i in r.json()["items"]])

    client.get("/api/catalog/products/bare-gems")
    db = SessionLocal()
    catalog_service.admin_update_variant(db, admin, v1.id, VariantUpdateIn(price=1899))
    db.close()
    r = client.get("/api/catalog/products/bare-gems")
    check("variant 改价后详情立即新价", r.status_code == 200
          and any(v["price"] == 1899 for v in r.json()["variants"]))

    _, h1 = sql_delta(lambda: client.get("/api/ai/hot", params={"size": 8}))
    _, h2 = sql_delta(lambda: client.get("/api/ai/hot", params={"size": 8}))
    check("ai/hot 首查 SQL、二次命中", h1 > 0 and h2 == 0)
    db = SessionLocal()
    catalog_service.admin_create_category(
        db, admin, CategoryCreateIn(slug=f"tmp-{p1.id}", name="Tmp"))
    db.close()
    _, h3 = sql_delta(lambda: client.get("/api/ai/hot", params={"size": 8}))
    check("catalog 写操作域级清理连 ai 前缀一并失效", h3 > 0)

    settings.cache_ttl_seconds = 0
    _, t1 = sql_delta(lambda: client.get("/api/catalog/products",
                                         params={"sort": "new", "page": 1, "size": 12}))
    _, t2 = sql_delta(lambda: client.get("/api/catalog/products",
                                         params={"sort": "new", "page": 1, "size": 12}))
    check("ttl=0 直通（SQL 每次都发）", t1 > 0 and t2 > 0)
    settings.cache_ttl_seconds = 30

print("== 默认关闭（子进程，无 GM_CACHE / GM_CACHE=0） ==")


def run_probe(env_extra: dict | None, tag: str) -> tuple:
    _env = {k: v for k, v in os.environ.items() if k != "GM_CACHE"}
    _env["GM_DB"] = f"sqlite:///{DB_FILE.as_posix()}"
    if env_extra:
        _env.update(env_extra)
    probe = (
        "import sys; sys.path.insert(0, r'%s');\n"
        "from app.core.config import settings\n"
        "from app.core.db import SessionLocal\n"
        "from app.domains.catalog import service\n"
        "from app.services.cache import _cache\n"
        "db = SessionLocal()\n"
        "out = service.list_products(db, category=None, tag=None, q=None, sort='new', page=1, size=12, locale=None)\n"
        "db.close()\n"
        "assert settings.cache_enable is False and settings.cache_ttl_seconds == 0, 'default off broken'\n"
        "assert _cache.stats()['size'] == 0, 'cache stored while disabled'\n"
        "assert out['total'] >= 2, 'direct query broken'\n"
        "print('%s OK')\n"
    ) % (str(BASE), tag)
    return subprocess.run([sys.executable, "-c", probe], env=_env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", cwd=str(BASE))


r = run_probe(None, "SUBPROCESS-UNSET")
check("默认 import（无 GM_CACHE）：直查 DB 且零缓存",
      r.returncode == 0 and "SUBPROCESS-UNSET OK" in r.stdout, r.stdout + r.stderr)
r = run_probe({"GM_CACHE": "0"}, "SUBPROCESS-ZERO")
check("GM_CACHE=0：同样直查 DB 且零缓存",
      r.returncode == 0 and "SUBPROCESS-ZERO OK" in r.stdout, r.stdout + r.stderr)

print(f"\nALL PASS: {PASSED}/{PASSED + len(FAILED)}")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
