"""智能体 B 自测 —— 推荐/订阅/礼品卡/退订/密码重置（GM_DB=sqlite 独立库 + BigInteger 垫片同 test_payments）"""

import hashlib
import hmac
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_r.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

import jwt as pyjwt
from fastapi.testclient import TestClient

from app.core.db import SessionLocal, utcnow
from app.core.enums import PointsReason, ReferralStatus
from app.core.security import create_token, hash_password
from app.main import app
from app.models import (
    EmailPreference, GiftCard, GiftCardLedger, Order, OrderTimeline, Payment,
    PointsLedger, Referral, Subscription, User,
)
from app.services import emails
from app.services.referrals import derive_code, on_order_paid

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


def make_order(s, no, *, user_id, email, total=3000):
    o = Order(order_no=no, user_id=user_id, email=email, status=0,
              subtotal=total, grand_total=total, shipping_address=ADDR)
    s.add(o)
    s.flush()
    return o


class _Cap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


with TestClient(app) as client:
    s = SessionLocal()

    rita = User(email="rita@glowmag.com", password_hash=hash_password("x"), name="Rita", points=0)
    ivy = User(email="ivy@glowmag.com", password_hash=hash_password("x"), name="Ivy", points=0)
    sam = User(email="sam@glowmag.com", password_hash=hash_password("x"), name="Sam", points=0)
    nia = User(email="nia@glowmag.com", password_hash=hash_password("x"), name="Nia", points=0)
    tina = User(email="tina@glowmag.com", password_hash=hash_password("x"), name="Tina", points=0)
    pwu = User(email="pw@glowmag.com", password_hash=hash_password("oldpassword8"), name="PW", points=0)
    s.add_all([rita, ivy, sam, nia, tina, pwu])
    s.commit()

    H_rita = {"Authorization": f"Bearer {create_token(rita.id, 0)}"}
    H_tina = {"Authorization": f"Bearer {create_token(tina.id, 0)}"}
    expected_code = "GLOW-" + hashlib.sha256(
        f"{rita.id}:{app_settings.jwt_secret}".encode()).hexdigest()[:8].upper()

    # ===== referrals：code 派生 / me =====
    r1 = client.get("/api/referrals/me", headers=H_rita).json()
    r2 = client.get("/api/referrals/me", headers=H_rita).json()
    check("referrals code 确定性派生 + 两次一致",
          r1["code"] == expected_code and r2["code"] == expected_code
          and re.fullmatch(r"GLOW-[0-9A-F]{8}", r1["code"]), r1)
    check("referrals me 空数据 stats",
          r1["invited"] == [] and r1["stats"] == {"invited": 0, "rewarded": 0, "points_earned": 0},
          r1["stats"])

    r = client.post("/api/referrals/simulate-invite", headers=H_rita,
                    json={"email": "ivy@glowmag.com"})
    check("simulate-invite 已注册邮箱 → 409（不允许直接置 REGISTERED）",
          r.status_code == 409, r.text)
    # ivy 已注册：绑定关系改由注册流/直插建立（等价 bind_referral_on_register 的产物）
    s.add(Referral(code=expected_code, referrer_user_id=rita.id,
                   invited_email="ivy@glowmag.com", invited_user_id=ivy.id,
                   status=int(ReferralStatus.REGISTERED)))
    s.commit()
    ref1 = s.query(Referral).filter(Referral.referrer_user_id == rita.id).one()
    check("预置 REGISTERED 绑定行 + code 同派生码",
          ref1.status == int(ReferralStatus.REGISTERED)
          and ref1.invited_email == "ivy@glowmag.com"
          and ref1.invited_user_id == ivy.id and ref1.code == expected_code,
          (ref1.status, ref1.invited_user_id))

    r = client.post("/api/referrals/simulate-invite", headers=H_rita,
                    json={"email": "ivy@glowmag.com"})
    check("simulate-invite 同 email 重复 → 409", r.status_code == 409, r.text)

    # ===== simulate-invite 收紧后的合法路径：未注册邮箱建 CLICKED 行 =====
    r = client.post("/api/referrals/simulate-invite", headers=H_tina,
                    json={"email": "fresh@glowmag.com"})
    tina_ref = s.query(Referral).filter(Referral.referrer_user_id == tina.id).one()
    check("simulate-invite 未注册邮箱 → 201 建 CLICKED 行（invited_user_id 空）",
          r.status_code == 201 and r.json()["code"] == derive_code(tina.id)
          and tina_ref.status == int(ReferralStatus.CLICKED)
          and tina_ref.invited_user_id is None,
          (r.status_code, tina_ref.status))
    r = client.post("/api/referrals/simulate-invite", headers=H_tina,
                    json={"email": "fresh@glowmag.com"})
    check("simulate-invite 未注册但重复 → 409 already invited", r.status_code == 409, r.text)
    r = client.post("/api/referrals/simulate-invite", headers=H_tina,
                    json={"email": "ivy@glowmag.com"})
    check("simulate-invite 已注册邮箱（tina 视角）→ 409", r.status_code == 409, r.text)

    r3 = client.get("/api/referrals/me", headers=H_rita).json()
    check("me invited 列表：email 脱敏 + status_text 中文 + stats",
          len(r3["invited"]) == 1 and r3["invited"][0]["email_masked"] == "i***y@glowmag.com"
          and r3["invited"][0]["status_text"] == "已注册"
          and r3["stats"] == {"invited": 1, "rewarded": 0, "points_earned": 0}, r3)

    # ===== on_order_paid：奖励发放 =====
    o1 = make_order(s, "NS260816R01", user_id=ivy.id, email="ivy@glowmag.com")
    s.commit()
    on_order_paid(s, o1)
    s.commit()
    s.expire_all()
    ref1 = s.query(Referral).filter(Referral.referrer_user_id == rita.id).one()
    led_rita = s.query(PointsLedger).filter(
        PointsLedger.user_id == rita.id, PointsLedger.reason == int(PointsReason.REFERRAL)).all()
    led_ivy = s.query(PointsLedger).filter(
        PointsLedger.user_id == ivy.id, PointsLedger.reason == int(PointsReason.REFERRAL)).all()
    check("on_order_paid referrer +1000（ledger reason=5 ref_type=referral balance_after 正确）",
          s.get(User, rita.id).points == 1000 and len(led_rita) == 1
          and led_rita[0].change == 1000 and led_rita[0].balance_after == 1000
          and led_rita[0].ref_type == "referral" and led_rita[0].ref_id == o1.id,
          (s.get(User, rita.id).points, [(l.change, l.balance_after) for l in led_rita]))
    check("on_order_paid invitee 已注册 +1000",
          s.get(User, ivy.id).points == 1000 and len(led_ivy) == 1
          and led_ivy[0].change == 1000 and led_ivy[0].balance_after == 1000,
          (s.get(User, ivy.id).points,))
    check("on_order_paid → status=3 + rewarded_at + first_order_no + timeline points_granted",
          ref1.status == 3 and ref1.rewarded_at is not None
          and ref1.first_order_no == "NS260816R01"
          and s.query(OrderTimeline).filter(
              OrderTimeline.order_id == o1.id,
              OrderTimeline.event == "points_granted").count() == 1,
          (ref1.status, ref1.first_order_no))

    on_order_paid(s, o1)
    s.commit()
    s.expire_all()
    check("status=3 后重复触发不重复奖励（幂等）",
          s.get(User, rita.id).points == 1000
          and s.query(PointsLedger).filter(
              PointsLedger.user_id == rita.id,
              PointsLedger.reason == int(PointsReason.REFERRAL)).count() == 1,
          s.get(User, rita.id).points)

    s.add(Referral(code=derive_code(sam.id), referrer_user_id=sam.id,
                   invited_email="sam@glowmag.com", status=1))
    o2 = make_order(s, "NS260816R02", user_id=sam.id, email="sam@glowmag.com")
    s.commit()
    on_order_paid(s, o2)
    s.commit()
    s.expire_all()
    self_ref = s.query(Referral).filter(Referral.referrer_user_id == sam.id).one()
    check("防自邀：referrer==下单人 → status=4 无效且不发分",
          self_ref.status == 4 and s.get(User, sam.id).points == 0
          and s.query(PointsLedger).filter(
              PointsLedger.user_id == sam.id,
              PointsLedger.reason == int(PointsReason.REFERRAL)).count() == 0,
          (self_ref.status, s.get(User, sam.id).points))

    # ===== 端到端：绑定（等价 /register?ref= 注册流）→ mock-pay → 钩子自动奖励 =====
    s.add(Referral(code=expected_code, referrer_user_id=rita.id,
                   invited_email="nia@glowmag.com", invited_user_id=nia.id,
                   status=int(ReferralStatus.REGISTERED)))
    s.commit()
    o3 = make_order(s, "NS260816R03", user_id=nia.id, email="nia@glowmag.com")
    s.commit()
    client.post("/api/payments/create-intent", json={"order_no": "NS260816R03"})
    r = client.post("/api/payments/mock-pay",
                    json={"order_no": "NS260816R03", "succeed": True})
    s.expire_all()
    nia_ref_ledger = s.query(PointsLedger).filter(
        PointsLedger.user_id == nia.id, PointsLedger.reason == int(PointsReason.REFERRAL)).all()
    check("端到端 mock-pay → 钩子自动奖励：referrer 累计 2000 / invitee 1000(另有下单 300 冻结)",
          r.status_code == 200 and s.get(User, rita.id).points == 2000
          and s.get(User, nia.id).points == 1300
          and len(nia_ref_ledger) == 1 and nia_ref_ledger[0].change == 1000
          and s.query(Referral).filter(Referral.invited_email == "nia@glowmag.com").one().status == 3
          and s.query(OrderTimeline).filter(
              OrderTimeline.order_id == o3.id,
              OrderTimeline.event == "points_granted").count() == 1,
          (r.status_code, s.get(User, rita.id).points, s.get(User, nia.id).points))
    r4 = client.get("/api/referrals/me", headers=H_rita).json()
    check("me stats 汇总：invited 2 / rewarded 2 / points_earned 2000",
          r4["stats"] == {"invited": 2, "rewarded": 2, "points_earned": 2000}, r4["stats"])

    # ===== /register?ref= 绑定闭环：RegisterIn.ref_code → REGISTERED 绑定行 =====
    r = client.post("/api/account/register", json={
        "email": "zoe@glowmag.com", "password": "zoepass123", "name": "Zoe",
        "ref_code": expected_code})
    zoe = s.query(User).filter(User.email == "zoe@glowmag.com").one()
    zoe_ref = s.query(Referral).filter(Referral.invited_email == "zoe@glowmag.com").one()
    check("注册带 ref_code → 建 REGISTERED 绑定（referrer=rita / invited_user_id 回填）",
          r.status_code == 201 and zoe_ref.referrer_user_id == rita.id
          and zoe_ref.status == int(ReferralStatus.REGISTERED)
          and zoe_ref.invited_user_id == zoe.id and zoe_ref.code == expected_code,
          (r.status_code, zoe_ref.status, zoe_ref.invited_user_id))
    # CLICKED 预登记（simulate-invite）+ 注册带码 → 流转为 REGISTERED 并回填
    client.post("/api/referrals/simulate-invite", headers=H_rita,
                json={"email": "kai@glowmag.com"})
    r = client.post("/api/account/register", json={
        "email": "kai@glowmag.com", "password": "kaipass123", "name": "Kai",
        "ref_code": expected_code})
    kai = s.query(User).filter(User.email == "kai@glowmag.com").one()
    kai_ref = s.query(Referral).filter(Referral.invited_email == "kai@glowmag.com").one()
    check("CLICKED 预登记 + 注册带码 → 升级 REGISTERED + invited_user_id 回填",
          r.status_code == 201 and kai_ref.status == int(ReferralStatus.REGISTERED)
          and kai_ref.invited_user_id == kai.id, (r.status_code, kai_ref.status))
    # 无效码 / 自身码：注册不受影响，不建行
    r = client.post("/api/account/register", json={
        "email": "rex@glowmag.com", "password": "rexpass123", "name": "Rex",
        "ref_code": "GLOW-DEADBEEF"})
    check("无效 ref_code → 注册正常 201 且不建绑定行",
          r.status_code == 201 and s.query(Referral).filter(
              Referral.invited_email == "rex@glowmag.com").count() == 0, r.status_code)
    # 被邀人首单支付 → 发放闭环验证（绑定行写对即钩子可用）
    o4 = make_order(s, "NS260816R04", user_id=zoe.id, email="zoe@glowmag.com")
    s.commit()
    on_order_paid(s, o4)
    s.commit()
    s.expire_all()
    check("zoe 首单支付 → 双方各 +1000（绑定闭环真实发放）",
          s.get(User, rita.id).points == 3000 and s.get(User, zoe.id).points == 1000
          and s.query(Referral).filter(
              Referral.invited_email == "zoe@glowmag.com").one().status == 3,
          (s.get(User, rita.id).points, s.get(User, zoe.id).points))

    # ===== subscriptions：计划常量 + 全状态机 =====
    me = client.get("/api/subscriptions/me", headers=H_rita).json()
    check("GET /subscriptions/me plans 常量（1=4周1299 / 2=6周1399 / 3=8周1499）",
          me["plans"] == [
              {"id": 1, "weeks": 4, "price_cents": 1299},
              {"id": 2, "weeks": 6, "price_cents": 1399},
              {"id": 3, "weeks": 8, "price_cents": 1499}] and me["items"] == [], me["plans"])

    r = client.post("/api/subscriptions", headers=H_rita, json={"plan": 1, "style_mode": 2})
    d = r.json()
    nb = datetime.fromisoformat(d["next_billing_at"])
    check("创建订阅 status=1 + SUBMOCK id + next_billing=now+4周 + plan_text",
          r.status_code == 201 and d["status"] == 1 and d["status_text"] == "生效中"
          and d["plan_text"] == "每4周" and d["style_mode"] == 2
          and re.fullmatch(r"SUBMOCK[0-9a-f]{12}", d["stripe_subscription_id"])
          and abs((nb - (utcnow() + timedelta(weeks=4))).total_seconds()) < 600,
          (r.status_code, d["stripe_subscription_id"], d["next_billing_at"]))
    sid = d["id"]

    check("非法 plan/style_mode → 422",
          client.post("/api/subscriptions", headers=H_rita,
                      json={"plan": 4, "style_mode": 1}).status_code == 422
          and client.post("/api/subscriptions", headers=H_rita,
                          json={"plan": 1, "style_mode": 3}).status_code == 422)

    resume_at = utcnow() + timedelta(days=30)
    r = client.post(f"/api/subscriptions/{sid}/pause", headers=H_rita,
                    json={"resume_at": resume_at.isoformat()})
    d = r.json()
    check("pause → status=2 + resume_at 存储",
          r.status_code == 200 and d["status"] == 2 and d["status_text"] == "已暂停"
          and d["resume_at"] is not None, d)
    check("非 active 再 pause → 409",
          client.post(f"/api/subscriptions/{sid}/pause", headers=H_rita,
                      json={}).status_code == 409)

    r = client.post(f"/api/subscriptions/{sid}/resume", headers=H_rita)
    d = r.json()
    check("resume（next_billing 未过期）→ status=1 且 next_billing 保持原值",
          r.status_code == 200 and d["status"] == 1
          and d["next_billing_at"] == nb.isoformat(), d)

    sub = s.get(Subscription, sid)
    sub.next_billing_at = utcnow() - timedelta(days=1)
    s.commit()
    client.post(f"/api/subscriptions/{sid}/pause", headers=H_rita, json={})
    r = client.post(f"/api/subscriptions/{sid}/resume", headers=H_rita)
    nb2 = datetime.fromisoformat(r.json()["next_billing_at"])
    check("resume（next_billing 已过期）→ 续期 now+4周",
          r.status_code == 200 and r.json()["status"] == 1
          and abs((nb2 - (utcnow() + timedelta(weeks=4))).total_seconds()) < 600,
          r.json()["next_billing_at"])

    skip_until = utcnow() + timedelta(weeks=8)
    r = client.post(f"/api/subscriptions/{sid}/skip", headers=H_rita,
                    json={"skip_until": skip_until.isoformat()})
    s.expire_all()
    check("skip → status 保持 1 + skip_until 记录",
          r.status_code == 200 and r.json()["status"] == 1
          and r.json()["skip_until"] is not None
          and s.get(Subscription, sid).skip_until is not None, r.json())

    r = client.post(f"/api/subscriptions/{sid}/cancel", headers=H_rita,
                    json={"cancel_reason": 3})
    s.expire_all()
    check("cancel → status=5 + cancel_reason",
          r.status_code == 200 and r.json()["status"] == 5
          and r.json()["status_text"] == "已取消"
          and s.get(Subscription, sid).cancel_reason == 3, r.json())
    check("已取消再操作 → 409",
          client.post(f"/api/subscriptions/{sid}/pause", headers=H_rita,
                      json={}).status_code == 409)
    check("归属校验：他人订阅 → 404 / 不存在 → 404",
          client.post(f"/api/subscriptions/{sid}/pause", headers=H_tina,
                      json={}).status_code == 404
          and client.post("/api/subscriptions/99999/pause", headers=H_rita,
                          json={}).status_code == 404)
    tina_me = client.get("/api/subscriptions/me", headers=H_tina).json()
    check("订阅按用户隔离：tina 无订阅",
          tina_me["items"] == [], tina_me)

    # ===== unsubscribe =====
    r = client.post("/api/account/unsubscribe", json={"email": "mkt@glowmag.com"})
    pref = s.get(EmailPreference, "mkt@glowmag.com")
    check("unsubscribe 无 token 且未登录 → 400 token_required（收紧宽限）",
          r.status_code == 400 and pref is None,
          (r.status_code, r.text[:60]))

    r = client.post("/api/account/unsubscribe",
                    json={"email": "bad@glowmag.com", "token": "us_wrongtoken00000"})
    check("unsubscribe 错 token → 400 且不落行",
          r.status_code == 400 and s.get(EmailPreference, "bad@glowmag.com") is None, r.text)

    good_token = "us_" + hmac.new(
        app_settings.jwt_secret.encode(), b"tok@glowmag.com", hashlib.sha256
    ).hexdigest()[:16]
    r = client.post("/api/account/unsubscribe",
                    json={"email": "tok@glowmag.com", "token": good_token})
    check("unsubscribe 正确 token → ok",
          r.status_code == 200 and s.get(EmailPreference, "tok@glowmag.com").sub_promo == 0,
          r.text)

    s.add(EmailPreference(email="dup@glowmag.com", sub_promo=1, sub_new_arrival=1,
                          sub_cart_abandon=1))
    s.commit()
    dup_token = "us_" + hmac.new(
        app_settings.jwt_secret.encode(), b"dup@glowmag.com", hashlib.sha256
    ).hexdigest()[:16]
    client.post("/api/account/unsubscribe",
                json={"email": "dup@glowmag.com", "token": dup_token})
    rows = s.query(EmailPreference).filter(EmailPreference.email == "dup@glowmag.com").all()
    check("unsubscribe upsert：已有偏好被置 0 且仍只一行",
          len(rows) == 1 and rows[0].sub_promo == 0 and rows[0].sub_new_arrival == 0
          and rows[0].sub_cart_abandon == 0 and rows[0].unsubscribed_at is not None,
          len(rows))

    # ===== password reset =====
    cap = _Cap()
    emails.log.setLevel(logging.INFO)
    emails.log.addHandler(cap)
    r = client.post("/api/account/password-reset/request",
                    json={"email": "nobody@glowmag.com"})
    nobody_mails = [m for m in cap.msgs if "nobody@glowmag.com" in m]
    check("pwreset request 不存在邮箱 → 恒 200 且不发邮件",
          r.status_code == 200 and r.json() == {"ok": True} and nobody_mails == [],
          (r.status_code, len(nobody_mails)))

    r = client.post("/api/account/password-reset/request",
                    json={"email": "pw@glowmag.com"})
    pw_mails = [m for m in cap.msgs if "to=pw@glowmag.com" in m]
    m_token = re.search(r"reset-password\?token=([A-Za-z0-9_\-\.]+)",
                        "".join(pw_mails)).group(1)
    check("pwreset request 存在用户 → 200 + 重置邮件含 15min token",
          r.status_code == 200 and len(pw_mails) == 1
          and pyjwt.decode(m_token, app_settings.jwt_secret,
                           algorithms=["HS256"])["purpose"] == "pwreset",
          len(pw_mails))
    emails.log.removeHandler(cap)

    check("pwreset confirm 坏 token → 400",
          client.post("/api/account/password-reset/confirm", json={
              "email": "pw@glowmag.com", "token": "not.a.jwt",
              "new_password": "newpassword9"}).status_code == 400)
    exp_token = pyjwt.encode(
        {"sub": str(pwu.id), "purpose": "pwreset",
         "iat": int(time.time()) - 3600, "exp": int(time.time()) - 1800},
        app_settings.jwt_secret, algorithm="HS256")
    check("pwreset confirm 过期 token → 400",
          client.post("/api/account/password-reset/confirm", json={
              "email": "pw@glowmag.com", "token": exp_token,
              "new_password": "newpassword9"}).status_code == 400)
    check("pwreset confirm token 与 email 不匹配 → 400 / 短密码 → 422",
          client.post("/api/account/password-reset/confirm", json={
              "email": "rita@glowmag.com", "token": m_token,
              "new_password": "newpassword9"}).status_code == 400
          and client.post("/api/account/password-reset/confirm", json={
              "email": "pw@glowmag.com", "token": m_token,
              "new_password": "short"}).status_code == 422)

    r = client.post("/api/account/password-reset/confirm", json={
        "email": "pw@glowmag.com", "token": m_token, "new_password": "newpassword9"})
    login_old = client.post("/api/account/login",
                            json={"email": "pw@glowmag.com", "password": "oldpassword8"})
    login_new = client.post("/api/account/login",
                            json={"email": "pw@glowmag.com", "password": "newpassword9"})
    check("pwreset confirm 成功 → 旧密码 401 / 新密码可登录",
          r.status_code == 200 and login_old.status_code == 401
          and login_new.status_code == 200, (r.status_code, login_old.status_code,
                                             login_new.status_code))

    # ===== giftcard purchase =====
    check("giftcard 非法面额 3000 → 422",
          client.post("/api/promo/giftcard/purchase", json={
              "amount_cents": 3000, "purchaser_email": "buy@glowmag.com"
          }).status_code == 422)

    r = client.post("/api/promo/giftcard/purchase", json={
        "amount_cents": 5000, "purchaser_email": "buy@glowmag.com",
        "recipient_email": "friend@glowmag.com", "message": "glow on"})
    d = r.json()
    gc_order = d["order_no"]
    card = s.query(GiftCard).filter(GiftCard.code == d["code"]).one()
    check("purchase → status=0 待激活 + 关联待付订单（堵免费铸造资损洞）",
          r.status_code == 201 and d["status"] == 0 and card.status == 0
          and card.purchaser_order_id is not None and gc_order.startswith("NS"), d)

    client.post("/api/payments/create-intent", json={"order_no": gc_order})
    client.post("/api/payments/mock-pay", json={"order_no": gc_order, "succeed": True})
    s.expire_all()
    card = s.query(GiftCard).filter(GiftCard.code == d["code"]).one()
    gledger = s.query(GiftCardLedger).filter(
        GiftCardLedger.gift_card_id == card.id).all()
    check("支付后激活 → code GC-XXXX 格式（去歧义字符） + status=1 + ledger change_type=1",
          re.fullmatch(r"GC(-[A-Z0-9]{4}){3}", d["code"])
          and not (set(d["code"]) & set("IO01")) and card.status == 1
          and card.initial_amount == 5000
          and card.recipient_email == "friend@glowmag.com"
          and len(gledger) == 1 and gledger[0].change_type == 1
          and gledger[0].amount == 5000 and gledger[0].balance_after == 5000,
          (card.status, [g.change_type for g in gledger]))

    check("激活后可被 /giftcard 查询余额 5000",
          client.post("/api/promo/giftcard", json={"code": d["code"]}).json()[
              "balance_cents"] == 5000)

    codes = set()
    for amt in (2500, 10000):
        rr = client.post("/api/promo/giftcard/purchase", json={
            "amount_cents": amt, "purchaser_email": "buy@glowmag.com"})
        codes.add(rr.json()["code"])
    codes.add(d["code"])
    check("giftcard 2500/10000 可购买且 code 互不相同",
          len(codes) == 3, len(codes))

    s.close()

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
