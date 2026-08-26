"""优惠券领取/券包（营销域）回归（GM_DB=sqlite:///test_coupons_<rand>.sqlite 独立库，
随机文件名避免与并发测试会话共享库冲突；BigInteger 垫片同 test_xpay.py）。覆盖：
- 领券中心列表过滤：is_claimable/is_active/窗口/领完四重过滤 + remaining/claimed 口径
- 领取：成功回完整码 / 未登录 401 / 重复领 409 already_claimed / 停用·不可领·窗口外
  409 coupon_ended / 领完 409 coupon_exhausted / 领取不动 used_count
- mine 三态：0可用 1已用 2已过期（ends_at 惰性判定）+ order_no join + claimed_at 倒序
- 下单核销：登录+用码 → CAS 置已用挂订单；90 秒防重回不重复核销；无券用户零影响；
  preview/place 的 code 参数语义不变
"""

import os
import random
import sys
from datetime import timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, f"test_coupons_{random.randint(100000, 999999)}.sqlite").replace("\\", "/")
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

from app.core.db import SessionLocal, utcnow  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, Order, Product, User, Variant  # noqa: E402
from app.models.promo import DiscountCode, UserCoupon  # noqa: E402

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


ADDR = {"full_name": "T", "line1": "1 Main St", "city": "SF", "state": "CA",
        "zip": "94110", "country": "US", "phone": "+14155550001"}


def place_body(code=None, email="user@glow.test"):
    body = {"email": email, "address": ADDR}
    if code:
        body["code"] = code
    return body


with TestClient(app) as client:
    s = SessionLocal()
    now = utcnow()

    cat = Category(slug="nail-care", name="Nail Care")
    s.add(cat)
    s.flush()
    p = Product(slug="cp-oil", title="CP Oil", category_id=cat.id, status=1,
                hero_image="https://img/c.jpg", price_min=5000, price_max=5000)
    s.add(p)
    s.flush()
    v = Variant(product_id=p.id, sku="CP-OIL-1", option1_value="30ml",
                option2_value="1pc", price=5000, stock=100)
    s.add(v)
    emma = User(email="emma@glow.test", password_hash=hash_password("x"),
                name="Emma", role=0, points=0)
    bob = User(email="bob@glow.test", password_hash=hash_password("x"),
               name="Bob", role=0, points=0)
    carol = User(email="carol@glow.test", password_hash=hash_password("x"),
                 name="Carol", role=0, points=0)
    s.add_all([v, emma, bob, carol])

    def mk_code(code, **kw):
        d = dict(code=code, name=f"{code} 券", type=2, value=500, min_subtotal=0,
                 usage_limit=None, per_user_limit=1, first_order_only=0, used_count=0,
                 starts_at=now - timedelta(days=1), ends_at=None,
                 is_active=1, is_claimable=1)
        d.update(kw)
        dc = DiscountCode(**d)
        s.add(dc)
        return dc

    save5 = mk_code("SAVE5", usage_limit=100, used_count=3)
    forever = mk_code("FOREVER")
    notcl = mk_code("NOTCL", is_claimable=0)
    gone = mk_code("GONE", is_active=0)
    soon = mk_code("SOON", starts_at=now + timedelta(days=1))
    full = mk_code("FULL", usage_limit=2, used_count=2)
    lasted = mk_code("LASTED", ends_at=now - timedelta(days=1))
    s.commit()

    emma_tok = {"Authorization": f"Bearer {create_token(emma.id, 0)}"}
    bob_tok = {"Authorization": f"Bearer {create_token(bob.id, 0)}"}
    carol_tok = {"Authorization": f"Bearer {create_token(carol.id, 0)}"}

    # ===== 领券中心列表过滤 =====
    r = client.get("/api/promo/coupons")
    check("列表公开可访问", r.status_code == 200, r.text)
    items = {i["id"]: i for i in r.json()["items"]}
    check("仅窗口内可领未领完的券上架",
          set(items) == {save5.id, forever.id}, sorted(items))
    check("remaining = usage_limit - used_count",
          items[save5.id]["remaining"] == 97, items[save5.id])
    check("无限额 remaining 为 null", items[forever.id]["remaining"] is None)
    check("未登录 claimed 恒 false",
          all(i["claimed"] is False for i in items.values()))
    check("面额字段口径", items[save5.id]["type"] == 2
          and items[save5.id]["value"] == 500
          and items[save5.id]["min_subtotal"] == 0
          and items[save5.id]["first_order_only"] == 0)
    r = client.get("/api/promo/coupons", headers=emma_tok)
    check("未领取时登录 claimed 仍 false",
          all(i["claimed"] is False for i in r.json()["items"]))

    # ===== 领取 =====
    r = client.post(f"/api/promo/coupons/{save5.id}/claim")
    check("未登录领取 → 401", r.status_code == 401, r.text)
    r = client.post(f"/api/promo/coupons/{save5.id}/claim", headers=emma_tok)
    check("领取成功回完整码", r.status_code == 200
          and r.json() == {"ok": True, "code": "SAVE5"}, r.text)
    r = client.post(f"/api/promo/coupons/{save5.id}/claim", headers=emma_tok)
    check("重复领取 → 409 already_claimed", r.status_code == 409
          and r.json()["detail"] == "already_claimed", r.text)
    r = client.post(f"/api/promo/coupons/{save5.id}/claim", headers=bob_tok)
    check("不同用户可领同码", r.status_code == 200
          and r.json()["code"] == "SAVE5", r.text)
    for dc, why in ((lasted, "已过期"), (notcl, "不可领"), (gone, "已停用"),
                    (soon, "未开始")):
        r = client.post(f"/api/promo/coupons/{dc.id}/claim", headers=emma_tok)
        check(f"领取{why} → 409 coupon_ended", r.status_code == 409
              and r.json()["detail"] == "coupon_ended", r.text)
    r = client.post(f"/api/promo/coupons/{full.id}/claim", headers=emma_tok)
    check("领取已领完 → 409 coupon_exhausted", r.status_code == 409
          and r.json()["detail"] == "coupon_exhausted", r.text)
    r = client.post("/api/promo/coupons/999999/claim", headers=emma_tok)
    check("不存在 → 404", r.status_code == 404, r.text)
    s.expire_all()
    check("领取不动 used_count（核销时才动）",
          s.get(DiscountCode, save5.id).used_count == 3)
    r = client.get("/api/promo/coupons", headers=emma_tok)
    got = {i["id"]: i for i in r.json()["items"]}
    check("已领标记回填", got[save5.id]["claimed"] is True
          and got[forever.id]["claimed"] is False)

    # ===== mine 三态 =====
    # 过期态无法经 API 领取（窗口拦截），按真实时序直接落一行历史持有记录
    s.add(UserCoupon(user_id=emma.id, code_id=lasted.id,
                     claimed_at=now - timedelta(days=2)))
    s.commit()
    r = client.get("/api/promo/coupons/mine")
    check("mine 未登录 → 401", r.status_code == 401, r.text)
    r = client.get("/api/promo/coupons/mine", headers=emma_tok)
    check("mine 登录可访问", r.status_code == 200, r.text)
    mine = r.json()["items"]
    check("claimed_at 倒序", [i["code"] for i in mine] == ["SAVE5", "LASTED"],
          [i["code"] for i in mine])
    m0 = mine[0]
    check("未用券 status=0", m0["status"] == 0 and m0["used_at"] is None
          and m0["order_no"] is None, m0)
    m1 = mine[1]
    check("过期券惰性判定 status=2", m1["status"] == 2
          and m1["expires_at"] is not None, m1)

    # ===== preview code 语义不变 =====
    r = client.post("/api/checkout/preview", headers=emma_tok,
                    json={"items": [{"variant_id": v.id, "qty": 1}], "code": "SAVE5"})
    check("preview 用码 code_valid/code_id 不变", r.status_code == 200
          and r.json()["code_valid"] is True
          and r.json()["code_id"] == save5.id
          and r.json()["code_discount"] == 500, r.text)

    # ===== 下单核销（登录 + 用码 + 有未用券） =====
    r = client.post("/api/cart/items", headers=emma_tok,
                    json={"variant_id": v.id, "qty": 1})
    check("加车", r.status_code == 201, r.text)
    r = client.post("/api/checkout/place", headers=emma_tok,
                    json=place_body("SAVE5", "emma@glow.test"))
    check("用码下单成功", r.status_code == 201 and r.json().get("order_no"), r.text)
    emma_order_no = r.json()["order_no"]
    s.expire_all()
    uc = s.query(UserCoupon).filter_by(user_id=emma.id, code_id=save5.id).one()
    emma_order = s.query(Order).filter_by(order_no=emma_order_no).one()
    check("券包核销 status=1 + used_at", uc.status == 1 and uc.used_at is not None)
    check("核销挂订单 order_id", uc.order_id == emma_order.id)
    r = client.get("/api/promo/coupons/mine", headers=emma_tok)
    used = next(i for i in r.json()["items"] if i["code"] == "SAVE5")
    check("mine 已用态回 order_no", used["status"] == 1
          and used["order_no"] == emma_order_no and used["used_at"], used)

    # 90 秒防重回：清车后同 body 重放 → 幂等返回同单，不重复核销
    r = client.post("/api/checkout/place", headers=emma_tok,
                    json=place_body("SAVE5", "emma@glow.test"))
    check("重放下单幂等返回同单", r.status_code == 201
          and r.json()["order_no"] == emma_order_no, r.text)
    s.expire_all()
    check("重放不重复建单", s.query(Order).filter_by(
        user_id=emma.id, status=0).count() == 1)
    uc2 = s.query(UserCoupon).filter_by(user_id=emma.id, code_id=save5.id).one()
    check("重放不重复核销（order_id 不变）", uc2.id == uc.id
          and uc2.order_id == emma_order.id and uc2.status == 1)

    # ===== 不同用户独立核销 / 无券用户零影响 =====
    r = client.post("/api/cart/items", headers=bob_tok,
                    json={"variant_id": v.id, "qty": 1})
    r = client.post("/api/checkout/place", headers=bob_tok,
                    json=place_body("SAVE5", "bob@glow.test"))
    bob_order_no = r.json().get("order_no")
    s.expire_all()
    bob_uc = s.query(UserCoupon).filter_by(user_id=bob.id, code_id=save5.id).one()
    bob_order = s.query(Order).filter_by(order_no=bob_order_no).one()
    check("bob 券独立核销挂自己的单", bob_uc.status == 1
          and bob_uc.order_id == bob_order.id)
    r = client.post("/api/cart/items", headers=carol_tok,
                    json={"variant_id": v.id, "qty": 1})
    r = client.post("/api/checkout/place", headers=carol_tok,
                    json=place_body("SAVE5", "carol@glow.test"))
    check("无券用户用码下单不受影响", r.status_code == 201, r.text)
    s.expire_all()
    check("无券用户不产生券包记录", s.query(UserCoupon).filter_by(
        user_id=carol.id).count() == 0)
    check("下单核销不动 used_count（支付时才自增）",
          s.get(DiscountCode, save5.id).used_count == 3)

    # ===== mine 补充：可用态（FOREVER）=====
    r = client.post(f"/api/promo/coupons/{forever.id}/claim", headers=emma_tok)
    check("补领 FOREVER", r.status_code == 200, r.text)
    r = client.get("/api/promo/coupons/mine", headers=emma_tok)
    codes = [(i["code"], i["status"]) for i in r.json()["items"]]
    check("mine 三态齐全（0/1/2）", ("SAVE5", 1) in codes
          and ("FOREVER", 0) in codes and ("LASTED", 2) in codes, codes)

    s.close()

print(f"\n==== test_coupons: {PASSED} passed, {len(FAILED)} failed ====")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
