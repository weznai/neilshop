"""支付路由（薄路由）—— Provider 抽象下的 intent 创建 / mock-pay / webhook 幂等回调。
真实 Stripe 模式：设置环境变量 GM_STRIPE_KEY / GM_STRIPE_WEBHOOK_SECRET（并 pip install stripe）后自动启用；
PayPal 模式：GM_PAYPAL_CLIENT_ID / GM_PAYPAL_SECRET（GM_PAYPAL_BASE 默认沙箱）；Klarna：GM_STRIPE_KLARNA=1。
GET /api/payments/methods 为公开端点，返回当前可用支付方式供 checkout 渲染；create-intent 可选
provider 字段（stripe|paypal，缺省走默认链；非默认且不可用 → 400 provider_unavailable；
MockProvider 下任何取值回落 mock 并在响应标注 provider=mock）。
无密钥或缺包时回落 MockProvider，行为与原 mock 版完全一致。核心事务在 service_payments。"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user_optional
from app.domains.trade import service_payments
from app.domains.trade.schemas import CreateIntentRequest, MockPayRequest, WebhookRequest
from app.models import Payment, User
from app.services import payment_provider

router = APIRouter(prefix="/api/payments", tags=["payments"])


class CreateIntentBody(CreateIntentRequest):
    provider: str | None = None


_PROVIDER_LABELS = {
    "mock": "Mock Pay (dev)",
    "stripe": "Credit / Debit Card (Stripe)",
    "paypal": "PayPal",
}


def _resolve_provider(provider: str) -> payment_provider.PaymentProvider:
    default = payment_provider.get_provider()
    if default.name == "mock" or provider == default.name:
        # 回落分支：默认链是 mock（无真实凭据/缺包降级）——非 dev 直接拒绝而非静默降级
        if default.name == "mock" and settings.env != "dev":
            raise HTTPException(status_code=409, detail="mock_provider_disabled")
        return default
    if provider == "stripe":
        try:
            import stripe  # noqa: F401
            if not settings.stripe_key:
                raise payment_provider.ProviderUnavailable("stripe key absent")
            return payment_provider.StripeProvider()
        except (ImportError, payment_provider.ProviderUnavailable):
            raise HTTPException(status_code=400, detail="provider_unavailable")
    if provider == "paypal":
        try:
            import httpx  # noqa: F401
            return payment_provider.PayPalProvider()
        except (ImportError, payment_provider.ProviderUnavailable):
            raise HTTPException(status_code=400, detail="provider_unavailable")
    raise HTTPException(status_code=400, detail="provider_unavailable")


def _create_intent_via(
    db: Session, order_no: str, provider: payment_provider.PaymentProvider,
    *, user: Optional[User] = None, email: Optional[str] = None,
) -> dict:
    from app.domains.trade import repository as repo

    if provider.name == "mock" and settings.env != "dev":
        raise HTTPException(status_code=409, detail="mock_provider_disabled")
    order = service_payments._get_order(db, order_no)
    service_payments.ensure_order_owner(order, user, email)
    if order.status != 0:
        raise HTTPException(status_code=409, detail=f"order_not_pending:{order.status}")
    # 幂等：同单同 provider 已有 PENDING payment 直接复用返回，不堆积新行（跨 provider 建新）
    pending = repo.pending_payment_of_order(db, order.id, provider=provider.name)
    if pending:
        return {
            "payment_intent": pending.stripe_payment_intent,
            "client_secret": (
                pending.stripe_checkout_session
                or f"{pending.stripe_payment_intent}_secret_mock"
            ),
            "amount": pending.amount,
            "provider": provider.name,
            "redirect_url": "",
        }
    intent = provider.create_intent(order, order.grand_total)
    payment = Payment(
        order_id=order.id,
        stripe_payment_intent=intent["payment_intent"],
        stripe_checkout_session=(intent.get("client_secret") or "")[:255],
        amount=order.grand_total,
        status=0,
    )
    db.add(payment)
    db.commit()
    return {
        "payment_intent": payment.stripe_payment_intent,
        "client_secret": intent["client_secret"],
        "amount": payment.amount,
        "provider": provider.name,
        "redirect_url": intent.get("redirect_url", ""),
    }


@router.post("/create-intent")
def create_intent(
    body: CreateIntentBody,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    if body.provider:
        chosen = _resolve_provider(body.provider)
        if chosen.name == "mock":
            result = service_payments.create_intent(
                db, body.order_no, user=user, email=body.email)
            result["provider"] = "mock"
            return result
        return _create_intent_via(
            db, body.order_no, chosen, user=user, email=body.email)
    return service_payments.create_intent(
        db, body.order_no, user=user, email=body.email)


@router.get("/methods")
def payment_methods():
    providers = []
    for name in payment_provider.available_providers():
        pid = "stripe" if name.startswith("stripe") else name
        providers.append({
            "id": pid,
            "name": _PROVIDER_LABELS.get(pid, pid),
            "klarna": pid == "stripe" and bool(settings.stripe_klarna),
        })
    # 非 dev 无可用真实 provider → 空列表 + default=none（前端隐藏支付入口）
    default = payment_provider.get_provider().name if providers else "none"
    return {"providers": providers, "default": default}


@router.post("/mock-pay")
def mock_pay(
    body: MockPayRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    return service_payments.mock_pay(
        db, body.order_no, body.succeed, user=user, email=body.email)


@router.post("/webhook")
async def webhook(
    request: Request,
    body: WebhookRequest,
    db: Session = Depends(get_db),
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
):
    payload = await request.body()
    return service_payments.handle_webhook(db, payload, stripe_signature)
