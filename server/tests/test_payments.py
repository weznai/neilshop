"""智能体 A 自测 —— 支付 Provider 抽象 / mock 默认模式全链路回归 / 伪 stripe 模块分支
（GM_DB=sqlite:///test_p.sqlite 独立库；BigInteger 垫片同 services/pricing.py 头部写法）"""

import logging
import os
import sys
import types
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_p.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient

from app.core.db import SessionLocal
from app.core.enums import PointsReason
from app.core.security import create_token, hash_password
from app.main import app
from app.models import (
    Category, DiscountCode, DiscountRedemption, Order, OrderItem, OrderTimeline,
    OutboxEvent, Payment, PointsLedger, Product, StockMovement, User, Variant,
    WebhookEvent,
)
from app.services import payment_provider as pp

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


def make_order(s, no, total, lines, *, user_id=None, code_id=None,
               discount_total=0, email="pay@glow.test", status=0):
    o = Order(order_no=no, user_id=user_id, email=email, status=status,
              subtotal=total, discount_total=discount_total,
              grand_total=total, shipping_address=ADDR, discount_code_id=code_id)
    s.add(o)
    s.flush()
    for vid, qty, price in lines:
        s.add(OrderItem(order_id=o.id, variant_id=vid, product_slug="bare-gems",
                        title_snapshot="Bare Gems", qty=qty, unit_price=price,
                        subtotal=price * qty))
    return o


def build_fake_stripe():
    calls = []
    state = {"mode": "ok", "event": None}

    class SignatureVerificationError(Exception):
        pass

    class FakePaymentIntent:
        @classmethod
        def create(cls, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id="pi_fake_123", client_secret="pi_fake_123_secret")

    class FakeWebhook:
        @staticmethod
        def construct_event(payload, sig_header, secret):
            if state["mode"] == "raise":
                raise SignatureVerificationError("bad signature")
            return state["event"]

    class FakeCheckoutSession:
        @classmethod
        def create(cls, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                id="cs_fake_1",
                url="https://checkout.stripe.com/c/pay/cs_fake_1",
            )

    stripe = types.ModuleType("stripe")
    err = types.ModuleType("stripe.error")
    err.SignatureVerificationError = SignatureVerificationError
    stripe.error = err
    stripe.PaymentIntent = FakePaymentIntent
    stripe.Webhook = FakeWebhook
    stripe.checkout = SimpleNamespace(Session=FakeCheckoutSession)
    stripe.api_key = ""
    return stripe, calls, state


try:
    with TestClient(app) as client:
        s = SessionLocal()

        cat = Category(slug="press-on-nails", name="Press-on Nails")
        s.add(cat)
        s.flush()
        p = Product(slug="bare-gems", title="Bare Gems", category_id=cat.id, status=1,
                    hero_image="https://img/b.jpg", price_min=1000, price_max=1000)
        s.add(p)
        s.flush()
        v1 = Variant(product_id=p.id, sku="BGP-S", option1_value="Short",
                     option2_value="24pcs", price=1000, stock=10)
        v2 = Variant(product_id=p.id, sku="BGP-L", option1_value="Long",
                     option2_value="24pcs", price=1500, stock=10)
        s.add_all([v1, v2])
        s.flush()
        emma = User(email="emma@glow.test", password_hash=hash_password("x"),
                    name="Emma", role=0, points=0)
        s.add(emma)
        s.flush()
        dc = DiscountCode(code="SAVE5", name="立减 5 刀", type=2, value=500,
                          max_discount=500, min_subtotal=0, first_order_only=0,
                          per_user_limit=1, is_active=1)
        s.add(dc)
        s.flush()

        o1 = make_order(s, "NS260815PAY01", 2000, [(v1.id, 1, 1000), (v2.id, 1, 1000)],
                        user_id=emma.id, code_id=dc.id, discount_total=500)
        o2 = make_order(s, "NS260815PAY02", 1500, [(v1.id, 1, 1500)], user_id=emma.id)
        o3 = make_order(s, "NS260815PAY03", 1000, [(v1.id, 1, 1000)], user_id=emma.id)
        s.commit()

        def order_by_no(no):
            s.expire_all()
            return s.query(Order).filter(Order.order_no == no).first()

        # ===== mock 默认模式：create-intent / mock-pay 回归 =====
        r = client.post("/api/payments/create-intent", json={"order_no": "NS260815PAY01"})
        d = r.json()
        check("mock create-intent → PI_+32hex / secret_mock / amount 2000",
              r.status_code == 200 and d["payment_intent"].startswith("PI_")
              and len(d["payment_intent"]) == 35
              and d["client_secret"].endswith("_secret_mock") and d["amount"] == 2000, d)

        r = client.post("/api/payments/create-intent", json={"order_no": "NS9999"})
        check("create-intent 订单不存在 → 404", r.status_code == 404, r.text)

        # ===== create-intent 幂等复用：二次调用返回同一 PENDING payment，不堆新行 =====
        r = client.post("/api/payments/create-intent", json={"order_no": "NS260815PAY02"})
        pi_reuse_a = r.json()["payment_intent"]
        r = client.post("/api/payments/create-intent", json={"order_no": "NS260815PAY02"})
        pi_reuse_b = r.json()["payment_intent"]
        s.expire_all()
        check("create-intent 二次调用复用同一 PENDING payment",
              r.status_code == 200 and pi_reuse_a == pi_reuse_b
              and pi_reuse_a.startswith("PI_")
              and s.query(Payment).filter(Payment.order_id == o2.id).count() == 1,
              (pi_reuse_a, pi_reuse_b))

        # ===== GM_ENV 门禁：非 dev 下 mock-pay 404 / webhook 未配密钥 400 / mock intent 409 =====
        app_settings.env = "prod"
        r = client.post("/api/payments/mock-pay",
                        json={"order_no": "NS260815PAY01", "succeed": True})
        check("GM_ENV=prod → mock-pay 404 not_found", r.status_code == 404, r.text)
        r = client.post("/api/payments/webhook", json={
            "id": "evt_env_1", "type": "payment_intent.succeeded",
            "data": {"payment_intent": "PI_whatever"}})
        check("GM_ENV=prod 未配验签密钥 → webhook 400 webhook_secret_not_configured",
              r.status_code == 400 and r.json()["detail"] == "webhook_secret_not_configured",
              r.text)
        r = client.get("/api/payments/methods")
        d = r.json()
        check("GM_ENV=prod 无真实凭据 → methods providers=[] / default=none",
              r.status_code == 200
              and d == {"providers": [], "default": "none"}, d)
        r = client.post("/api/payments/create-intent", json={"order_no": "NS260815PAY02"})
        check("GM_ENV=prod 默认链 mock → create-intent 409 mock_provider_disabled",
              r.status_code == 409 and r.json()["detail"] == "mock_provider_disabled", r.text)
        r = client.post("/api/payments/create-intent",
                        json={"order_no": "NS260815PAY02", "provider": "stripe"})
        check("GM_ENV=prod 显式 provider 回落 mock 分支 → 409 mock_provider_disabled",
              r.status_code == 409 and r.json()["detail"] == "mock_provider_disabled", r.text)
        app_settings.env = "dev"
        check("GM_ENV 还原 dev 后门禁放行（404 order_not_found 而非 not_found）",
              client.post("/api/payments/mock-pay",
                          json={"order_no": "NS_NOPE", "succeed": True}).json().get("detail")
              == "order_not_found")

        r = client.post("/api/payments/mock-pay",
                        json={"order_no": "NS260815PAY01", "succeed": False})
        d = r.json()
        pay1 = (s.query(Payment).filter(Payment.order_id == o1.id)
                .order_by(Payment.id.desc()).first())
        check("mock-pay 失败 → Payment FAILED 订单 PENDING + payment_failed timeline",
              r.status_code == 200 and d["payment_status"] == 2 and d["order_status"] == 0
              and pay1.failure_reason == "mock_declined"
              and s.query(OrderTimeline).filter(OrderTimeline.order_id == o1.id,
                                                OrderTimeline.event == "payment_failed").count() == 1, d)

        r = client.post("/api/payments/create-intent", json={"order_no": "NS260815PAY01"})
        r = client.post("/api/payments/mock-pay",
                        json={"order_no": "NS260815PAY01", "succeed": True})
        d = r.json()
        o1 = order_by_no("NS260815PAY01")
        s.expire_all()
        check("mock-pay 成功 → 订单 PAID / Payment SUCCESS / paid_at",
              r.status_code == 200 and o1.status == 1 and o1.paid_at is not None
              and d["payment_status"] == 1, d)

        emma_db = s.get(User, emma.id)
        ledger = (s.query(PointsLedger)
                  .filter(PointsLedger.user_id == emma.id,
                          PointsLedger.reason == int(PointsReason.ORDER_EARN_FROZEN)).first())
        check("mock-pay 积分 2000//10=200 冻结入账",
              o1.points_earned == 200 and ledger is not None and ledger.frozen == 1
              and emma_db.points == 200, (o1.points_earned, emma_db.points))

        outbox_paid = (s.query(OutboxEvent)
                       .filter(OutboxEvent.event_type == "order.paid",
                               OutboxEvent.aggregate_id == o1.id).first())
        redemption = (s.query(DiscountRedemption)
                      .filter(DiscountRedemption.order_id == o1.id).first())
        dc_db = s.query(DiscountCode).filter(DiscountCode.code == "SAVE5").first()
        check("mock-pay total_spent 2000 + outbox order.paid",
              emma_db.total_spent == 2000 and outbox_paid is not None
              and outbox_paid.payload["grand_total"] == 2000,
              (emma_db.total_spent,))
        check("mock-pay Redemption 500 + used_count 1",
              redemption is not None and redemption.discount_amount == 500
              and dc_db.used_count == 1)
        check("mock-pay DEDUCT 实扣确认 2 条且库存不变",
              s.query(StockMovement).filter(StockMovement.type == 3).count() == 2
              and s.get(Variant, v1.id).stock == 10 and s.get(Variant, v2.id).stock == 10)

        r = client.post("/api/payments/mock-pay",
                        json={"order_no": "NS260815PAY01", "succeed": True})
        check("mock-pay 已付 → 409 already_paid", r.status_code == 409, r.text)

        # ===== 赢者语义：已取消订单的迟到回调不把 payment 置 SUCCESS =====
        o9 = make_order(s, "NS260815PAY09", 1000, [(v1.id, 1, 1000)], user_id=emma.id)
        s.commit()
        emma_auth = {"Authorization": f"Bearer {create_token(emma.id, emma.role)}"}
        pi9 = client.post("/api/payments/create-intent",
                          json={"order_no": "NS260815PAY09"}).json()["payment_intent"]
        r = client.post("/api/orders/NS260815PAY09/cancel", headers=emma_auth)
        check("迟到回调前置：待付单取消 → 200 CANCELED", r.status_code == 200, r.text)
        r = client.post("/api/payments/webhook", json={
            "id": "evt_late_1", "type": "payment_intent.succeeded",
            "data": {"payment_intent": pi9}})
        o9 = order_by_no("NS260815PAY09")
        s.expire_all()
        pay9 = (s.query(Payment).filter(Payment.order_id == o9.id)
                .order_by(Payment.id.desc()).first())
        check("已取消订单的迟到 webhook → 订单仍 8 / payment 保持 PENDING（防假支付）",
              r.status_code == 200 and o9.status == 8 and pay9.status == 0
              and pay9.refunded_amount == 0
              and s.query(PointsLedger).filter(
                  PointsLedger.ref_id == o9.id,
                  PointsLedger.reason == int(PointsReason.ORDER_EARN_FROZEN)).count() == 0,
              (o9.status, pay9.status))

        # ===== mock 默认模式：webhook 回归 =====
        r = client.post("/api/payments/create-intent", json={"order_no": "NS260815PAY02"})
        pi2 = r.json()["payment_intent"]
        r = client.post("/api/payments/webhook", json={
            "id": "evt_p_1", "type": "payment_intent.succeeded",
            "data": {"payment_intent": pi2}})
        o2 = order_by_no("NS260815PAY02")
        evt_db = s.get(WebhookEvent, "evt_p_1")
        check("webhook payment_intent.succeeded → 订单 PAID + WebhookEvent 已处理",
              r.status_code == 200 and o2.status == 1
              and evt_db is not None and evt_db.status == 1
              and evt_db.processed_at is not None, r.text)

        r = client.post("/api/payments/webhook", json={
            "id": "evt_p_1", "type": "payment_intent.succeeded",
            "data": {"payment_intent": pi2}})
        check("webhook 同 event_id 幂等 → duplicate",
              r.status_code == 200 and r.json().get("duplicate") is True, r.text)

        r = client.post("/api/payments/webhook", json={
            "id": "evt_p_2", "type": "payment_intent.succeeded",
            "data": {"payment_intent": "PI_nope"}})
        d = r.json()
        s.expire_all()
        evt_p2 = s.get(WebhookEvent, "evt_p_2")
        check("webhook 未知 payment_intent → 200 skipped + WebhookEvent status=2（不可恢复不重试）",
              r.status_code == 200 and d.get("ok") is True
              and d.get("skipped") == "payment_intent_not_found"
              and evt_p2 is not None and evt_p2.status == 2
              and evt_p2.processed_at is not None, (d, evt_p2 and evt_p2.status))
        r = client.post("/api/payments/webhook", json={
            "id": "evt_p_2", "type": "payment_intent.succeeded",
            "data": {"payment_intent": "PI_nope"}})
        check("status=2 事件重发 → 200 幂等 skipped（不再处理）",
              r.status_code == 200 and r.json().get("skipped") is True, r.text)

        # ===== webhook 不可恢复：全额退款后重发 charge.refunded → 200 skipped + status=2 =====
        o10 = make_order(s, "NS260815PAY10", 1000, [(v1.id, 1, 1000)], user_id=emma.id)
        s.commit()
        pi10 = client.post("/api/payments/create-intent",
                           json={"order_no": "NS260815PAY10"}).json()["payment_intent"]
        assert client.post("/api/payments/mock-pay",
                           json={"order_no": "NS260815PAY10", "succeed": True}).status_code == 200
        r = client.post("/api/payments/webhook", json={
            "id": "evt_ref_1", "type": "charge.refunded",
            "data": {"payment_intent": pi10, "amount": 1000}})
        check("charge.refunded 全额退款首推 → 200 ok（payment → 3 全退）",
              r.status_code == 200 and r.json().get("ok") is True, r.text)
        r = client.post("/api/payments/webhook", json={
            "id": "evt_ref_2", "type": "charge.refunded",
            "data": {"payment_intent": pi10, "amount": 100}})
        d = r.json()
        s.expire_all()
        evt_ref2 = s.get(WebhookEvent, "evt_ref_2")
        pay10 = (s.query(Payment).filter(Payment.stripe_payment_intent == pi10)
                 .first())
        check("全退后重发 charge.refunded → 200 skipped（不可恢复码）+ evt status=2",
              r.status_code == 200
              and d.get("skipped") in ("already_fully_refunded", "no_refundable_payment")
              and evt_ref2 is not None and evt_ref2.status == 2
              and pay10.refunded_amount == 1000,
              (d, evt_ref2 and evt_ref2.status))
        r = client.post("/api/payments/webhook", json={
            "id": "evt_ref_2", "type": "charge.refunded",
            "data": {"payment_intent": pi10, "amount": 100}})
        check("已标 status=2 的退款事件重发 → 幂等 skipped",
              r.status_code == 200 and r.json().get("skipped") is True, r.text)

        # ===== provider 选择 =====
        logs = []

        class _Cap(logging.Handler):
            def emit(self, record):
                logs.append(record.getMessage())

        pp.logger.setLevel(logging.WARNING)
        pp.logger.addHandler(_Cap())
        pp._mock_warned = False

        pp._provider = None
        p_mock = pp.get_provider()
        check("无 key → MockProvider + 一次性告警",
              p_mock.name == "mock" and isinstance(p_mock, pp.MockProvider)
              and any("stripe key absent" in m for m in logs), logs)

        app_settings.stripe_key = "sk_test_fake"
        sys.modules["stripe"] = None
        pp._provider = None
        p_fb = pp.get_provider()
        check("有 key 缺包 → 降级 MockProvider + 告警",
              p_fb.name == "mock" and any("package missing" in m for m in logs), logs)

        fake_stripe, calls, state = build_fake_stripe()
        sys.modules["stripe"] = fake_stripe
        pp._provider = None
        p_stripe = pp.get_provider()
        check("有 key 有包 → StripeProvider", p_stripe.name == "stripe"
              and isinstance(p_stripe, pp.StripeProvider), type(p_stripe))

        res = p_stripe.create_intent(o1, 2000)
        check("StripeProvider.create_intent 参数 amount/currency/metadata/idempotency_key",
              calls and calls[0] == {"amount": 2000, "currency": "usd",
                                     "metadata": {"order_no": "NS260815PAY01"},
                                     "idempotency_key": "NS260815PAY01"}
              and res == {"payment_intent": "pi_fake_123",
                          "client_secret": "pi_fake_123_secret"}, calls)

        try:
            p_stripe.confirm(o1, None, True)
            raised = False
        except NotImplementedError:
            raised = True
        check("StripeProvider.confirm → NotImplementedError", raised)

        state["mode"] = "raise"
        try:
            p_stripe.verify_webhook(b"{}", "sig_bad")
            sig_raised = False
        except pp.InvalidSignatureError:
            sig_raised = True
        check("verify_webhook 签名失败 → InvalidSignatureError", sig_raised)

        state["mode"] = "ok"
        state["event"] = {"id": "evt_10", "type": "payment_intent.succeeded",
                          "data": {"object": {"id": "pi_x", "metadata": {}}}}
        try:
            p_stripe.verify_webhook(b"{}", "sig")
            meta_raised = False
        except pp.WebhookVerificationError:
            meta_raised = True
        check("verify_webhook 缺 order_no → WebhookVerificationError", meta_raised)

        state["event"] = {"id": "evt_11", "type": "payment_intent.succeeded",
                          "data": {"object": {"id": "pi_x", "amount": 1500,
                                              "metadata": {"order_no": "NS260815PAY01"}}}}
        ne = pp.normalize_event(p_stripe.verify_webhook(b"{}", "sig"))
        check("verify + normalize → data.payment_intent 取自 object.id",
              ne["id"] == "evt_11" and ne["data"]["payment_intent"] == "pi_x"
              and ne["data"]["amount"] == 1500
              and ne["data"]["metadata"]["order_no"] == "NS260815PAY01", ne)

        ne2 = pp.normalize_event({"id": "evt_m", "type": "t",
                                  "data": {"payment_intent": "PI_abc"}})
        check("normalize mock 形态原样透传",
              ne2 == {"id": "evt_m", "type": "t", "data": {"payment_intent": "PI_abc"}}, ne2)

        # ===== stripe 模式 API =====
        r = client.post("/api/payments/create-intent", json={"order_no": "NS260815PAY03"})
        d = r.json()
        check("stripe 模式 create-intent → 走 SDK 返回 pi_fake_123",
              r.status_code == 200 and d["payment_intent"] == "pi_fake_123"
              and d["client_secret"] == "pi_fake_123_secret"
              and (s.query(Payment).filter(Payment.stripe_payment_intent == "pi_fake_123")
                   .count() == 1), d)

        r = client.post("/api/payments/mock-pay", json={"order_no": "NS260815PAY03"})
        check("stripe 模式 mock-pay → 409 use_webhook",
              r.status_code == 409 and r.json()["detail"] == "use_webhook", r.text)

        state["event"] = {"id": "evt_st_1", "type": "payment_intent.succeeded",
                          "data": {"object": {"id": "pi_fake_123", "amount": 1000,
                                              "metadata": {"order_no": "NS260815PAY03"}}}}
        r = client.post("/api/payments/webhook",
                        headers={"stripe-signature": "t=1,v=1"},
                        json={"id": "evt_st_1", "type": "payment_intent.succeeded",
                              "data": {"payment_intent": "pi_fake_123"}})
        o3 = order_by_no("NS260815PAY03")
        check("stripe 模式 webhook 验签通过 → 订单 PAID",
              r.status_code == 200 and o3.status == 1, r.text)

        state["mode"] = "raise"
        r = client.post("/api/payments/webhook",
                        headers={"stripe-signature": "t=1,v=bad"},
                        json={"id": "evt_st_2", "type": "payment_intent.succeeded",
                              "data": {"payment_intent": "pi_fake_123"}})
        check("stripe 模式 webhook 无效签名 → 400 invalid_signature",
              r.status_code == 400 and r.json()["detail"] == "invalid_signature", r.text)

        # ===== 智能体 B：PayPal / Klarna / provider 选择矩阵（全 monkeypatch，无外呼） =====
        sys.modules.pop("stripe", None)
        app_settings.stripe_key = ""
        app_settings.stripe_klarna = 0
        app_settings.paypal_client_id = ""
        app_settings.paypal_secret = ""
        pp._provider = None
        pp._mock_warned = False
        pp._paypal_warned = False
        logs.clear()

        o4 = make_order(s, "NS260815PAY04", 2000, [(v1.id, 2, 1000)], user_id=emma.id)
        o5 = make_order(s, "NS260815PAY05", 1000, [(v1.id, 1, 1000)], user_id=emma.id)
        o6 = make_order(s, "NS260815PAY06", 1000, [(v1.id, 1, 1000)], user_id=emma.id)
        s.commit()

        check("B 矩阵: 无凭据 → mock", pp.get_provider().name == "mock")

        app_settings.paypal_client_id = "pid_test"
        app_settings.paypal_secret = "psecret_test"
        pp._provider = None
        p_paypal = pp.get_provider()
        check("B 矩阵: 仅 paypal 凭据 → PayPalProvider（默认沙箱 base）",
              isinstance(p_paypal, pp.PayPalProvider)
              and p_paypal.base == "https://api-m.sandbox.paypal.com", type(p_paypal))

        app_settings.stripe_key = "sk_test_fake"
        sys.modules["stripe"] = fake_stripe
        pp._provider = None
        check("B 矩阵: stripe+paypal 并存 → stripe 优先", pp.get_provider().name == "stripe")

        sys.modules.pop("stripe", None)
        app_settings.stripe_key = ""
        app_settings.paypal_secret = ""
        pp._provider = None
        pp._paypal_warned = False
        logs.clear()
        check("B 矩阵: paypal 半缺（有 id 无 secret）→ mock + incomplete 告警",
              pp.get_provider().name == "mock" and any("incomplete" in m for m in logs), logs)

        app_settings.paypal_secret = "psecret_test"
        pay_provider = pp.PayPalProvider()

        import json as _json

        def _pp_noop():
            return None

        class _FakeHTTP:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if url.endswith("/v2/oauth2/token"):
                    return SimpleNamespace(
                        status_code=200, raise_for_status=_pp_noop,
                        json=lambda: {"access_token": "tok_b_1"})
                return SimpleNamespace(
                    status_code=201, raise_for_status=_pp_noop,
                    json=lambda: {"id": "PAYID-B-0001",
                                  "links": [{"rel": "approve",
                                             "href": "https://pp.example/approve"}]})

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        fake_http = _FakeHTTP()
        pay_provider._client = lambda: fake_http
        pp_res = pay_provider.create_intent(o4, 2000)

        oauth_url, oauth_kw = fake_http.calls[0]
        check("B PayPal oauth: POST {base}/v2/oauth2/token + Basic auth + client_credentials",
              oauth_url == "https://api-m.sandbox.paypal.com/v2/oauth2/token"
              and oauth_kw["auth"] == ("pid_test", "psecret_test")
              and oauth_kw["data"] == {"grant_type": "client_credentials"}, (oauth_url, oauth_kw))

        order_url, order_kw = fake_http.calls[1]
        pu = order_kw["json"]["purchase_units"][0]
        check("B PayPal orders: Bearer token + PayPal-Request-Id 幂等 + amount USD + metadata.order_no",
              order_url == "https://api-m.sandbox.paypal.com/v2/checkout/orders"
              and order_kw["headers"] == {"Authorization": "Bearer tok_b_1",
                                          "PayPal-Request-Id": "NS260815PAY04"}
              and pu["amount"] == {"currency_code": "USD", "value": "20.00"}
              and pu["custom_id"] == "NS260815PAY04"
              and pu["metadata"] == {"order_no": "NS260815PAY04"}, order_kw)

        check("B PayPal create_intent 返回: 订单 id + approve 链接作 client_secret + redirect_url",
              pp_res == {"payment_intent": "PAYID-B-0001",
                         "client_secret": "https://pp.example/approve",
                         "redirect_url": "https://pp.example/approve"}, pp_res)

        try:
            pay_provider.verify_webhook(b"{}", None)
            no_hdr = False
        except pp.InvalidSignatureError:
            no_hdr = True
        try:
            pay_provider.verify_webhook(b"{not-json", "t=1")
            bad_json = False
        except pp.WebhookVerificationError:
            bad_json = True
        check("B PayPal verify_webhook 桩: 无 header → InvalidSignature / 坏 JSON → WebhookVerificationError",
              no_hdr and bad_json)

        ok_evt = _json.dumps({"id": "WH-1", "type": "PAYMENT.CAPTURE.COMPLETED",
                              "resource": {"id": "CAP-1"}}).encode()
        try:
            pay_provider.verify_webhook(_json.dumps({"id": "WH-2"}).encode(), "t=1")
            no_type = False
        except pp.WebhookVerificationError:
            no_type = True
        vw = pay_provider.verify_webhook(ok_evt, "t=1")
        check("B PayPal verify_webhook 桩: 正常事件返回 / 缺 type → WebhookVerificationError",
              vw["id"] == "WH-1" and vw["type"] == "PAYMENT.CAPTURE.COMPLETED" and no_type, vw)

        app_settings.paypal_webhook_id = "WHID-OK"
        try:
            pay_provider.verify_webhook(_json.dumps(
                {"id": "WH-3", "type": "T", "webhook_id": "WHID-BAD"}).encode(), "t=1")
            wid_bad = False
        except pp.InvalidSignatureError:
            wid_bad = True
        wid_evt = pay_provider.verify_webhook(_json.dumps(
            {"id": "WH-4", "type": "T", "webhook_id": "WHID-OK"}).encode(), "t=1")
        check("B PayPal verify_webhook 桩: webhook_id 匹配通过 / 不匹配 → InvalidSignatureError",
              wid_bad and wid_evt["id"] == "WH-4")
        del app_settings.paypal_webhook_id

        try:
            pay_provider.confirm(o4, None, True)
            pp_confirm = False
        except NotImplementedError:
            pp_confirm = True
        check("B PayPalProvider.confirm → NotImplementedError", pp_confirm)

        app_settings.paypal_client_id = ""
        app_settings.paypal_secret = ""
        sys.modules.pop("stripe", None)
        app_settings.stripe_key = ""
        pp._provider = None
        r = client.get("/api/payments/methods")
        d = r.json()
        check("B /methods 无凭据 → providers=[mock] / default=mock",
              r.status_code == 200
              and d == {"providers": [{"id": "mock", "name": "Mock Pay (dev)", "klarna": False}],
                        "default": "mock"}, d)

        app_settings.stripe_key = "sk_test_fake"
        sys.modules["stripe"] = fake_stripe
        app_settings.stripe_klarna = 1
        pp._provider = None
        r = client.get("/api/payments/methods")
        d = r.json()
        check("B /methods stripe+klarna → providers=[stripe(klarna)] / default=stripe",
              r.status_code == 200 and pp.available_providers() == ["stripe(klarna)"]
              and d == {"providers": [{"id": "stripe", "name": "Credit / Debit Card (Stripe)",
                                       "klarna": True}], "default": "stripe"}, d)

        app_settings.stripe_key = ""
        sys.modules.pop("stripe", None)
        app_settings.stripe_klarna = 0
        app_settings.paypal_client_id = "pid_test"
        app_settings.paypal_secret = "psecret_test"
        pp._provider = None
        r = client.get("/api/payments/methods")
        d = r.json()
        check("B /methods 仅 paypal → providers=[paypal] / default=paypal",
              r.status_code == 200 and pp.available_providers() == ["paypal"]
              and d == {"providers": [{"id": "paypal", "name": "PayPal", "klarna": False}],
                        "default": "paypal"}, d)

        app_settings.paypal_client_id = ""
        app_settings.paypal_secret = ""
        pp._provider = None
        r = client.post("/api/payments/create-intent",
                        json={"order_no": "NS260815PAY05", "provider": "stripe"})
        d = r.json()
        check("B create-intent mock 默认 + provider=stripe → 回落 mock + 响应 provider=mock",
              r.status_code == 200 and d["payment_intent"].startswith("PI_")
              and d["client_secret"].endswith("_secret_mock") and d["provider"] == "mock", d)

        # ===== create-intent 幂等复用区分 provider：mock PENDING 在 → paypal 不复用建新；同 provider 二次复用 =====
        o7 = make_order(s, "NS260815PAY07", 1500, [(v1.id, 1, 1500)], user_id=emma.id)
        s.commit()
        r = client.post("/api/payments/create-intent", json={"order_no": "NS260815PAY07"})
        d = r.json()
        check("mock intent 响应含 redirect_url 空串（前端无 pay-mock 页，不跳转维持现状）",
              r.status_code == 200 and d["redirect_url"] == ""
              and d["payment_intent"].startswith("PI_"), d)
        app_settings.paypal_client_id = "pid_test"
        app_settings.paypal_secret = "psecret_test"
        pp._provider = None
        fake_http3 = _FakeHTTP()
        _orig_client3 = pp.PayPalProvider._client
        pp.PayPalProvider._client = lambda self: fake_http3
        try:
            r = client.post("/api/payments/create-intent",
                            json={"order_no": "NS260815PAY07", "provider": "paypal"})
            d = r.json()
            s.expire_all()
            check("跨 provider 不复用：单上已有 mock PENDING → paypal 建新行 PAYID + redirect_url=approve",
                  r.status_code == 200 and d["payment_intent"] == "PAYID-B-0001"
                  and d["provider"] == "paypal"
                  and d["redirect_url"] == "https://pp.example/approve"
                  and s.query(Payment).filter(Payment.order_id == o7.id).count() == 2
                  and len(fake_http3.calls) == 2, d)
            r = client.post("/api/payments/create-intent",
                            json={"order_no": "NS260815PAY07", "provider": "paypal"})
            d = r.json()
            s.expire_all()
            check("同 provider 二次调用 → 复用 PENDING（不建新行 / 无新外呼）",
                  r.status_code == 200 and d["payment_intent"] == "PAYID-B-0001"
                  and s.query(Payment).filter(Payment.order_id == o7.id).count() == 2
                  and len(fake_http3.calls) == 2, d)
        finally:
            pp.PayPalProvider._client = _orig_client3
            app_settings.paypal_client_id = ""
            app_settings.paypal_secret = ""
            pp._provider = None

        app_settings.stripe_key = "sk_test_fake"
        sys.modules["stripe"] = fake_stripe
        pp._provider = None
        r = client.post("/api/payments/create-intent",
                        json={"order_no": "NS260815PAY06", "provider": "paypal"})
        check("B create-intent 非默认 provider 不可用 → 400 provider_unavailable",
              r.status_code == 400 and r.json()["detail"] == "provider_unavailable", r.text)

        sys.modules.pop("stripe", None)
        app_settings.stripe_key = ""
        app_settings.paypal_client_id = "pid_test"
        app_settings.paypal_secret = "psecret_test"
        pp._provider = None
        fake_http2 = _FakeHTTP()
        _orig_client = pp.PayPalProvider._client
        pp.PayPalProvider._client = lambda self: fake_http2
        try:
            r = client.post("/api/payments/create-intent",
                            json={"order_no": "NS260815PAY04", "provider": "paypal"})
            d = r.json()
        finally:
            pp.PayPalProvider._client = _orig_client
        check("B create-intent provider=paypal（伪造可用）→ 走 PayPal 桩落库 + provider=paypal",
              r.status_code == 200 and d["payment_intent"] == "PAYID-B-0001"
              and d["provider"] == "paypal" and len(fake_http2.calls) == 2
              and s.query(Payment).filter(
                  Payment.order_id == o4.id,
                  Payment.stripe_payment_intent == "PAYID-B-0001").count() == 1, d)

        app_settings.stripe_key = "sk_test_fake"
        sys.modules["stripe"] = fake_stripe
        app_settings.stripe_klarna = 1
        p_stripe_b = pp.StripeProvider()
        p_stripe_b.create_intent(o5, 1000)
        klarna_call = dict(calls[-1])
        app_settings.stripe_klarna = 0
        p_stripe_b.create_intent(o5, 1000)
        plain_call = dict(calls[-1])
        check("B stripe_klarna=1 → payment_method_types=[card,klarna]；=0 → 不传（默认不变）",
              klarna_call.get("payment_method_types") == ["card", "klarna"]
              and klarna_call["idempotency_key"] == "NS260815PAY05"
              and klarna_call["amount"] == 1000
              and "payment_method_types" not in plain_call, (klarna_call, plain_call))

        # ===== StripeProvider.create_checkout（hosted checkout 会话）=====
        res_ck = p_stripe_b.create_checkout("NS260815PAY05", 1000, "https://shop.example.com/")
        kw_ck = calls[-1]
        check("create_checkout: success/cancel 回跳 + client_reference_id + line_items 单价",
              kw_ck["mode"] == "payment"
              and kw_ck["success_url"] == (
                  "https://shop.example.com/success?no=NS260815PAY05"
                  "&session_id={CHECKOUT_SESSION_ID}")
              and kw_ck["cancel_url"] == "https://shop.example.com/checkout?canceled=1"
              and kw_ck["client_reference_id"] == "NS260815PAY05"
              and kw_ck["metadata"] == {"order_no": "NS260815PAY05"}
              and kw_ck["line_items"][0]["price_data"]["unit_amount"] == 1000
              and kw_ck["line_items"][0]["quantity"] == 1
              and res_ck == {"checkout_session_id": "cs_fake_1",
                             "redirect_url": "https://checkout.stripe.com/c/pay/cs_fake_1"},
              (kw_ck, res_ck))
        app_settings.stripe_key = ""
        p_nokey = pp.StripeProvider()
        try:
            p_nokey.create_checkout("X1", 100, "https://s.example.com/")
            ck_raised = False
        except pp.ProviderUnavailable:
            ck_raised = True
        check("create_checkout 无 key → ProviderUnavailable", ck_raised)

        s.close()
finally:
    app_settings.stripe_key = ""
    app_settings.stripe_webhook_secret = ""
    app_settings.stripe_klarna = 0
    app_settings.paypal_client_id = ""
    app_settings.paypal_secret = ""
    app_settings.paypal_webhook_id = ""
    app_settings.env = "dev"
    sys.modules.pop("stripe", None)
    pp._provider = None
    pp._mock_warned = False
    pp._paypal_warned = False

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
