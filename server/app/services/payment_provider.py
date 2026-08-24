"""支付 Provider 抽象层 —— 无 GM_STRIPE_KEY 时 MockProvider（行为对齐原 mock 版）；
设置 GM_STRIPE_KEY / GM_STRIPE_WEBHOOK_SECRET 并安装 stripe 包后自动切换 StripeProvider，
缺包时惰性导入失败降级 mock 并告警。
配置来源（resolve_pay_config）：settings 表 payment_config（后台「系统设置 → 支付通道」，
热生效）> GM_STRIPE_* / GM_PAYPAL_* 环境变量；后台保存后 reset_provider_cache 立即切换。
Klarna：不建独立 Provider —— stripe_klarna 开（表字段或 GM_STRIPE_KLARNA=1）时
StripeProvider 的 PaymentIntent 附带 payment_method_types=["card","klarna"]；
Klarna 经 Stripe 仅在 US/UK/DE/AT/BE/NL/SE/NO/FI/DK 等部分地区可用，以 Stripe
账户后台实际开通为准。
PayPal：paypal_client_id + paypal_secret 齐全且 httpx 可用时启用 PayPalProvider
（Orders v2 REST 直调，paypal_base 默认沙箱）。选择优先级 stripe > paypal > mock，
缺凭据/缺包逐级降级，每个不可用原因一次性 warning。"""

import json
import logging
import time
import uuid
from abc import ABC, abstractmethod

from app.core.config import settings

logger = logging.getLogger("glowmag.payments")

# 后台 settings 表 mock_pay 键：存在即优先于 GM_MOCK_PAY 环境变量（管理员可运维开关）
MOCK_PAY_SETTING_KEY = "mock_pay"


def mock_pay_enabled(db=None) -> bool:
    """mock 支付总开关（三级优先）：settings 表 mock_pay > 环境变量 GM_MOCK_PAY > env==dev。
    行缺失/值为 null 视为未配置，回落环境链；值支持 JSON 布尔/数字/字符串（1/0、true/false、on/off）。"""
    if db is not None:
        from app.models import Setting
        row = db.get(Setting, MOCK_PAY_SETTING_KEY)
        if row is not None and row.value is not None:
            if isinstance(row.value, bool):
                return row.value
            return str(row.value).strip().lower() in ("1", "true", "on", "yes")
    return settings.mock_pay_enabled


# 支付通道配置（settings 表 key=payment_config，JSON）：后台「系统设置 → 支付通道」可配，
# 字段级覆盖 GM_STRIPE_* / GM_PAYPAL_* 环境变量（优先链与 llm_config 一致：DB 非空值 > env）；
# 表内空串/缺省字段不生效（回落 env）——即「后台清除 = 回到环境变量配置」而非「清除凭据」
PAY_SETTING_KEY = "payment_config"

# 凭据字段（GET 回显需脱敏）：密钥只存服务端，界面以掩码展示
PAY_SECRET_FIELDS = ("stripe_key", "stripe_webhook_secret", "paypal_secret", "paypal_webhook_id")


def mask_secret(value: str) -> str:
    """凭据脱敏展示：sk_***wxyz（≤8 位全隐藏；对齐 llm.mask_key 规则）"""
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:3] + "***" + value[-4:]


def _importable(module: str) -> bool:
    """依赖包可用性探测（后台支付配置页提示「缺包降级」用）"""
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def resolve_pay_config(db=None) -> dict:
    """支付通道生效配置：env 兜底 + settings 表 payment_config 覆盖（DB 异常静默回退 env，
    支付不断供）。每次调用实时解析（读一行 Setting，代价可忽略），保存后无需重启。"""
    cfg = {
        "stripe_key": settings.stripe_key,
        "stripe_webhook_secret": settings.stripe_webhook_secret,
        "stripe_klarna": bool(settings.stripe_klarna),
        "paypal_client_id": settings.paypal_client_id,
        "paypal_secret": settings.paypal_secret,
        "paypal_base": settings.paypal_base,
        "paypal_webhook_id": settings.paypal_webhook_id,
    }
    if db is not None:
        try:
            from app.models import Setting

            row = db.get(Setting, PAY_SETTING_KEY)
            if row and isinstance(row.value, dict):
                for k in ("stripe_key", "stripe_webhook_secret", "paypal_client_id",
                          "paypal_secret", "paypal_base", "paypal_webhook_id"):
                    v = row.value.get(k)
                    if isinstance(v, str) and v.strip():
                        cfg[k] = v.strip()
                v = row.value.get("stripe_klarna")
                if isinstance(v, bool):
                    cfg["stripe_klarna"] = v
        except Exception as exc:  # DB 故障不影响 env 配置
            logger.warning("payment config load failed: %s", exc)
    return cfg


class ProviderUnavailable(Exception):
    pass


class WebhookVerificationError(Exception):
    pass


class InvalidSignatureError(WebhookVerificationError):
    pass


class PaymentProvider(ABC):
    name: str = ""

    @abstractmethod
    def create_intent(self, order, amount_cents: int) -> dict:
        ...

    @abstractmethod
    def confirm(self, order, payment, succeed: bool) -> bool:
        ...

    @abstractmethod
    def verify_webhook(
        self, payload: bytes, sig_header: str | None, headers: dict | None = None,
    ) -> dict:
        ...

    def webhook_gate_secret(self) -> str:
        """非 dev 环境 webhook 验签门禁密钥（stripe=webhook 签名密钥 / paypal=webhook_id）"""
        return ""


class MockProvider(PaymentProvider):
    name = "mock"

    def create_intent(self, order, amount_cents: int) -> dict:
        pi = "PI_" + uuid.uuid4().hex
        # redirect_url：前端暂无 /pay-mock 假跳转页 → 返回空串维持现状（不跳转）
        return {"payment_intent": pi, "client_secret": f"{pi}_secret_mock",
                "redirect_url": ""}

    def confirm(self, order, payment, succeed: bool) -> bool:
        return succeed

    def verify_webhook(
        self, payload: bytes, sig_header: str | None, headers: dict | None = None,
    ) -> dict:
        return json.loads(payload.decode("utf-8"))


class StripeProvider(PaymentProvider):
    name = "stripe"

    def __init__(self, cfg: dict | None = None) -> None:
        # cfg 为显式解析结果（get_provider/_resolve_provider 传入）；None=调用时实时解析
        # （零参构造兼容测试/直用场景，字段经 property 每次取值——配置热更新即时生效）
        self._cfg = cfg

    def _c(self) -> dict:
        return self._cfg if self._cfg is not None else resolve_pay_config()

    @property
    def key(self) -> str:
        return self._c().get("stripe_key", "")

    @property
    def webhook_secret(self) -> str:
        return self._c().get("stripe_webhook_secret", "")

    @property
    def klarna(self) -> bool:
        return bool(self._c().get("stripe_klarna"))

    def _sdk(self):
        try:
            import stripe
        except ImportError as exc:
            raise ProviderUnavailable("stripe package not installed") from exc
        stripe.api_key = self.key
        return stripe

    def create_intent(self, order, amount_cents: int) -> dict:
        stripe = self._sdk()
        kwargs = {
            "amount": amount_cents,
            "currency": "usd",
            "metadata": {"order_no": order.order_no},
            # 时变幂等键：固定 order_no 会让失败重试永远取回同一笔失败 PI（用户卡死）；
            # 加时间戳后每次重试建新 PI（上限 255 字符，order_no 20 + 冒号 + 10 位时间戳安全）
            "idempotency_key": f"{order.order_no}:{int(time.time())}",
        }
        if self.klarna:
            kwargs["payment_method_types"] = ["card", "klarna"]
        intent = stripe.PaymentIntent.create(**kwargs)
        return {"payment_intent": intent.id, "client_secret": intent.client_secret}

    def create_checkout(self, order_no: str, amount_cents: int, site_url: str) -> dict:
        """Hosted Checkout 会话（stripe.checkout.Session.create）：
        成功回跳 {site_url}/success?no=订单号&session_id={CHECKOUT_SESSION_ID}，
        取消回跳 {site_url}/checkout?canceled=1；无 key 抛 ProviderUnavailable。"""
        stripe = self._sdk()
        if not self.key:
            raise ProviderUnavailable("stripe key absent")
        base = site_url.rstrip("/")
        session = stripe.checkout.Session.create(
            mode="payment",
            success_url=f"{base}/success?no={order_no}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/checkout?canceled=1",
            client_reference_id=order_no,
            metadata={"order_no": order_no},
            line_items=[{
                "quantity": 1,
                "price_data": {
                    "currency": "usd",
                    "unit_amount": amount_cents,
                    "product_data": {"name": f"GLOWMAG order {order_no}"},
                },
            }],
        )
        return {"checkout_session_id": session.id, "redirect_url": session.url}

    def confirm(self, order, payment, succeed: bool) -> bool:
        raise NotImplementedError("stripe payments are driven by webhook events")

    def verify_webhook(
        self, payload: bytes, sig_header: str | None, headers: dict | None = None,
    ) -> dict:
        stripe = self._sdk()
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, self.webhook_secret)
        except Exception as exc:
            raise InvalidSignatureError(str(exc)) from exc
        obj = ((event.get("data") or {}).get("object") or {})
        if not ((obj.get("metadata") or {}).get("order_no")):
            raise WebhookVerificationError("order_no_missing")
        return event

    def webhook_gate_secret(self) -> str:
        return self.webhook_secret


class PayPalProvider(PaymentProvider):
    """PayPal Orders v2 Provider —— httpx 直调 REST，无 SDK 依赖，凭据缺失即不可用。"""

    name = "paypal"

    def __init__(self, cfg: dict | None = None) -> None:
        self._cfg = cfg
        c = self._c()
        if not (c.get("paypal_client_id") and c.get("paypal_secret")):
            raise ProviderUnavailable("paypal credentials absent")

    def _c(self) -> dict:
        return self._cfg if self._cfg is not None else resolve_pay_config()

    @property
    def client_id(self) -> str:
        return self._c().get("paypal_client_id", "")

    @property
    def secret(self) -> str:
        return self._c().get("paypal_secret", "")

    @property
    def base(self) -> str:
        return self._c().get("paypal_base") or "https://api-m.sandbox.paypal.com"

    @property
    def webhook_id(self) -> str:
        return self._c().get("paypal_webhook_id", "")

    def _client(self):
        try:
            import httpx
        except ImportError as exc:
            raise ProviderUnavailable("httpx package not installed") from exc
        return httpx.Client(timeout=30.0)

    def _token(self, client) -> str:
        resp = client.post(
            f"{self.base}/v2/oauth2/token",
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.secret),
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def create_intent(self, order, amount_cents: int) -> dict:
        with self._client() as client:
            token = self._token(client)
            resp = client.post(
                f"{self.base}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    # 时变幂等键（与 Stripe 同因）：固定 order_no 失败重试永远取回旧失败单
                    "PayPal-Request-Id": f"{order.order_no}:{int(time.time())}",
                },
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{
                        "amount": {
                            "currency_code": "USD",
                            "value": f"{amount_cents / 100:.2f}",
                        },
                        "custom_id": order.order_no,
                        "metadata": {"order_no": order.order_no},
                    }],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        approve = next(
            (str(link.get("href")) for link in data.get("links") or []
             if link.get("rel") == "approve"),
            "",
        )
        pid = data.get("id") or ""
        return {"payment_intent": pid, "client_secret": approve or f"{pid}_paypal",
                "redirect_url": approve}

    def confirm(self, order, payment, succeed: bool) -> bool:
        raise NotImplementedError("paypal payments are driven by webhook events")

    def verify_webhook(
        self, payload: bytes, sig_header: str | None, headers: dict | None = None,
    ) -> dict:
        """真实验签：携带 webhook_id + paypal-transmission-* 请求头 POST
        /v1/notifications/verify-webhook-signature，校验 verification_status == VERIFIED。
        webhook_id 未配置（dev 降级，非 dev 由 handle_webhook 门禁 400 拒绝）时保持
        原结构桩行为：事件结构（id/type 必填）+ webhook_id 匹配（双方均配置时）。"""
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise WebhookVerificationError("invalid_payload") from exc
        if not isinstance(event, dict) or not event.get("id") or not event.get("type"):
            raise WebhookVerificationError("invalid_event")
        expected = self.webhook_id
        if expected and event.get("webhook_id") != expected:
            raise InvalidSignatureError("webhook_id_mismatch")
        if not expected:
            return event
        hdr = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        fields = {
            "transmission_id": hdr.get("paypal-transmission-id"),
            "transmission_time": hdr.get("paypal-transmission-time"),
            "transmission_sig": hdr.get("paypal-transmission-sig"),
            "cert_url": hdr.get("paypal-cert-url"),
            "auth_algo": hdr.get("paypal-auth-algo"),
        }
        if not all(fields.values()):
            raise InvalidSignatureError("paypal transmission headers missing")
        with self._client() as client:
            token = self._token(client)
            resp = client.post(
                f"{self.base}/v1/notifications/verify-webhook-signature",
                headers={"Authorization": f"Bearer {token}"},
                json={"webhook_id": expected, "webhook_event": event, **fields},
            )
            resp.raise_for_status()
            status = (resp.json() or {}).get("verification_status")
        if status != "VERIFIED":
            raise InvalidSignatureError(f"paypal_verify_status:{status}")
        return event

    def webhook_gate_secret(self) -> str:
        return self.webhook_id


def normalize_event(event) -> dict:
    data = event.get("data") or {}
    if isinstance(data, dict) and isinstance(data.get("object"), dict):
        obj = data["object"] or {}
        # charge.refunded 金额口径：amount_refunded 是累计值（直接当本次退款会重复入账）。
        # 优先取本次退款对象 refunds.data[0].amount；同时透传 cumulative_refunded（若有）
        # 供调用方按 delta = cumulative - 已记账 refunded_amount 求本次增量。
        refund_rows = (obj.get("refunds") or {}).get("data") \
            if isinstance(obj.get("refunds"), dict) else None
        this_refund = (
            refund_rows[0].get("amount")
            if isinstance(refund_rows, list) and refund_rows
            and isinstance(refund_rows[0], dict) else None
        )
        out = {
            "id": event.get("id") or "",
            "type": event.get("type") or "",
            "data": {
                "payment_intent": obj.get("payment_intent") or obj.get("id"),
                "amount": (
                    this_refund if this_refund is not None
                    else obj.get("amount_refunded") or obj.get("amount")
                ),
                "metadata": obj.get("metadata") or {},
            },
        }
        if obj.get("amount_refunded") is not None:
            out["data"]["cumulative_refunded"] = obj.get("amount_refunded")
        return out
    return {
        "id": event.get("id") or "",
        "type": event.get("type") or "",
        "data": data if isinstance(data, dict) else {},
    }


_provider: PaymentProvider | None = None
_provider_sig: tuple | None = None
_mock_warned = False
_paypal_warned = False


def _cfg_sig(cfg: dict) -> tuple:
    """配置指纹（缓存失效依据）：任一字段变化即重建 provider——后台保存 payment_config
    后热生效，无需重启也无需显式清缓存（多 worker 部署同样自愈）"""
    return tuple(sorted((k, str(v)) for k, v in cfg.items()))


def reset_provider_cache() -> None:
    """主动失效 provider 缓存（后台保存支付配置后调用；多 worker 场景其余进程靠
    _cfg_sig 指纹比对兜底）"""
    global _provider, _provider_sig
    _provider = None
    _provider_sig = None


def get_provider(db=None) -> PaymentProvider:
    global _provider, _provider_sig, _mock_warned, _paypal_warned
    cfg = resolve_pay_config(db)
    sig = _cfg_sig(cfg)
    if _provider is not None and sig == _provider_sig:
        return _provider
    _provider, _provider_sig = None, None
    if cfg.get("stripe_key"):
        try:
            import stripe  # noqa: F401
            _provider = StripeProvider(cfg)
            _provider_sig = sig
            return _provider
        except ImportError:
            logger.warning("stripe key set but package missing, using mock provider")
    if cfg.get("paypal_client_id") and cfg.get("paypal_secret"):
        try:
            import httpx  # noqa: F401
            _provider = PayPalProvider(cfg)
            _provider_sig = sig
            return _provider
        except ImportError:
            logger.warning("paypal credentials set but httpx missing, using mock provider")
    elif (cfg.get("paypal_client_id") or cfg.get("paypal_secret")) and not _paypal_warned:
        logger.warning("paypal credentials incomplete (client_id/secret), skipping paypal provider")
        _paypal_warned = True
    if not _mock_warned:
        logger.warning("stripe key absent, using mock provider")
        _mock_warned = True
    _provider = MockProvider()
    _provider_sig = sig
    return _provider


def available_providers(db=None) -> list[str]:
    cfg = resolve_pay_config(db)
    names: list[str] = []
    if cfg.get("stripe_key"):
        try:
            import stripe  # noqa: F401
            names.append("stripe(klarna)" if cfg.get("stripe_klarna") else "stripe")
        except ImportError:
            pass
    if cfg.get("paypal_client_id") and cfg.get("paypal_secret"):
        try:
            import httpx  # noqa: F401
            names.append("paypal")
        except ImportError:
            pass
    # mock 仅在开关放行时可见（后台 settings mock_pay / GM_MOCK_PAY 环境变量，默认 dev）：
    # 无真实 provider 且开关关闭时空列表（前端隐藏支付入口）
    return names or (["mock"] if mock_pay_enabled(db) else [])
