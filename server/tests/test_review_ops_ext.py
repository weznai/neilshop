"""评审修复扩展自测 —— settings LLM Key 掩码/写白名单 / 美甲师(role=4)越权收口 /
对账 resolve 死胡同出口 / 弹窗删除 / 礼品卡作废（负流水清零）/ 订阅 q 搜索 + skip_until /
看板 AOV paid 口径（gmv_cents/paid_count 同口径）。
（GM_DB=sqlite:///test_review_ops.sqlite 独立库，用完清理；BigInteger 垫片同
test_admin_queues_ext.py；直跑与 pytest 双兼容：main() 承载全部断言）"""

import os
import sys
from datetime import date, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_review_ops.sqlite").replace("\\", "/")


def _remove_db_files():
    for _suffix in ("", "-wal", "-shm"):
        _p = _DB + _suffix
        if os.path.exists(_p):
            os.remove(_p)


_remove_db_files()
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings  # noqa: E402

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, engine, utcnow  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    GiftCard, GiftCardLedger, Order, Payment, PopupConfig, ReconciliationDaily,
    Setting, Subscription, User,
)
from app.services.llm import mask_key  # noqa: E402

PASSED = 0
FAILED = []

ADDR = {"full_name": "T", "line1": "1 Main St", "city": "SF", "state": "CA",
        "zip": "94110", "country": "US"}

PLAIN_KEY = "sk-live-reviewtest1234wxyz"


def check(name, cond, info=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok  {name}")
    else:
        FAILED.append(name)
        print(f"FAIL  {name}  {info}")


def main() -> int:
    try:
        with TestClient(app) as client:
            s = SessionLocal()
            admin = User(email="revops@glow.test", password_hash=hash_password("x"),
                         name="RevOps", role=2)
            super_admin = User(email="revsuper@glow.test", password_hash=hash_password("x"),
                               name="RevSuper", role=9)
            artist = User(email="revartist@glow.test", password_hash=hash_password("x"),
                          name="RevArtist", role=4, status=1)
            s.add_all([admin, super_admin, artist])
            s.commit()
            H_OPS = {"Authorization": f"Bearer {create_token(admin.id, admin.role)}"}
            H_SUP = {"Authorization": f"Bearer {create_token(super_admin.id, super_admin.role)}"}
            H_ART = {"Authorization": f"Bearer {create_token(artist.id, artist.role)}"}

            # ===== 1. settings LLM Key 掩码 =====
            s.add(Setting(key="llm_config", value={
                "api_key": PLAIN_KEY, "base_url": "https://api.openai.com/v1",
                "model": "gpt-4o-mini", "timeout": 20,
            }))
            s.add(Setting(key="chat_quick_replies",
                          value={"zh": [{"q": "运费多少"}], "en": []}))
            s.commit()
            r = client.get("/api/admin/ops/settings", headers=H_OPS)
            kv = {i["key"]: i["value"] for i in r.json()["items"]}
            llm = kv.get("llm_config") or {}
            check("llm_config api_key 掩码（复用 mask_key，不再明文）",
                  r.status_code == 200 and llm.get("api_key") == mask_key(PLAIN_KEY)
                  and llm.get("api_key") == "sk-***wxyz"
                  and PLAIN_KEY not in r.text, llm)
            check("llm_config 形状不变 + api_key_set 约定（对齐 ai 域 config）",
                  llm.get("api_key_set") is True
                  and llm.get("base_url") == "https://api.openai.com/v1"
                  and llm.get("model") == "gpt-4o-mini"
                  and llm.get("timeout") == 20, llm)
            check("非 llm_config 行原样返回（chat_quick_replies 不受掩码影响）",
                  kv.get("chat_quick_replies") == {"zh": [{"q": "运费多少"}], "en": []},
                  kv.get("chat_quick_replies"))
            row = s.get(Setting, "llm_config")
            row.value = {**row.value, "api_key": ""}
            s.commit()
            llm = next(i["value"] for i in client.get(
                "/api/admin/ops/settings", headers=H_OPS).json()["items"]
                if i["key"] == "llm_config")
            check("api_key 空串保持空串 + api_key_set=False",
                  llm.get("api_key") == "" and llm.get("api_key_set") is False, llm)

            # ===== 2. settings 写白名单 =====
            r = client.put("/api/admin/ops/settings", headers=H_OPS,
                           json={"key": "llm_config", "value": {"api_key": "sk-hack"}})
            check("PUT 已存在非白名单 key（llm_config）→ 403 readonly",
                  r.status_code == 403 and r.json()["detail"] == "readonly setting key",
                  (r.status_code, r.json().get("detail")))
            r = client.put("/api/admin/ops/settings", headers=H_OPS,
                           json={"key": "chat_quick_replies", "value": {}})
            check("PUT 已存在非白名单 key（chat_quick_replies）→ 403 readonly",
                  r.status_code == 403 and r.json()["detail"] == "readonly setting key",
                  (r.status_code, r.json().get("detail")))
            r = client.put("/api/admin/ops/settings", headers=H_OPS,
                           json={"key": "review_ext_flag", "value": 1})
            check("运营建未知新 key → 403 unknown",
                  r.status_code == 403 and r.json()["detail"] == "unknown setting key",
                  (r.status_code, r.json().get("detail")))
            r = client.put("/api/admin/ops/settings", headers=H_SUP,
                           json={"key": "review_ext_flag", "value": 1})
            check("超管建未知新 key → 200",
                  r.status_code == 200 and r.json()["value"] == 1, r.text[:120])
            r = client.put("/api/admin/ops/settings", headers=H_OPS,
                           json={"key": "free_shipping_threshold", "value": 3600})
            check("白名单 key（SettingsView 项）运营可写 → 200",
                  r.status_code == 200 and r.json()["value"] == 3600, r.text[:120])
            r = client.put("/api/admin/ops/settings", headers=H_OPS,
                           json={"key": "bundle_2_off", "value": 15})
            check("白名单 key（MarketingView bundle 项，缺失可建）→ 200",
                  r.status_code == 200 and r.json()["value"] == 15, r.text[:120])

            # ===== 3. 美甲师(role=4)越权收口 =====
            r = client.get("/api/admin/ops/settings", headers=H_ART)
            check("role4 访问 ops settings → 403 artist scope",
                  r.status_code == 403 and r.json()["detail"] == "artist scope",
                  (r.status_code, r.json().get("detail")))
            r = client.get("/api/admin/ops/dashboard", headers=H_ART)
            check("role4 访问 dashboard → 403 artist scope",
                  r.status_code == 403 and r.json()["detail"] == "artist scope",
                  (r.status_code, r.json().get("detail")))
            r = client.get("/api/admin/chat/conversations", headers=H_ART)
            check("role4 访问 /api/admin/chat/ 前缀不被守卫拦截（200 列表）",
                  r.status_code == 200 and "items" in r.json(),
                  (r.status_code, r.text[:120]))
            r = client.get("/api/admin/ops/admins", headers=H_OPS)
            ids = [i["id"] for i in r.json()["items"]]
            check("工单指派候选排除美甲师（role=4 不在 admins 列表）",
                  r.status_code == 200 and artist.id not in ids
                  and {admin.id, super_admin.id} <= set(ids), ids)

            # ===== 4. 对账 resolve 死胡同出口 =====
            rec_alert = ReconciliationDaily(
                reconcile_date=date(2026, 8, 24), payments_gross=2000,
                orders_paid_total=1900, diff_payment=100, status=1, checked_at=utcnow())
            rec_done = ReconciliationDaily(
                reconcile_date=date(2026, 8, 23), payments_gross=1000,
                orders_paid_total=1000, status=2, checked_at=utcnow())
            s.add_all([rec_alert, rec_done])
            s.commit()
            r = client.post(f"/api/admin/ops/reconciliations/{rec_alert.id}/resolve",
                            headers=H_OPS)
            s.expire_all()
            check("resolve 告警行 → {ok:true} 且置 status=2",
                  r.status_code == 200 and r.json() == {"ok": True}
                  and s.get(ReconciliationDaily, rec_alert.id).status == 2, r.text[:120])
            r = client.post(f"/api/admin/ops/reconciliations/{rec_alert.id}/resolve",
                            headers=H_OPS)
            check("重复 resolve → 409 already resolved",
                  r.status_code == 409 and r.json()["detail"] == "already resolved",
                  (r.status_code, r.json().get("detail")))
            r = client.post("/api/admin/ops/reconciliations/999999/resolve",
                            headers=H_OPS)
            check("resolve 不存在 → 404", r.status_code == 404, r.status_code)
            d = client.get("/api/admin/ops/logs", headers=H_OPS,
                           params={"entity": "reconcile", "action": "resolve"}).json()
            check("resolve 审计落库（log_admin resolve/reconcile）",
                  d["total"] == 1 and d["items"][0]["entity_id"] == rec_alert.id,
                  d.get("total"))

            # ===== 5. 弹窗删除 =====
            r = client.post("/api/admin/ops/popups", headers=H_OPS,
                            json={"scene": "review_ext", "title": "Rev Ext"})
            popup_id = r.json()["id"]
            r = client.delete(f"/api/admin/ops/popups/{popup_id}", headers=H_OPS)
            check("popup 删除 → {ok:true} 且行消失",
                  r.status_code == 200 and r.json() == {"ok": True}
                  and s.get(PopupConfig, popup_id) is None, r.text[:120])
            r = client.delete(f"/api/admin/ops/popups/{popup_id}", headers=H_OPS)
            check("重复删除 → 404",
                  r.status_code == 404 and r.json()["detail"] == "popup not found",
                  (r.status_code, r.json().get("detail")))
            check("删除不存在 → 404",
                  client.delete("/api/admin/ops/popups/999999",
                                headers=H_OPS).status_code == 404)
            d = client.get("/api/admin/ops/logs", headers=H_OPS,
                           params={"entity": "popup", "action": "delete"}).json()
            check("popup 删除审计落库", d["total"] >= 1, d.get("total"))

            # ===== 6. 礼品卡作废（余额清零负流水）=====
            gc = GiftCard(code="GC-REV-VOID-01", initial_amount=3000, balance=3000,
                          status=1, purchaser_email="rev@glow.test")
            gc_used = GiftCard(code="GC-REV-USED-01", initial_amount=2000, balance=0,
                               status=3, purchaser_email="rev@glow.test")
            s.add_all([gc, gc_used])
            s.commit()
            r = client.put(f"/api/admin/promo/giftcards/{gc.id}/void", headers=H_OPS)
            d = r.json()
            check("void 有效卡 → 200 status=4 + 余额清零（形状同 freeze）",
                  r.status_code == 200 and d["status"] == 4
                  and d["balance_cents"] == 0 and d["code"] == gc.code, r.text[:160])
            led = client.get(f"/api/admin/promo/giftcards/{gc.id}/ledger",
                             headers=H_OPS).json()["items"]
            check("作废负流水（change_type=6 / -3000 / balance_after=0）",
                  led and led[0]["change_type"] == 6 and led[0]["delta_cents"] == -3000
                  and led[0]["balance_after_cents"] == 0, led[:1])
            r = client.put(f"/api/admin/promo/giftcards/{gc.id}/void", headers=H_OPS)
            check("重复 void → 409 already void",
                  r.status_code == 409 and r.json()["detail"] == "already void",
                  (r.status_code, r.json().get("detail")))
            r = client.put("/api/admin/promo/giftcards/999999/void", headers=H_OPS)
            check("void 不存在 → 404",
                  r.status_code == 404 and r.json()["detail"] == "giftcard not found",
                  (r.status_code, r.json().get("detail")))
            r = client.put(f"/api/admin/promo/giftcards/{gc_used.id}/void", headers=H_OPS)
            n_ledger = s.query(GiftCardLedger).filter(
                GiftCardLedger.gift_card_id == gc_used.id).count()
            check("零余额卡作废不产生流水（仅置 status=4）",
                  r.status_code == 200 and r.json()["status"] == 4 and n_ledger == 0,
                  (r.status_code, n_ledger))
            d = client.get("/api/admin/ops/logs", headers=H_OPS,
                            params={"entity": "giftcard", "action": "void"}).json()
            check("void 审计落库", d["total"] >= 1, d.get("total"))

            # ===== 7. 订阅列表 q 搜索 + skip_until =====
            user_hit = User(email="rev-search-hit@glow.test",
                            password_hash=hash_password("x"), name="Hit")
            user_other = User(email="rev-other@glow.test",
                              password_hash=hash_password("x"), name="Other")
            s.add_all([user_hit, user_other])
            s.commit()
            base = utcnow()
            skip_until = base + timedelta(days=20)
            sub_hit = Subscription(
                user_id=user_hit.id, stripe_subscription_id="SUBMOCKrev1",
                plan=1, style_mode=1, status=1,
                next_billing_at=base + timedelta(days=28), skip_until=skip_until,
                created_at=base - timedelta(days=4))
            s.add(sub_hit)
            for i in range(3):
                s.add(Subscription(
                    user_id=user_other.id, stripe_subscription_id=f"SUBMOCKrev{i + 2}",
                    plan=2, style_mode=2, status=1,
                    next_billing_at=base + timedelta(days=42),
                    created_at=base - timedelta(days=3 - i)))
            s.commit()
            d = client.get("/api/admin/member/subscriptions", headers=H_OPS,
                           params={"size": 2, "page": 2}).json()
            check("无 q 时命中目标的订阅在第 2 页（倒序分页基准）",
                  d["total"] == 4 and any(i["id"] == sub_hit.id for i in d["items"]),
                  (d.get("total"), [i["id"] for i in d.get("items", [])]))
            d = client.get("/api/admin/member/subscriptions", headers=H_OPS,
                           params={"q": "rev-search-hit"}).json()
            check("q 按 email 搜索命中第 2 页那条数据",
                  d["total"] == 1 and d["items"][0]["id"] == sub_hit.id
                  and d["items"][0]["email"] == "rev-search-hit@glow.test",
                  (d.get("total"), d.get("items", [])[:1]))
            check("订阅行含 skip_until 字段",
                  d["items"][0]["skip_until"] is not None
                  and d["items"][0]["skip_until"].startswith(skip_until.isoformat()[:10]),
                  d["items"][0].get("skip_until"))
            d = client.get("/api/admin/member/subscriptions", headers=H_OPS,
                           params={"q": "rev-search-hit", "status": 2}).json()
            check("q 与 status 组合过滤（无命中）", d["total"] == 0, d.get("total"))

            # ===== 8. 看板 AOV paid 口径 =====
            now = utcnow()
            s.add_all([
                Order(order_no="NSREVPAID01", email="rev@glow.test", status=1,
                      subtotal=1000, grand_total=1000, shipping_address=ADDR,
                      placed_at=now, paid_at=now),
                Order(order_no="NSREVUNPAID1", email="rev@glow.test", status=0,
                      subtotal=5000, grand_total=5000, shipping_address=ADDR,
                      placed_at=now),
            ])
            s.commit()
            d = client.get("/api/admin/ops/dashboard", headers=H_OPS).json()
            check("AOV 口径同配：today gmv/paid_count 均为 paid（ unpaid 不进 GMV）",
                  d["today"]["gmv_cents"] == 1000 and d["today"]["paid_count"] == 1,
                  d.get("today"))
            check("orders 卡仍为下单数（含未支付）+ 各窗口均有 paid_count",
                  d["today"]["orders"] == 2
                  and all("paid_count" in d[w] for w in ("today", "last7", "last30")),
                  {w: d[w] for w in ("today", "last7", "last30")})

            # ===== 9. 作废卡退款不回填（不可复活） =====
            gc_pay = GiftCard(code="GC-REV-PAY-01", initial_amount=2000, balance=500,
                              status=1, purchaser_email="rev@glow.test")
            s.add(gc_pay)
            s.flush()
            void_order = Order(order_no="NSREVVOIDGC1", email="rev@glow.test", status=1,
                               subtotal=2000, giftcard_discount=1500, grand_total=536,
                               shipping_address=ADDR, placed_at=utcnow(), paid_at=utcnow())
            s.add(void_order)
            s.flush()
            s.add(Payment(order_id=void_order.id, amount=536, status=1))
            s.add(GiftCardLedger(gift_card_id=gc_pay.id, order_id=void_order.id,
                                 change_type=3, amount=1500, balance_after=500))
            s.commit()
            r = client.put(f"/api/admin/promo/giftcards/{gc_pay.id}/void", headers=H_OPS)
            check("礼品卡支付的卡作废 → 200 status=4 + 余额清零",
                  r.status_code == 200 and r.json()["status"] == 4
                  and r.json()["balance_cents"] == 0, r.text[:120])
            r = client.post(f"/api/admin/trade/orders/{void_order.order_no}/refund",
                            headers=H_OPS)
            s.expire_all()
            gc_void = s.get(GiftCard, gc_pay.id)
            n_refund_ledger = s.query(GiftCardLedger).filter(
                GiftCardLedger.gift_card_id == gc_pay.id,
                GiftCardLedger.change_type == 5).count()
            check("作废卡退款不回填：全额退款后余额仍 0 / status=4（不复活）且无返还流水",
                  r.status_code == 200 and r.json().get("full") is True
                  and gc_void.balance == 0 and gc_void.status == 4
                  and n_refund_ledger == 0,
                  (r.status_code, gc_void.balance, gc_void.status, n_refund_ledger))

            s.close()

        print(f"\n{PASSED} passed, {len(FAILED)} failed")
        if FAILED:
            print("failed:", FAILED)
            return 1
        return 0
    finally:
        # 用完清理：先释放连接池再删 sqlite 文件（含 WAL/SHM）
        engine.dispose()
        _remove_db_files()


def test_review_ops_ext():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
