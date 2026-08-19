"""支付 Provider 抽象层 —— 无 GM_STRIPE_KEY 时 MockProvider（行为对齐原 mock 版）；
设置 GM_STRIPE_KEY / GM_STRIPE_WEBHOOK_SECRET 并安装 stripe 包后自动切换 StripeProvider，
缺包时惰性导入失败降级 mock 并告警。
Klarna：不建独立 Provider —— GM_STRIPE_KLARNA=1 时 StripeProvider 的 PaymentIntent
附带 payment_method_types=["card","klarna"]；Klarna 经 Stripe 仅在 US/UK/DE/AT/BE/NL/
SE/NO/FI/DK 等部分地区可用，以 Stripe 账户后台实际开通为准。
PayPal：GM_PAYPAL_CLIENT_ID + GM_PAYPAL_SECRET 齐全且 httpx 可用时启用 PayPalProvider
（Orders v2 REST 直调，GM_PAYPAL_BASE 默认沙箱）。选择优先级 stripe > paypal > mock，
缺凭据/缺包逐级降级，每个不可用原因一次性 warning。"""

import json
import logging
import uuid
from abc import ABC, abstractmethod

from app.core.config import settings

logger = logging.getLogger("glowmag.payments")


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
    def verify_webhook(self, payload: bytes, sig_header: str | None) -> dict:
        ...


class MockProvider(PaymentProvider):
    name = "mock"

    def create_intent(self, order, amount_cents: int) -> dict:
        pi = "PI_" + uuid.uuid4().hex
        return {"payment_intent": pi, "client_secret": f"{pi}_secret_mock"}

    def confirm(self, order, payment, succeed: bool) -> bool:
        return succeed

    def verify_webhook(self, payload: bytes, sig_header: str | None) -> dict:
        return json.loads(payload.decode("utf-8"))


class StripeProvider(PaymentProvider):
    name = "stripe"

    def __init__(self) -> None:
        self.key = settings.stripe_key
        self.webhook_secret = settings.stripe_webhook_secret

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
            "idempotency_key": order.order_no,
        }
        if settings.stripe_klarna:
            kwargs["payment_method_types"] = ["card", "klarna"]
        intent = stripe.PaymentIntent.create(**kwargs)
        return {"payment_intent": intent.id, "client_secret": intent.client_secret}

    def confirm(self, order, payment, succeed: bool) -> bool:
        raise NotImplementedError("stripe payments are driven by webhook events")

    def verify_webhook(self, payload: bytes, sig_header: str | None) -> dict:
        stripe = self._sdk()
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, self.webhook_secret)
        except Exception as exc:
            raise InvalidSignatureError(str(exc)) from exc
        obj = ((event.get("data") or {}).get("object") or {})
        if not ((obj.get("metadata") or {}).get("order_no")):
            raise WebhookVerificationError("order_no_missing")
        return event


class PayPalProvider(PaymentProvider):
    """PayPal Orders v2 Provider —— httpx 直调 REST，无 SDK 依赖，凭据缺失即不可用。"""

    name = "paypal"

    def __init__(self) -> None:
        if not (settings.paypal_client_id and settings.paypal_secret):
            raise ProviderUnavailable("paypal credentials absent")
        self.client_id = settings.paypal_client_id
        self.secret = settings.paypal_secret
        self.base = settings.paypal_base or "https://api-m.sandbox.paypal.com"

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
                    "PayPal-Request-Id": order.order_no,
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
        return {"payment_intent": pid, "client_secret": approve or f"{pid}_paypal"}

    def confirm(self, order, payment, succeed: bool) -> bool:
        raise NotImplementedError("paypal payments are driven by webhook events")

    def verify_webhook(self, payload: bytes, sig_header: str | None) -> dict:
        """结构桩：真实实现应携带 webhook_id + paypal-transmission-* headers 调
        POST /v1/notifications/verify-webhook-signature 校验 VERIFIED（CA cert 或
        transmission 签名）；此处简化为 transmission header 存在性 + 事件结构
        （id/type 必填）+ webhook_id 匹配（双方均配置时）。"""
        if not sig_header:
            raise InvalidSignatureError("paypal transmission headers missing")
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise WebhookVerificationError("invalid_payload") from exc
        if not isinstance(event, dict) or not event.get("id") or not event.get("type"):
            raise WebhookVerificationError("invalid_event")
        expected = getattr(settings, "paypal_webhook_id", "")
        if expected and event.get("webhook_id") != expected:
            raise InvalidSignatureError("webhook_id_mismatch")
        return event


def normalize_event(event) -> dict:
    data = event.get("data") or {}
    if isinstance(data, dict) and isinstance(data.get("object"), dict):
        obj = data["object"] or {}
        return {
            "id": event.get("id") or "",
            "type": event.get("type") or "",
            "data": {
                "payment_intent": obj.get("payment_intent") or obj.get("id"),
                "amount": obj.get("amount_refunded") or obj.get("amount"),
                "metadata": obj.get("metadata") or {},
            },
        }
    return {
        "id": event.get("id") or "",
        "type": event.get("type") or "",
        "data": data if isinstance(data, dict) else {},
    }


_provider: PaymentProvider | None = None
_mock_warned = False
_paypal_warned = False


def get_provider() -> PaymentProvider:
    global _provider, _mock_warned, _paypal_warned
    if _provider is not None:
        return _provider
    if settings.stripe_key:
        try:
            import stripe  # noqa: F401
            _provider = StripeProvider()
            return _provider
        except ImportError:
            logger.warning("stripe key set but package missing, using mock provider")
    if settings.paypal_client_id and settings.paypal_secret:
        try:
            import httpx  # noqa: F401
            _provider = PayPalProvider()
            return _provider
        except ImportError:
            logger.warning("paypal credentials set but httpx missing, using mock provider")
    elif (settings.paypal_client_id or settings.paypal_secret) and not _paypal_warned:
        logger.warning("paypal credentials incomplete (client_id/secret), skipping paypal provider")
        _paypal_warned = True
    if not _mock_warned:
        logger.warning("stripe key absent, using mock provider")
        _mock_warned = True
    _provider = MockProvider()
    return _provider


def available_providers() -> list[str]:
    names: list[str] = []
    if settings.stripe_key:
        try:
            import stripe  # noqa: F401
            names.append("stripe(klarna)" if settings.stripe_klarna else "stripe")
        except ImportError:
            pass
    if settings.paypal_client_id and settings.paypal_secret:
        try:
            import httpx  # noqa: F401
            names.append("paypal")
        except ImportError:
            pass
    return names or ["mock"]
