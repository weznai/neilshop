"""折扣码校验 —— B(结算引擎)与 C(营销API)的公共契约，集成者持有，路由层不得复制实现
MVP 简化：applies_to 范围限定暂不生效（只按小门票价门槛），seed 时注明
"""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import DiscountCode, DiscountRedemption, Order


def validate_code(
    db: Session,
    code: str,
    subtotal_cents: int,
    *,
    email: str | None = None,
    user_id: int | None = None,
) -> tuple[bool, int, bool, str]:
    """返回 (valid, discount_cents, free_shipping, reason)"""
    code = (code or "").strip().upper()
    if not code:
        return False, 0, False, "empty"

    dc = db.query(DiscountCode).filter(DiscountCode.code == code).first()
    if not dc or not dc.is_active:
        return False, 0, False, "code_not_found"

    now = utcnow()
    if dc.starts_at and now < dc.starts_at:
        return False, 0, False, "not_started"
    if dc.ends_at and now > dc.ends_at:
        return False, 0, False, "expired"
    if dc.usage_limit is not None and dc.used_count >= dc.usage_limit:
        return False, 0, False, "usage_limit"
    if subtotal_cents < (dc.min_subtotal or 0):
        return False, 0, False, "min_subtotal"

    if dc.first_order_only and email:
        # 首单判定：email 或 user_id 任一命中既有有效订单（已取消 status=8 不算）即非首单。
        # 归一 strip+lower 与下单落库口径一致；user_id 为 None 时只按 email 匹配
        email_norm = email.strip().lower()
        conds = [Order.email == email_norm]
        if user_id:
            conds.append(Order.user_id == user_id)
        placed = (
            db.query(Order.id)
            .filter(Order.status != 8, or_(*conds))  # 已取消订单不算“已下单”
        )
        if db.query(placed.exists()).scalar():
            return False, 0, False, "first_order_only"

    if email and dc.per_user_limit:
        used = (
            db.query(DiscountRedemption)
            .filter(DiscountRedemption.code_id == dc.id,
                    DiscountRedemption.email == email.strip().lower())
            .count()
        )
        if used >= dc.per_user_limit:
            return False, 0, False, "per_user_limit"

    if dc.type == 1:  # 百分比
        disc = subtotal_cents * int(dc.value) // 100
        if dc.max_discount:
            disc = min(disc, dc.max_discount)
    elif dc.type == 2:  # 固定金额
        disc = min(int(dc.value), subtotal_cents)
    else:  # 免邮
        return True, 0, True, "ok"

    return True, min(disc, subtotal_cents), False, "ok"
