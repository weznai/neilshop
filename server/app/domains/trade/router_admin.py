"""后台交易/履约/库存路由（薄路由，/api/admin/trade）—— 订单发货/送达/退款、RMA 队列推进、
库存调整与流水；业务与退款公共路径在 service_admin。"""

import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_perm, require_superadmin
from app.domains.trade import service_admin, service_exchanges
from app.domains.trade.schemas import (
    ExchangeRejectRequest, NoteIn, OrderAddressUpdateIn, RefundRequest, RmaRejectRequest,
    RmaRefundRequest, ShipRequest, ShippingRateIn, ShippingRateUpdateIn, StockAdjustRequest,
)
from app.models import Setting, User

router = APIRouter(prefix="/api/admin/trade", tags=["admin-trade"])


def _parse_order_status(raw: Optional[str]) -> tuple[Optional[int], Optional[list[int]]]:
    """状态过滤解析（订单/RMA 列表共用）：含逗号拆分转 int 列表（任一段非法 422 invalid status），
    单值保持 int 语义（与旧 status: int 行为一致）；空/未传 → 不过滤"""
    if raw is None or raw.strip() == "":
        return None, None
    if "," in raw:
        try:
            return None, [int(x) for x in raw.split(",")]
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid status")
    try:
        return int(raw), None
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid status")


@router.get("/orders")
def list_orders(
    status: Optional[str] = None,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: Optional[int] = Query(default=None, ge=1),
    admin: User = Depends(require_perm("trade:read")),
    db: Session = Depends(get_db),
):
    status_eq, status_in = _parse_order_status(status)
    return service_admin.list_orders(
        db, status_eq, q, page, per_page, date_from, date_to, sort,
        status_in=status_in,
    )


@router.get("/orders/{order_no}")
def order_detail(order_no: str, admin: User = Depends(require_perm("trade:read")), db: Session = Depends(get_db)):
    return service_admin.order_detail(db, order_no)


@router.post("/orders/{order_no}/ship")
def ship_order(order_no: str, body: ShipRequest, admin: User = Depends(require_perm("trade:ship")), db: Session = Depends(get_db)):
    return service_admin.ship_order(db, admin, order_no, body)


@router.post("/orders/{order_no}/prepare")
def prepare_order(order_no: str, admin: User = Depends(require_perm("trade:ship")), db: Session = Depends(get_db)):
    return service_admin.prepare_order(db, admin, order_no)


@router.post("/orders/{order_no}/mark-completed")
def mark_completed(order_no: str, admin: User = Depends(require_perm("trade:manage")), db: Session = Depends(get_db)):
    return service_admin.mark_completed(db, admin, order_no)


@router.put("/orders/{order_no}/address")
def update_order_address(
    order_no: str,
    body: OrderAddressUpdateIn | None = None,
    admin: User = Depends(require_perm("trade:manage")),
    db: Session = Depends(get_db),
):
    return service_admin.update_order_address(db, admin, order_no, body)


@router.post("/orders/{order_no}/mark-delivered")
def mark_delivered(order_no: str, admin: User = Depends(require_perm("trade:ship")), db: Session = Depends(get_db)):
    return service_admin.mark_delivered(db, admin, order_no)


@router.post("/orders/{order_no}/refund")
def refund_order(
    order_no: str,
    body: RefundRequest | None = None,
    admin: User = Depends(require_perm("trade:refund")),
    db: Session = Depends(get_db),
):
    return service_admin.refund_order(db, admin, order_no, body)


@router.post("/orders/{order_no}/cancel")
def cancel_order(order_no: str, admin: User = Depends(require_perm("trade:manage")), db: Session = Depends(get_db)):
    return service_admin.cancel_order(db, admin, order_no)


@router.post("/orders/{order_no}/note")
def add_order_note(order_no: str, body: NoteIn, admin: User = Depends(require_perm("trade:manage")), db: Session = Depends(get_db)):
    return service_admin.add_order_note(db, admin, order_no, body)


@router.get("/rmas")
def list_rmas(
    status: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    admin: User = Depends(require_perm("rma:read")),
    db: Session = Depends(get_db),
):
    # 状态过滤支持 CSV（"2,4" → 多状态队列），与订单列表 _parse_order_status 同口径
    status_eq, status_in = _parse_order_status(status)
    return service_admin.list_rmas(db, status_eq, page, per_page, q, status_in=status_in)


@router.post("/rmas/{rma_no}/approve")
def approve_rma(rma_no: str, admin: User = Depends(require_perm("rma:manage")), db: Session = Depends(get_db)):
    return service_admin.approve_rma(db, admin, rma_no)


@router.post("/rmas/{rma_no}/reject")
def reject_rma(
    rma_no: str,
    body: RmaRejectRequest | None = None,
    admin: User = Depends(require_perm("rma:manage")),
    db: Session = Depends(get_db),
):
    return service_admin.reject_rma(db, admin, rma_no, body.reason if body else None)


@router.post("/rmas/{rma_no}/receive")
def receive_rma(rma_no: str, admin: User = Depends(require_perm("rma:receive")), db: Session = Depends(get_db)):
    return service_admin.receive_rma(db, admin, rma_no)


@router.post("/rmas/{rma_no}/refund")
def refund_rma(
    rma_no: str,
    body: RmaRefundRequest | None = None,
    admin: User = Depends(require_perm("trade:refund")),
    db: Session = Depends(get_db),
):
    return service_admin.refund_rma(db, admin, rma_no, body)


@router.post("/stock/adjust")
def adjust_stock(body: StockAdjustRequest, admin: User = Depends(require_perm("stock:manage")), db: Session = Depends(get_db)):
    return service_admin.adjust_stock(db, admin, body)


@router.get("/stock/movements")
def stock_movements(
    variant_id: Optional[int] = None,
    type: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: Optional[int] = Query(default=None, ge=1),
    admin: User = Depends(require_perm("stock:read")),
    db: Session = Depends(get_db),
):
    return service_admin.stock_movements(
        db, variant_id, page, type, date_from, date_to, per_page,
    )


@router.get("/stock/low")
def low_stock(
    threshold: int = 8,
    admin: User = Depends(require_perm("stock:read")),
    db: Session = Depends(get_db),
):
    return service_admin.low_stock(db, threshold)


@router.get("/exchanges")
def list_exchanges(
    status: Optional[int] = None,
    q: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    admin: User = Depends(require_perm("rma:read")),
    db: Session = Depends(get_db),
):
    return service_exchanges.admin_list_exchanges(db, status, page, size, q)


@router.post("/exchanges/{exchange_no}/approve")
def approve_exchange(
    exchange_no: str, admin: User = Depends(require_perm("rma:manage")), db: Session = Depends(get_db),
):
    return service_exchanges.approve_exchange(db, admin, exchange_no)


@router.post("/exchanges/{exchange_no}/reject")
def reject_exchange(
    exchange_no: str,
    body: ExchangeRejectRequest | None = None,
    admin: User = Depends(require_perm("rma:manage")),
    db: Session = Depends(get_db),
):
    return service_exchanges.reject_exchange(
        db, admin, exchange_no, body.reason if body else None)


@router.post("/exchanges/{exchange_no}/mark-paid")
def mark_paid_exchange(
    exchange_no: str, admin: User = Depends(require_perm("trade:refund")), db: Session = Depends(get_db),
):
    return service_exchanges.mark_paid_exchange(db, admin, exchange_no)


@router.post("/exchanges/{exchange_no}/ship")
def ship_exchange(
    exchange_no: str, body: ShipRequest,
    admin: User = Depends(require_perm("trade:ship")), db: Session = Depends(get_db),
):
    return service_exchanges.ship_exchange(db, admin, exchange_no, body)


@router.post("/exchanges/{exchange_no}/complete")
def complete_exchange(
    exchange_no: str, admin: User = Depends(require_perm("rma:manage")), db: Session = Depends(get_db),
):
    return service_exchanges.complete_exchange(db, admin, exchange_no)


# ---------- 运费模板管理 ----------

@router.get("/shipping-rates")
def list_shipping_rates(
    admin: User = Depends(require_perm("trade:read")), db: Session = Depends(get_db),
):
    return service_admin.list_shipping_rates(db)


@router.post("/shipping-rates", status_code=201)
def create_shipping_rate(
    body: ShippingRateIn,
    admin: User = Depends(require_perm("trade:manage")), db: Session = Depends(get_db),
):
    return service_admin.create_shipping_rate(db, admin, body)


@router.put("/shipping-rates/{rate_id}")
def update_shipping_rate(
    rate_id: int,
    body: ShippingRateUpdateIn,
    admin: User = Depends(require_perm("trade:manage")), db: Session = Depends(get_db),
):
    return service_admin.update_shipping_rate(db, admin, rate_id, body)


@router.delete("/shipping-rates/{rate_id}")
def delete_shipping_rate(
    rate_id: int,
    admin: User = Depends(require_perm("trade:manage")), db: Session = Depends(get_db),
):
    return service_admin.delete_shipping_rate(db, admin, rate_id)


# ---------- 支付通道配置（settings key=payment_config，覆盖 GM_STRIPE_*/GM_PAYPAL_* 环境变量） ----------

def _pay_row(db: Session) -> Setting | None:
    return db.get(Setting, "payment_config")


def _site_url(db: Session) -> str:
    """站点根地址（webhook 回调地址提示用）：ops settings site_url/base_url > GM_SITE_URL"""
    for key in ("site_url", "base_url"):
        row = db.get(Setting, key)
        if row is not None and row.value:
            val = str(row.value).strip().rstrip("/")
            if val.startswith(("http://", "https://")):
                return val
    return (os.getenv("GM_SITE_URL") or "").strip().rstrip("/")


@router.get("/payments/config")
def get_payments_config(admin: User = Depends(require_perm("settings:manage")), db: Session = Depends(get_db)):
    """当前生效支付配置（凭据掩码回显）+ 来源标记（db=后台配置 / env=环境变量 / 空=未配置）"""
    from app.services import payment_provider as pp

    row = _pay_row(db)
    dbcfg = row.value if (row and isinstance(row.value, dict)) else {}
    return _payments_config_payload(db, row, dbcfg, pp.resolve_pay_config(db))


def _payments_config_payload(db: Session, row, dbcfg: dict, cfg: dict) -> dict:
    from app.core.config import settings
    from app.services import payment_provider as pp

    def _src(db_val: bool, cfg_val: str) -> str:
        return "db" if db_val else ("env" if cfg_val else "")

    stripe_key = cfg.get("stripe_key", "")
    key_mode = "test" if stripe_key.startswith("sk_test_") else ("live" if stripe_key.startswith("sk_live_") else "")
    payload = {
        "stripe": {
            "key_set": bool(stripe_key),
            "key_masked": pp.mask_secret(stripe_key),
            "key_mode": key_mode,
            "webhook_secret_set": bool(cfg.get("stripe_webhook_secret")),
            "webhook_secret_masked": pp.mask_secret(cfg.get("stripe_webhook_secret") or ""),
            "klarna": bool(cfg.get("stripe_klarna")),
            "source": _src(bool(dbcfg.get("stripe_key")), stripe_key),
        },
        "paypal": {
            "client_id": cfg.get("paypal_client_id", ""),
            "secret_set": bool(cfg.get("paypal_secret")),
            "secret_masked": pp.mask_secret(cfg.get("paypal_secret") or ""),
            "base": cfg.get("paypal_base") or "https://api-m.sandbox.paypal.com",
            "webhook_id_set": bool(cfg.get("paypal_webhook_id")),
            "webhook_id_masked": pp.mask_secret(cfg.get("paypal_webhook_id") or ""),
            "source": _src(bool(dbcfg.get("paypal_client_id")), cfg.get("paypal_client_id", "")),
        },
        "package": {"stripe": pp._importable("stripe"), "httpx": pp._importable("httpx")},
        "effective": {
            "provider": pp.get_provider(db).name,
            "available": pp.available_providers(db),
            "mock_pay": pp.mock_pay_enabled(db),
            "env": settings.env,
        },
        "updated_at": row.updated_at if row else None,
        "updated_by": row.updated_by if row else None,
    }
    site = _site_url(db)
    payload["effective"]["webhook_url"] = f"{site}/api/payments/webhook" if site else ""
    return payload


@router.put("/payments/config")
def save_payments_config(
    body: dict, admin: User = Depends(require_superadmin), db: Session = Depends(get_db),
):
    """保存支付通道配置（仅超管）：字段存在才更新，空串=清除该字段（回落环境变量），
    保存后 reset_provider_cache 立即生效。凭据长度/前缀校验防粘贴错误。"""
    from app.domains.support.service import log_admin
    from app.services import payment_provider as pp

    STR = {
        "stripe_key": 255, "stripe_webhook_secret": 255,
        "paypal_client_id": 128, "paypal_secret": 128,
        "paypal_base": 200, "paypal_webhook_id": 128,
    }
    row = _pay_row(db)
    cur = dict(row.value) if (row and isinstance(row.value, dict)) else {}

    for k, hi in STR.items():
        if k in body:
            v = str(body.get(k) or "").strip()
            if len(v) > hi:
                raise HTTPException(status_code=422, detail=f"{k} 超长（≤{hi} 字符）")
            cur[k] = v
    if "stripe_key" in cur and cur["stripe_key"] and not cur["stripe_key"].startswith("sk_"):
        raise HTTPException(status_code=422, detail="stripe_key 需以 sk_ 开头（sk_test_ / sk_live_）")
    if "stripe_webhook_secret" in cur and cur["stripe_webhook_secret"] \
            and not cur["stripe_webhook_secret"].startswith("whsec_"):
        raise HTTPException(status_code=422, detail="stripe_webhook_secret 需以 whsec_ 开头")
    if "paypal_base" in cur and cur["paypal_base"] \
            and not cur["paypal_base"].startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="paypal_base 需以 http(s):// 开头")
    if "stripe_klarna" in body:
        if not isinstance(body.get("stripe_klarna"), bool):
            raise HTTPException(status_code=422, detail="stripe_klarna 需为布尔值")
        cur["stripe_klarna"] = body["stripe_klarna"]

    # 空值字段不入库（对齐 llm_config）：DB 无该字段即回落环境变量——「后台清除 = 回到 env 配置」
    clean = {k: v for k, v in cur.items() if v not in ("", None)}
    if row:
        row.value = clean
        row.updated_by = admin.id
    else:
        db.add(Setting(key="payment_config", value=clean,
                       description="支付通道配置（Stripe/PayPal，覆盖环境变量）", updated_by=admin.id))
    log_admin(db, admin, "setting", "payment_config", 0, {
        "fields": sorted(body.keys()),
        "secrets_touched": [k for k in body if k in pp.PAY_SECRET_FIELDS],
    })
    db.commit()
    pp.reset_provider_cache()
    return _payments_config_payload(db, _pay_row(db), clean, pp.resolve_pay_config(db))


@router.post("/payments/test")
def test_payments_connectivity(
    body: dict | None = None, admin: User = Depends(require_perm("settings:manage")), db: Session = Depends(get_db),
):
    """连通性测试（真实外呼一次最小 API）：body.provider=stripe|paypal（缺省测当前默认链），
    返回 ok/延迟/密钥模式；未配置凭据或缺包给出具体原因。"""
    from app.services import payment_provider as pp

    cfg = pp.resolve_pay_config(db)
    target = (body or {}).get("provider") or pp.get_provider(db).name
    t0 = time.monotonic()
    if target == "stripe":
        if not cfg.get("stripe_key"):
            return {"ok": False, "provider": "stripe", "reason": "未配置 Stripe 密钥"}
        try:
            import stripe
        except ImportError:
            return {"ok": False, "provider": "stripe",
                    "reason": "服务端未安装 stripe 包（容器内 pip install stripe 后重启）"}
        stripe.api_key = cfg["stripe_key"]
        try:
            bal = stripe.Balance.retrieve()
            ms = int((time.monotonic() - t0) * 1000)
            avail = sum(int(a.get("amount", 0)) for a in (getattr(bal, "available", None) or []))
            mode = "test" if cfg["stripe_key"].startswith("sk_test_") else "live"
            return {"ok": True, "provider": "stripe", "latency_ms": ms, "mode": mode,
                    "balance_cents": avail}
        except Exception as exc:
            ms = int((time.monotonic() - t0) * 1000)
            return {"ok": False, "provider": "stripe", "latency_ms": ms,
                    "reason": f"调用失败：{str(exc)[:160]}"}
    if target == "paypal":
        if not (cfg.get("paypal_client_id") and cfg.get("paypal_secret")):
            return {"ok": False, "provider": "paypal", "reason": "PayPal 凭据不完整（需 Client ID + Secret）"}
        try:
            provider = pp.PayPalProvider(cfg)
            with provider._client() as client:
                provider._token(client)
        except Exception as exc:
            ms = int((time.monotonic() - t0) * 1000)
            return {"ok": False, "provider": "paypal", "latency_ms": ms,
                    "reason": f"调用失败：{str(exc)[:160]}"}
        ms = int((time.monotonic() - t0) * 1000)
        base = cfg.get("paypal_base") or "https://api-m.sandbox.paypal.com"
        return {"ok": True, "provider": "paypal", "latency_ms": ms,
                "mode": "sandbox" if "sandbox" in base else "live"}
    return {"ok": False, "provider": target,
            "reason": "当前默认链为 mock（无真实通道可测），请指定 provider=stripe|paypal"}
