"""智能体 C 自测 —— 邮件偏好中心（细粒度退订/复订）（GM_DB=sqlite test_ep.sqlite + BigInteger 垫片同 test_refsub）"""

import os
import sys
from datetime import timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_ep.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "scripts"))  # worker.py 在 scripts/

from app.core.config import settings as app_settings

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient

from app.core.db import SessionLocal, utcnow
from app.core.security import create_token, hash_password
from app.domains.member.service_account import _unsubscribe_token
from app.main import app
from app.models import Cart, EmailPreference, OutboxEvent, User

import worker

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


with TestClient(app) as client:
    s = SessionLocal()

    maya = User(email="maya@glowmag.com", password_hash=hash_password("x"), name="Maya")
    s.add(maya)
    s.commit()
    H_maya = {"Authorization": f"Bearer {create_token(maya.id, 0)}"}

    # ===== 读取：登录默认态 / 鉴权矩阵 =====
    r = client.get("/api/account/email-preferences", headers=H_maya)
    d = r.json()
    check("登录 GET 无记录 → 默认全 1 + unsubscribed_at=None 且不落库",
          r.status_code == 200 and d == {"email": "maya@glowmag.com", "sub_promo": 1,
                                         "sub_new_arrival": 1, "sub_cart_abandon": 1,
                                         "unsubscribed_at": None}
          and s.get(EmailPreference, "maya@glowmag.com") is None, d)

    check("未登录无 token GET → 401",
          client.get("/api/account/email-preferences").status_code == 401)
    check("未登录无 token PUT → 401",
          client.put("/api/account/email-preferences",
                     json={"sub_promo": False}).status_code == 401)

    tok = _unsubscribe_token("pc@glowmag.com")
    r = client.get("/api/account/email-preferences",
                   params={"email": "pc@glowmag.com", "token": tok})
    check("?email+token GET 正确 token → 200 默认全 1",
          r.status_code == 200 and r.json()["sub_cart_abandon"] == 1
          and r.json()["unsubscribed_at"] is None, r.text)

    check("错 token GET → 400 / email 缺 token → 400",
          client.get("/api/account/email-preferences",
                     params={"email": "pc@glowmag.com", "token": "us_wrongtoken0000"}
                     ).status_code == 400
          and client.get("/api/account/email-preferences",
                         params={"email": "pc@glowmag.com"}).status_code == 400)
    check("错 token PUT → 400 且不落库",
          client.put("/api/account/email-preferences",
                     params={"email": "nope@glowmag.com", "token": "us_wrongtoken0000"},
                     json={"sub_promo": True}).status_code == 400
          and s.get(EmailPreference, "nope@glowmag.com") is None)

    # ===== 部分更新（token 流） =====
    r = client.put("/api/account/email-preferences",
                   params={"email": "pc@glowmag.com", "token": tok},
                   json={"sub_promo": False})
    d = r.json()
    row = s.get(EmailPreference, "pc@glowmag.com")
    check("PUT 单开关：只关 promo 其它不变 + 无记录先建 source=preference_center + 非全退不清 unsubscribed_at",
          r.status_code == 200 and d["sub_promo"] == 0 and d["sub_new_arrival"] == 1
          and d["sub_cart_abandon"] == 1 and d["unsubscribed_at"] is None
          and row is not None and row.source == "preference_center"
          and row.sub_promo == 0 and row.sub_new_arrival == 1, d)

    r = client.put("/api/account/email-preferences",
                   params={"email": "pc@glowmag.com", "token": tok},
                   json={"sub_new_arrival": False})
    d = r.json()
    check("部分更新不覆盖未传字段：关 new 后 promo 仍 0 / cart 仍 1",
          r.status_code == 200 and d["sub_promo"] == 0 and d["sub_new_arrival"] == 0
          and d["sub_cart_abandon"] == 1, d)

    r = client.put("/api/account/email-preferences",
                   params={"email": "pc@glowmag.com", "token": tok},
                   json={"sub_cart_abandon": False})
    d = r.json()
    check("三开关全 0 → unsubscribed_at 置位（等价全退）",
          r.status_code == 200 and d["sub_promo"] == 0 and d["sub_cart_abandon"] == 0
          and d["unsubscribed_at"] is not None, d)

    # ===== 复订语义：unsubscribe 全退 → PUT 开单开关 =====
    em, etok = "resub@glowmag.com", _unsubscribe_token("resub@glowmag.com")
    r = client.post("/api/account/unsubscribe", json={"email": em, "token": etok})
    pref = s.get(EmailPreference, em)
    check("前置：unsubscribe 全退语义未变 → 三开关 0 + unsubscribed_at 置位",
          r.status_code == 200 and pref.sub_promo == 0 and pref.sub_new_arrival == 0
          and pref.sub_cart_abandon == 0 and pref.unsubscribed_at is not None)

    r = client.put("/api/account/email-preferences",
                   params={"email": em, "token": etok},
                   json={"sub_promo": True})
    s.expire_all()
    pref = s.get(EmailPreference, em)
    check("复订语义：PUT 开 promo → unsubscribed_at 清空且其它开关不被连带打开",
          r.status_code == 200 and pref.unsubscribed_at is None and pref.sub_promo == 1
          and pref.sub_new_arrival == 0 and pref.sub_cart_abandon == 0,
          (pref.sub_promo, pref.sub_new_arrival, pref.sub_cart_abandon,
           pref.unsubscribed_at))

    # ===== 登录流 PUT + GET 读穿 =====
    r = client.put("/api/account/email-preferences", headers=H_maya,
                   json={"sub_cart_abandon": False})
    g = client.get("/api/account/email-preferences", headers=H_maya).json()
    row = s.get(EmailPreference, "maya@glowmag.com")
    check("登录 PUT 落库（user_id 回填）+ 登录 GET 读穿一致",
          r.status_code == 200 and r.json()["sub_cart_abandon"] == 0
          and g["sub_cart_abandon"] == 0 and g["sub_promo"] == 1
          and row is not None and row.user_id == maya.id, g)

    # ===== 偏好中心 ↔ worker 弃购合规联动 =====
    now = utcnow()
    old = now - timedelta(hours=2)
    s.add_all([
        Cart(session_id="ep-ok", email="cartok@glowmag.com",
             items=[{"variantId": 1, "qty": 2}], created_at=old, updated_at=old),
        Cart(session_id="ep-off", email="cartoff@glowmag.com",
             items=[{"variantId": 1, "qty": 1}], created_at=old, updated_at=old),
    ])
    s.commit()
    client.put("/api/account/email-preferences",
               params={"email": "cartoff@glowmag.com",
                       "token": _unsubscribe_token("cartoff@glowmag.com")},
               json={"sub_cart_abandon": False})
    worker.scan_abandoned_carts(s)
    ev_mails = [ev.payload.get("email") for ev in s.query(OutboxEvent)
                .filter(OutboxEvent.event_type == "cart.abandoned").all()]
    s.expire_all()
    check("worker 合规联动：偏好中心关 sub_cart_abandon → 弃购扫描跳过（验证现有 worker 行为）",
          "cartok@glowmag.com" in ev_mails and "cartoff@glowmag.com" not in ev_mails
          and s.query(Cart).filter(Cart.session_id == "ep-ok").one().abandoned_mails_sent == 1
          and s.query(Cart).filter(Cart.session_id == "ep-off").one().abandoned_mails_sent == 0,
          ev_mails)

    s.close()

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
