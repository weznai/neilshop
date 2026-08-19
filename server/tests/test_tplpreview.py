"""运营智能体 C 自测 —— 邮件模板预览端点 GET /api/admin/ops/email-templates
（GM_DB=sqlite:///server/test_tp.sqlite 独立库；BigInteger 垫片抄 test_payments.py；
index.html 新品区 locale 联动由 jsdom 侧 scripts 目录配套用例覆盖：jsdomtest/test_tplpreview_jsdom.js）"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_HERE = os.path.dirname(os.path.abspath(__file__))
_CAND = [os.path.join(_HERE, "server"), os.path.dirname(_HERE)]
_SERVER = next(p for p in _CAND if os.path.isdir(os.path.join(p, "app")))
_DB = os.path.join(_SERVER, "test_tp.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, _SERVER)

from app.core.config import settings as app_settings  # noqa: E402

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, init_db  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

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


init_db()
s = SessionLocal()
admin = User(email="ops@glow.test", name="Ops", role=2, status=1,
             password_hash=hash_password("x"))
customer = User(email="cindy@glow.test", name="Cindy", role=0, status=1,
                password_hash=hash_password("x"))
s.add_all([admin, customer])
s.commit()
admin_id, customer_id = admin.id, customer.id
s.close()

WANT_NAMES = {"daily_digest", "order_paid", "order_shipped", "order_refunded",
              "abandoned_cart", "welcome_coupon", "restock_notify", "password_reset"}

with TestClient(app) as client:
    atok = {"Authorization": f"Bearer {create_token(admin_id, 2)}"}
    ctok = {"Authorization": f"Bearer {create_token(customer_id, 0)}"}

    # ===== 守卫 =====
    r = client.get("/api/admin/ops/email-templates")
    check("守卫：未登录 401", r.status_code == 401, r.status_code)
    r = client.get("/api/admin/ops/email-templates", headers=ctok)
    check("守卫：顾客 403", r.status_code == 403, r.status_code)

    # ===== 端点主体 =====
    r = client.get("/api/admin/ops/email-templates", headers=atok)
    d = r.json()
    check("端点 200 且 items=8",
          r.status_code == 200 and isinstance(d.get("items"), list) and len(d["items"]) == 8,
          r.status_code)
    names = {t.get("name") for t in d["items"]}
    check("模板清单 = 8 个既定模板（daily_digest/…/password_reset）",
          names == WANT_NAMES, names)
    check("每项三键 name/subject/html 且非空",
          all(set(t.keys()) == {"name", "subject", "html"}
              and all(t[k] for k in ("name", "subject", "html")) for t in d["items"]),
          [sorted(t.keys()) for t in d["items"]])
    by_name = {t["name"]: t for t in d["items"]}

    # ===== 渲染一致性：GLOWMAG 页脚 + 退订链（8 模板全量）=====
    check("html 渲染一致性：8/8 含 GLOWMAG 页脚与示例邮箱",
          all("GLOWMAG &middot; Press-on nails" in t["html"]
              and "emma@glowmag.com" in t["html"] for t in d["items"]))
    check("html 渲染一致性：8/8 含退订链（unsubscribe?email=）",
          all('https://glowmag.example/unsubscribe?email=emma@glowmag.com' in t["html"]
              for t in d["items"]))

    # ===== 关键模板内容 =====
    dd = by_name["daily_digest"]
    check("daily_digest：含示例 GMV $2669.00 与日报标题",
          "$2669.00" in dd["html"] and "Daily Digest &mdash; 2026-07-27" in dd["html"],
          dd["subject"])
    ab = by_name["abandoned_cart"]
    check("abandoned_cart：含 recovery 恢复链与商品名",
          "https://glowmag.example/cart?recover=rt-demo-token" in ab["html"]
          and "Bare Gems · Short Almond" in ab["html"], ab["subject"])
    op = by_name["order_paid"]
    check("order_paid：subject 含示例单号，html 含金额 $31.10（3110 美分÷100）",
          "NS260728D4E5F6" in op["subject"] and "$31.10" in op["html"], op["subject"])
    wc = by_name["welcome_coupon"]
    check("welcome_coupon：含折扣码 WELCOME20 与 10% 力度",
          "WELCOME20" in wc["html"] and "10% off" in wc["html"], wc["subject"])

    # ===== 与真实发送渲染同源（emails.py 只读）=====
    from app.services import emails
    check("预览 html 与 emails.render 同源（welcome_coupon 逐字节一致）",
          wc["html"] == emails.render(
              "welcome_coupon", email="emma@glowmag.com",
              order_no="NS260728D4E5F6", discount=10, code="WELCOME20"))

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
