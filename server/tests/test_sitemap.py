"""sitemap/robots 路由自测 —— main.py 显式路由（共享文件只测不改）：
robots.txt 200 + Sitemap 行；sitemap.xml 静态段全量 / 商品与文章动态段（可见性过滤：
status=1 且 published_at 到点）/ 动态查询失败兜底仅静态段不 5xx。
（GM_DB=sqlite:///test_sm.sqlite 独立库；BigInteger 垫片同 test_payments.py）"""

import os
import sys
from datetime import timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_sm.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings  # noqa: E402

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_mod  # noqa: E402
from app.core.db import SessionLocal, utcnow  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Article, Category, Product  # noqa: E402

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


BASE = "http://testserver"

with TestClient(app) as client:
    s = SessionLocal()
    now = utcnow()
    cat = Category(slug="sm-cat", name="SM Cat")
    s.add(cat)
    s.flush()
    s.add_all([
        Product(slug="sm-pub", title="Pub Gel", category_id=cat.id, status=1,
                price_min=1000, price_max=1000, published_at=now - timedelta(days=1)),
        Product(slug="sm-future", title="Future Gel", category_id=cat.id, status=1,
                price_min=1000, price_max=1000, published_at=now + timedelta(days=7)),
        Product(slug="sm-draft", title="Draft Gel", category_id=cat.id, status=0,
                price_min=1000, price_max=1000, published_at=now - timedelta(days=1)),
        Article(slug="sm-post", title="SM Post", author="QA", content_md="x",
                status=1, published_at=now - timedelta(days=1)),
        Article(slug="sm-draft-post", title="SM Draft", author="QA", content_md="x",
                status=0, published_at=now - timedelta(days=1)),
    ])
    s.commit()
    s.close()

    print("== robots.txt ==")
    r = client.get("/robots.txt")
    body = r.text
    check("robots 200 纯文本：User-agent 允全站 + Sitemap 绝对地址",
          r.status_code == 200 and body.startswith("User-agent: *")
          and "Allow: /" in body and f"Sitemap: {BASE}/sitemap.xml" in body
          and r.headers["content-type"].startswith("text/plain"), body)

    print("== sitemap.xml 静态段 + 动态段 ==")
    r = client.get("/sitemap.xml")
    xml = r.text
    check("sitemap 200 text/xml + urlset 包裹",
          r.status_code == 200 and r.headers["content-type"].startswith("text/xml")
          and xml.startswith('<?xml version="1.0"') and "<urlset" in xml, r.status_code)
    static_ok = all(f"<loc>{BASE}{p}</loc>" in xml for p in
                    ("/", "/store", "/bundles", "/gallery", "/blog", "/faq",
                     "/privacy", "/gift-cards"))
    check("静态路由全量收录（首页/门店/捆绑/画廊/博客/FAQ/隐私/礼品卡）", static_ok, xml[:400])
    check("商品动态段：已发布商品 slug 入 sitemap",
          f"<loc>{BASE}/product?slug=sm-pub</loc>" in xml, None)
    check("可见性过滤：定时未到点（future）与草稿（status=0）商品不入",
          "sm-future" not in xml and "sm-draft<" not in xml and "slug=sm-draft" not in xml,
          [ln for ln in xml.splitlines() if "sm-" in ln])
    check("文章动态段：已发布文章 slug 入 sitemap",
          f"<loc>{BASE}/blog/post?slug=sm-post</loc>" in xml, None)
    check("草稿文章不入 sitemap", "sm-draft-post" not in xml, None)
    check("发布商品 lastmod 落盘（published_at isoformat）",
          "<lastmod>" in xml, None)

    print("== 查询失败兜底 ==")
    _orig_factory = main_mod.SessionLocal

    def _boom():
        raise RuntimeError("db down")

    main_mod.SessionLocal = _boom
    try:
        r = client.get("/sitemap.xml")
    finally:
        main_mod.SessionLocal = _orig_factory
    xml2 = r.text
    check("动态段查询异常 → 200 兜底仅静态段（sitemap 不整体 5xx）",
          r.status_code == 200 and f"<loc>{BASE}/store</loc>" in xml2
          and "sm-pub" not in xml2 and "<urlset" in xml2, r.status_code)

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
