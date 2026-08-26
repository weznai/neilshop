"""积分/会员域修复回归（P0-1/P0-2 并发原子性 + P1 修复项）。
sqlite 独立库自包含；并发用 ThreadPoolExecutor 直打 service 层（test_concurrency 为
MySQL 专属，此为 sqlite 版）。BigInteger 垫片同 test_refsub.py。
"""

import hashlib
import hmac
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_points_ext.sqlite").replace("\\", "/")
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

import jwt as pyjwt  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal, init_db, utcnow  # noqa: E402
from app.core.enums import PointsReason, ReferralStatus  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    EmailPreference, NewsletterSubscriber, Order, OrderItem, PointsLedger,
    Product, Referral, Ticket, TicketMessage, User, WishlistItem,
)
from app.services import points as points_svc  # noqa: E402
from app.services.referrals import derive_code, on_order_paid  # noqa: E402
from app.domains.member import repository as repo  # noqa: E402
from app.domains.member import service_account, service_referrals  # noqa: E402
from app.domains.member.schemas import (  # noqa: E402
    NewsletterIn, PasswordResetConfirmIn, UnsubscribeIn,
)

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

ADDR = {"full_name": "T", "line1": "1 Main St", "city": "SF", "state": "CA",
        "zip": "94110", "country": "US", "phone": "+14155550001"}


def make_order(s, no, *, user_id, email, total=3000):
    o = Order(order_no=no, user_id=user_id, email=email, status=0,
              subtotal=total, grand_total=total, shipping_address=ADDR)
    s.add(o)
    s.flush()
    return o


def fresh_balance(uid):
    s = SessionLocal()
    try:
        return int(s.execute(points_svc._POINTS_OF_SQL, {"uid": uid}).scalar())
    finally:
        s.close()
# ===== P0-1：发放原子原语 =====

s = SessionLocal()
u1 = User(email="p1@glowmag.com", password_hash=hash_password("x"), name="P1", points=0)
s.add(u1)
s.commit()
uid1 = u1.id

bal = points_svc.add_points(s, uid1, 500)
s.commit()
check("add_points 单线程：+500 返回新余额", bal == 500 and fresh_balance(uid1) == 500,
      (bal, fresh_balance(uid1)))

# 并发 grant_for_order：6 线程 × 15 次 × 100 分 → 恰 9000（ORM 读改写会丢更新少发）
stub_order = Order(id=0, user_id=uid1)
N_T, N_ITER, GRANT = 6, 15, 100
barrier = threading.Barrier(N_T)


def grant_worker(_i):
    barrier.wait()
    for _ in range(N_ITER):
        sx = SessionLocal()
        try:
            points_svc.grant_for_order(sx, stub_order, GRANT)
            sx.commit()
        finally:
            sx.close()


with ThreadPoolExecutor(max_workers=N_T) as ex:
    list(ex.map(grant_worker, range(N_T)))

s.expire_all()
rows = s.query(PointsLedger).filter(PointsLedger.user_id == uid1).all()
final = fresh_balance(uid1)
check("grant_for_order 并发不丢更新：先前 500 + 6x15x100=9000 恰额到账 + ledger 对齐",
      final == 500 + N_T * N_ITER * GRANT and len(rows) == N_T * N_ITER
      and sum(r.change for r in rows) == N_T * N_ITER * GRANT,
      (final, len(rows)))

# ===== P0-2：spend 冻结守卫（口径一致） =====

u2 = User(email="p2@glowmag.com", password_hash=hash_password("x"), name="P2", points=1000)
s.add(u2)
s.commit()
uid2 = u2.id
# 冻结 1000（frozen=1 正流水）→ 可用 0
s.execute(text(
    "INSERT INTO points_ledger (user_id, change, balance_after, reason, frozen, created_at)"
    " VALUES (:u, 1000, 1000, 1, 1, :t)"), {"u": uid2, "t": utcnow()})
s.commit()

try:
    points_svc.spend(s, uid2, 200)
    check("spend 冻结不可花：余额 1000 全冻结 → ValueError", False, "no exception")
except ValueError:
    check("spend 冻结不可花：余额 1000 全冻结 → ValueError", True)

# 解冻后可花
s.execute(text("UPDATE points_ledger SET frozen=0 WHERE user_id=:u"), {"u": uid2})
s.commit()
bal = points_svc.spend(s, uid2, 300)
s.commit()
check("spend 解冻后可花：-300 → 700", bal == 700 and fresh_balance(uid2) == 700,
      (bal, fresh_balance(uid2)))

# 并发双花：余额 700 无冻结，6 线程同时 spend(600) → 恰 1 成功，终态 100
barrier2 = threading.Barrier(N_T)
wins = []


def spend_worker(_i):
    barrier2.wait()
    sx = SessionLocal()
    try:
        points_svc.spend(sx, uid2, 600)
        sx.commit()
        return 1
    except ValueError:
        return 0
    finally:
        sx.close()


with ThreadPoolExecutor(max_workers=N_T) as ex:
    wins = list(ex.map(spend_worker, range(N_T)))
check("spend 并发双花：恰 1 成功（SQL 守卫为准）终态 100",
      sum(wins) == 1 and fresh_balance(uid2) == 100, (sum(wins), fresh_balance(uid2)))

# 并发花到冻结线：余额 1000 + 冻结 400 → 可用 600，6 线程 spend(600) → 恰 1 成功，终态 400
u3 = User(email="p3@glowmag.com", password_hash=hash_password("x"), name="P3", points=1000)
s.add(u3)
s.commit()
uid3 = u3.id
s.execute(text(
    "INSERT INTO points_ledger (user_id, change, balance_after, reason, frozen, created_at)"
    " VALUES (:u, 400, 400, 1, 1, :t)"), {"u": uid3, "t": utcnow()})
s.commit()
barrier3 = threading.Barrier(N_T)


def spend_frozen_worker(_i):
    barrier3.wait()
    sx = SessionLocal()
    try:
        points_svc.spend(sx, uid3, 600)
        sx.commit()
        return 1
    except ValueError:
        return 0
    finally:
        sx.close()


with ThreadPoolExecutor(max_workers=N_T) as ex:
    wins3 = list(ex.map(spend_frozen_worker, range(N_T)))
check("spend 并发不侵占冻结额：恰 1 成功且终态==冻结额 400",
      sum(wins3) == 1 and fresh_balance(uid3) == 400, (sum(wins3), fresh_balance(uid3)))

# 静态边界：非并发时可用=700-400? 用 u2（700 无冻结）与 u3 已验证，再验部分冻结静态路径
u4 = User(email="p4@glowmag.com", password_hash=hash_password("x"), name="P4", points=1000)
s.add(u4)
s.commit()
uid4 = u4.id
s.execute(text(
    "INSERT INTO points_ledger (user_id, change, balance_after, reason, frozen, created_at)"
    " VALUES (:u, 300, 300, 1, 1, :t)"), {"u": uid4, "t": utcnow()})
s.commit()
bal = points_svc.spend(s, uid4, 700)   # 扣后 300 == 冻结 300，允许
s.commit()
try:
    points_svc.spend(s, uid4, 1)       # 再扣 1 就侵占冻结
    check("spend 静态边界：扣后=冻结额允许 / 再扣 1 拒绝", False, "no exception")
except ValueError:
    check("spend 静态边界：扣后=冻结额允许 / 再扣 1 拒绝",
          bal == 300 and fresh_balance(uid4) == 300, (bal, fresh_balance(uid4)))

# ===== P1-3：CLICKED 不再发奖 / FIRST_ORDER(2) 仍发 =====

refA = User(email="refa@glowmag.com", password_hash=hash_password("x"), name="RefA", points=0)
guest = User(email="guest@glowmag.com", password_hash=hash_password("x"), name="Guest", points=0)
s.add_all([refA, guest])
s.commit()
s.add(Referral(code=derive_code(refA.id), referrer_user_id=refA.id,
               invited_email="guest@glowmag.com", invited_user_id=None,
               status=int(ReferralStatus.CLICKED)))
oc = make_order(s, "NSEXTCLK01", user_id=guest.id, email="guest@glowmag.com")
s.commit()
on_order_paid(s, oc)
s.commit()
s.expire_all()
clk = s.query(Referral).filter(Referral.invited_email == "guest@glowmag.com").one()
led_refA = s.execute(text(
    "SELECT COUNT(*) FROM points_ledger WHERE user_id=:u AND reason=5"),
    {"u": refA.id}).scalar()
check("P1-3 CLICKED 行支付不发奖（防冒领）：状态不动且无 REFERRAL 流水",
      clk.status == int(ReferralStatus.CLICKED) and led_refA == 0,
      (clk.status, led_refA))

s.add(Referral(code=derive_code(refA.id) + "X", referrer_user_id=refA.id,
               invited_email="guest2@glowmag.com", invited_user_id=guest.id,
               status=int(ReferralStatus.FIRST_ORDER)))
oc2 = make_order(s, "NSEXTCLK02", user_id=guest.id, email="guest2@glowmag.com")
s.commit()
on_order_paid(s, oc2)
s.commit()
s.expire_all()
row2 = s.query(Referral).filter(Referral.invited_email == "guest2@glowmag.com").one()
led_refA2 = s.execute(text(
    "SELECT COUNT(*) FROM points_ledger WHERE user_id=:u AND reason=5"),
    {"u": refA.id}).scalar()
check("P1-3 FIRST_ORDER(2) 行仍发奖 → status=3",
      row2.status == int(ReferralStatus.REWARDED) and led_refA2 == 1,
      (row2.status, led_refA2))

# ===== P1-4：pwreset token 一次性 =====

pwu = User(email="pwext@glowmag.com", password_hash=hash_password("oldpass88"), name="PW")
s.add(pwu)
s.commit()
now = int(time.time())
tok = pyjwt.encode({"sub": str(pwu.id), "purpose": "pwreset", "iat": now, "exp": now + 900},
                   app_settings.jwt_secret, algorithm="HS256")
body = PasswordResetConfirmIn(email="pwext@glowmag.com", token=tok,
                              new_password="newpass889")
service_account.password_reset_confirm(s, body)
s.commit()
check("P1-4 pwreset 首次 confirm 成功", True)
try:
    service_account.password_reset_confirm(s, body)
    check("P1-4 同 token 二次 confirm → 400（一次性）", False, "no exception")
except HTTPException as e:
    check("P1-4 同 token 二次 confirm → 400（一次性）",
          e.status_code == 400, e.status_code)
# 改密后，改密前签发的旧 token 同样作废
tok_old = pyjwt.encode({"sub": str(pwu.id), "purpose": "pwreset", "iat": now - 10,
                        "exp": now + 900}, app_settings.jwt_secret, algorithm="HS256")
try:
    service_account.password_reset_confirm(s, PasswordResetConfirmIn(
        email="pwext@glowmag.com", token=tok_old, new_password="hacked998"))
    check("P1-4 改密后旧 token → 400", False, "no exception")
except HTTPException as e:
    check("P1-4 改密后旧 token → 400", e.status_code == 400, e.status_code)
# 改密之后新签发的 token 有效（pwd_changed_at 不误伤）：跨过改密秒再签发
s.expire_all()
pw_now = s.get(User, pwu.id).pwd_changed_at
time.sleep(1.2)
tok_new = pyjwt.encode(
    {"sub": str(pwu.id), "purpose": "pwreset",
     "iat": int(time.time()), "exp": int(time.time()) + 900},
    app_settings.jwt_secret, algorithm="HS256")
service_account.password_reset_confirm(s, PasswordResetConfirmIn(
    email="pwext@glowmag.com", token=tok_new, new_password="again8899"))
s.commit()
check("P1-4 改密后新签发 token 仍有效", True)

s.close()

# ===== HTTP 层：P1-5 / P1-6 / P1-9 =====

with TestClient(app) as client:
    s = SessionLocal()
    hu = User(email="hu@glowmag.com", password_hash=hash_password("x"), name="HU")
    s.add(hu)
    s.commit()
    H = {"Authorization": f"Bearer {create_token(hu.id, 0)}"}

    r = client.post("/api/subscriptions", headers=H, json={"plan": 1, "style_mode": 1})
    check("P1-5 首次创建订阅 201", r.status_code == 201, r.text)
    r2 = client.post("/api/subscriptions", headers=H, json={"plan": 2, "style_mode": 1})
    check("P1-5 已有生效订阅再创建 → 409 subscription_exists",
          r2.status_code == 409 and r2.json().get("detail") == "subscription_exists", r2.text)
    sid = r.json()["id"]
    client.post(f"/api/subscriptions/{sid}/cancel", headers=H, json={})
    r3 = client.post("/api/subscriptions", headers=H, json={"plan": 3, "style_mode": 2})
    check("P1-5 取消后可再创建 201", r3.status_code == 201, r3.text)
    sid = r3.json()["id"]

    past = (utcnow() - timedelta(days=3)).isoformat()
    fut = (utcnow() + timedelta(days=30)).isoformat()
    r = client.post(f"/api/subscriptions/{sid}/pause", headers=H,
                    json={"resume_at": past})
    check("P1-6 pause resume_at 过去 → 422", r.status_code == 422, r.text)
    r = client.post(f"/api/subscriptions/{sid}/pause", headers=H,
                    json={"resume_at": fut})
    check("P1-6 pause resume_at 未来 → 200", r.status_code == 200, r.text)
    client.post(f"/api/subscriptions/{sid}/resume", headers=H)  # 复原生效态供 skip 用
    r = client.post(f"/api/subscriptions/{sid}/skip", headers=H,
                    json={"skip_until": past})
    check("P1-6 skip_until 过去 → 422", r.status_code == 422, r.text)
    r = client.post(f"/api/subscriptions/{sid}/skip", headers=H,
                    json={"skip_until": fut})
    check("P1-6 skip_until 未来 → 200", r.status_code == 200, r.text)

    r = client.put("/api/account/me", headers=H, json={"name": "   "})
    check("P1-9 name 纯空白 → 422", r.status_code == 422, r.text)
    r = client.put("/api/account/me", headers=H, json={"name": "  Ann  "})
    check("P1-9 name strip 落库", r.status_code == 200 and r.json()["name"] == "Ann", r.text)
    r = client.put("/api/account/me", headers=H,
                   json={"birthday": (date.today() + timedelta(days=1)).isoformat()})
    check("P1-9 birthday 未来 → 422", r.status_code == 422, r.text)
    r = client.put("/api/account/me", headers=H, json={"birthday": "1900-01-01"})
    check("P1-9 birthday 超 120 岁 → 422", r.status_code == 422, r.text)
    r = client.put("/api/account/me", headers=H, json={"birthday": "2000-01-01"})
    check("P1-9 birthday 合法 → 200", r.status_code == 200, r.text)

    # ===== P1-7：check-then-insert 竞态撞唯一索引不 500 =====
    wp = Product(slug="ext-wish", title="Ext Wish", category_id=1, status=1,
                 price_min=1000, price_max=1000)
    s.add(wp)
    s.commit()
    s.add(WishlistItem(user_id=hu.id, product_id=wp.id))
    s.commit()
    real_gwi = repo.get_wishlist_item
    repo.get_wishlist_item = lambda db, u, p: None  # 模拟竞态：查时无行
    try:
        out, created = service_account.add_to_wishlist(s, hu, wp.id)
        check("P1-7 wishlist 竞态撞主键 → 幂等返回已存在（created=False）",
              out["ok"] is True and created is False, (out, created))
    finally:
        repo.get_wishlist_item = real_gwi
    s.expire_all()
    check("P1-7 wishlist 行仍唯一",
          s.query(WishlistItem).filter(WishlistItem.user_id == hu.id).count() == 1)

    s.add(EmailPreference(email="race@glowmag.com", user_id=hu.id, source="seed",
                          sub_promo=1))
    s.commit()
    s.add(NewsletterSubscriber(email="race@glowmag.com", source="seed"))
    s.commit()
    real_gns = repo.get_newsletter_subscriber
    real_gep = repo.get_email_preference
    calls = {"n": 0}

    def fake_gep(db, email):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_gep(db, email)

    repo.get_newsletter_subscriber = lambda db, email: None
    repo.get_email_preference = fake_gep
    try:
        out = service_account.newsletter(s, None, NewsletterIn(
            email="race@glowmag.com", source="race"))
        s.expire_all()
        pref = s.get(EmailPreference, "race@glowmag.com")
        check("P1-7 newsletter 竞态 → 幂等 200 且行被置全 1 / 仍一行",
              out["ok"] is True and pref is not None and pref.sub_promo == 1
              and s.query(NewsletterSubscriber).filter(
                  NewsletterSubscriber.email == "race@glowmag.com").count() == 1,
              (out, pref and pref.sub_promo))
    finally:
        repo.get_newsletter_subscriber = real_gns
        repo.get_email_preference = real_gep

    # unsubscribe 竞态：首查 None（行已存在）→ 插入撞主键 → 重查走置 0 路径
    calls2 = {"n": 0}

    def fake_gep2(db, email):
        calls2["n"] += 1
        return None if calls2["n"] == 1 else real_gep(db, email)

    s.add(EmailPreference(email="unsub@glowmag.com", sub_promo=1, sub_new_arrival=1,
                          sub_cart_abandon=1))
    s.commit()
    us_tok = "us_" + hmac.new(app_settings.jwt_secret.encode(),
                              b"unsub@glowmag.com", hashlib.sha256).hexdigest()[:16]
    repo.get_email_preference = fake_gep2
    try:
        out = service_account.unsubscribe(s, None, UnsubscribeIn(
            email="unsub@glowmag.com", token=us_tok))
        s.expire_all()
        pref = s.get(EmailPreference, "unsub@glowmag.com")
        check("P1-7 unsubscribe 竞态 → 幂等 200 且三开关置 0",
              out["ok"] is True and pref.sub_promo == 0
              and pref.unsubscribed_at is not None, (out, pref and pref.sub_promo))
    finally:
        repo.get_email_preference = real_gep

    # ===== P2-10：推荐码缓存未命中重建（新用户码立即可见） =====
    ua = User(email="cache-a@glowmag.com", password_hash=hash_password("x"), name="CA")
    s.add(ua)
    s.commit()
    # 先用无效码触发快照构建（此时 cache-b 尚未注册）
    service_referrals.bind_referral_on_register(
        s, "GLOW-DEADBEEF", User(id=999999, email="x@x.com"))
    ub = User(email="cache-b@glowmag.com", password_hash=hash_password("x"), name="CB")
    s.add(ub)
    s.commit()
    # uc 以 ub 的码注册：缓存未命中须强制重建，绑定成功
    service_referrals.bind_referral_on_register(
        s, derive_code(ub.id), User(email="cache-c@glowmag.com"))
    s.commit()
    row = (s.query(Referral)
           .filter(Referral.invited_email == "cache-c@glowmag.com").one_or_none())
    check("P2-10 缓存 TTL 内新注册用户的码未命中 → 重建可见并建 REGISTERED 绑定",
          row is not None and row.referrer_user_id == ub.id
          and row.status == int(ReferralStatus.REGISTERED),
          (row and row.referrer_user_id, ub.id))

    # ===== P2-11：export 批查仍含 items/messages =====
    ex_u = User(email="export@glowmag.com", password_hash=hash_password("x"),
                name="EX", points=0)
    s.add(ex_u)
    s.flush()
    eo = Order(order_no="NSEXPEXP01", user_id=ex_u.id, email="export@glowmag.com",
               status=1, subtotal=3000, grand_total=3000, shipping_address=ADDR)
    s.add(eo)
    s.flush()
    s.add_all([
        OrderItem(order_id=eo.id, variant_id=1, product_slug="a", title_snapshot="A",
                  qty=1, unit_price=1500, subtotal=1500),
        OrderItem(order_id=eo.id, variant_id=2, product_slug="b", title_snapshot="B",
                  qty=1, unit_price=1500, subtotal=1500),
    ])
    tk = Ticket(ticket_no="TKEXTP0001", user_id=ex_u.id, email="export@glowmag.com",
                category=1, priority=1, subject="s")
    s.add(tk)
    s.flush()
    s.add(TicketMessage(ticket_id=tk.id, sender=1, content="hello"))
    s.commit()
    data = service_account.export_my_data(s, ex_u)
    check("P2-11 export 订单 items 批查齐（2 条）",
          len(data["orders"]) == 1 and len(data["orders"][0]["items"]) == 2, data["orders"])
    check("P2-11 export 工单 messages 批查齐（1 条）",
          len(data["tickets"]) == 1 and len(data["tickets"][0]["messages"]) == 1)

    # ===== P1-8：GDPR 匿名化（积分流水 + PII 残留） =====
    refA_id = (s.query(User.id)
               .filter(User.email == "refa@glowmag.com").one())[0]
    gd = User(email="gdpr-ext@glowmag.com", password_hash=hash_password("x"),
              name="GD", points=0)
    s.add(gd)
    s.commit()
    # 生产口径：余额须有台账背书（SUM(change)==points），先经原语+流水入 300 分
    bal = points_svc.add_points(s, gd.id, 300)
    s.add(PointsLedger(user_id=gd.id, change=300,
                       reason=int(PointsReason.ADMIN_ADJUST), balance_after=bal,
                       ref_type="admin", ref_id=0, created_at=utcnow()))
    s.commit()
    gd_ref = Referral(code="GLOW-EXTGDPR", referrer_user_id=refA_id,
                      invited_email="gdpr-ext@glowmag.com", invited_user_id=gd.id,
                      status=int(ReferralStatus.REGISTERED))
    s.add(gd_ref)
    s.add(EmailPreference(email="gdpr-ext@glowmag.com", user_id=gd.id, source="x",
                          sub_promo=1))
    s.commit()
    gd_uid, ref_id = gd.id, gd_ref.id
    ok = service_account.anonymize_user(s, gd_uid)
    s.commit()
    s.expire_all()
    g2 = s.get(User, gd_uid)
    led_gd = s.execute(text(
        "SELECT change, balance_after, reason, ref_type FROM points_ledger"
        " WHERE user_id=:u AND reason=11"), {"u": gd_uid}).fetchall()
    led_sum = s.execute(text(
        "SELECT COALESCE(SUM(change),0) FROM points_ledger WHERE user_id=:u"),
        {"u": gd_uid}).scalar()
    gdpr_rows = [r for r in led_gd if r[3] == "gdpr"]
    pref_left = (s.query(EmailPreference)
                 .filter((EmailPreference.email == "gdpr-ext@glowmag.com")
                         | (EmailPreference.user_id == gd_uid)).count())
    ref_row = s.get(Referral, ref_id)
    check("P1-8 匿名化：points=0 + ADMIN_ADJUST 清零流水（ref=gdpr）+ 对账为平",
          ok is True and g2.points == 0 and len(gdpr_rows) == 1
          and gdpr_rows[0][0] == -300 and gdpr_rows[0][1] == 0
          and int(led_sum) == 0,
          (g2.points, led_gd))
    check("P1-8 匿名化：EmailPreference 删除 + Referral.invited_email 脱敏",
          pref_left == 0 and ref_row.invited_email == f"deleted+{ref_id}@anonymized.local",
          (pref_left, ref_row.invited_email))

    s.close()

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
