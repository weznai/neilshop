"""购物车服务 —— 视图组装与加/改/删/合并（游客 X-Cart-Token，登录后合并，上限 99）"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.deps import resolve_cart
from app.domains.trade import repository as repo
from app.models import Cart, User, Variant


def _stock_status(v: Variant) -> str:
    if v.stock <= 0:
        return "out"
    if v.stock <= v.safety_stock:
        return "low"
    return "in"


def token_of(cart: Cart, token: str | None) -> str:
    return token or cart.session_id


def get_view(db: Session, cart: Cart, token: str | None) -> dict:
    token = token or cart.session_id
    entries = cart.items or []
    vids = [e.get("variantId") for e in entries if e.get("variantId")]
    variants = repo.variants_by_ids(db, vids)
    products = {}
    pids = {v.product_id for v in variants.values()}
    if pids:
        products = repo.products_by_ids(db, pids)
    items = []
    subtotal = 0
    for e in entries:
        v = variants.get(e.get("variantId"))
        p = products.get(v.product_id) if v else None
        # 失效行（变体停用/删除或商品下架）：不再静默吞掉 —— 带标记返回供前端
        # 展示"已下架"并提供删除，避免 preview/place 409 后 UI 无行可删的死锁
        if not v or not v.is_active or not p or p.status != 1:
            qty = int(e.get("qty", 0))
            items.append({
                "variant_id": e.get("variantId"),
                "product_id": v.product_id if v else None,
                "qty": qty,
                "price": int(v.price) if v else 0,
                "title": f"{p.title} · {v.option1_value}" if (p and v) else "",
                "variant_label": v.option1_value if v else "",
                "image": p.hero_image if p else None,
                "product_slug": p.slug if p else "",
                "stock": 0,
                "stock_status": "out",
                "line_total": 0,
                "inactive": True,
            })
            continue
        qty = int(e.get("qty", 0))
        line_total = v.price * qty
        subtotal += line_total
        items.append({
            "variant_id": v.id,
            "product_id": v.product_id,
            "qty": qty,
            "price": v.price,
            "title": f"{p.title} · {v.option1_value}",
            "variant_label": v.option1_value,
            "image": p.hero_image,
            "product_slug": p.slug,
            "stock": v.stock,
            "stock_status": _stock_status(v),
            "line_total": line_total,
        })
    return {"token": token, "items": items, "subtotal_cents": subtotal}


def _entries(cart: Cart) -> list[dict]:
    return [dict(e) for e in (cart.items or [])]


def _save(db: Session, cart: Cart, entries: list[dict]) -> None:
    # 弃购周期重置：回访改车（items 发生变化 = 新弃购周期开始）时清零已发计数，
    # 使三封阶梯从第 1 封重新起算（place 清车后用户再加购即命中）
    if cart.abandoned_mails_sent > 0 and (cart.items or []) != entries:
        cart.abandoned_mails_sent = 0
    cart.items = entries
    db.commit()


def add_item(db: Session, cart: Cart, token: str | None, variant_id: int, qty: int) -> dict:
    variant = repo.get_variant(db, variant_id)
    if not variant or not variant.is_active:
        raise HTTPException(status_code=404, detail="variant not found")
    entries = _entries(cart)
    current = next(
        (e for e in entries if e.get("variantId") == variant_id), None
    )
    new_qty = qty + (int(current["qty"]) if current else 0)
    if new_qty > variant.stock:
        raise HTTPException(status_code=409, detail="insufficient_stock")
    if current:
        current["qty"] = new_qty
    else:
        entries.append({"variantId": variant_id, "qty": qty})
    _save(db, cart, entries)
    return get_view(db, cart, token)


def add_batch(db: Session, cart: Cart, token: str | None, items: list) -> dict:
    """批量加购：复用 add_item 内部判定（变体存在/激活 + 累计数量不超库存），
    单件失败不回滚整体 —— 收集 failed:[{variant_id,reason}]，成功件一次性落库。
    同请求重复 variant_id 合并计数（逐条累计进 entries），added 去重只报一次。"""
    entries = _entries(cart)
    added: list[int] = []
    failed: list[dict] = []
    for it in items:
        variant = repo.get_variant(db, it.variant_id)
        if not variant or not variant.is_active:
            failed.append({"variant_id": it.variant_id, "reason": "variant_not_found"})
            continue
        current = next(
            (e for e in entries if e.get("variantId") == it.variant_id), None
        )
        new_qty = it.qty + (int(current["qty"]) if current else 0)
        if new_qty > variant.stock:
            failed.append({"variant_id": it.variant_id, "reason": "insufficient_stock"})
            continue
        if current:
            current["qty"] = new_qty
        else:
            entries.append({"variantId": it.variant_id, "qty": it.qty})
        if it.variant_id not in added:
            added.append(it.variant_id)
    if added:
        _save(db, cart, entries)
    view = get_view(db, cart, token)
    return {**view, "added": added, "failed": failed}


def update_item(db: Session, cart: Cart, token: str | None, variant_id: int, qty: int) -> dict:
    entries = _entries(cart)
    idx = next(
        (i for i, e in enumerate(entries) if e.get("variantId") == variant_id), None
    )
    if idx is None:
        raise HTTPException(status_code=404, detail="item not in cart")
    if qty == 0:
        entries.pop(idx)
    else:
        variant = repo.get_variant(db, variant_id)
        if not variant:
            raise HTTPException(status_code=404, detail="variant not found")
        if qty > variant.stock:
            raise HTTPException(status_code=409, detail="insufficient_stock")
        entries[idx]["qty"] = qty
    _save(db, cart, entries)
    return get_view(db, cart, token)


def delete_item(db: Session, cart: Cart, token: str | None, variant_id: int) -> dict:
    entries = _entries(cart)
    idx = next(
        (i for i, e in enumerate(entries) if e.get("variantId") == variant_id), None
    )
    if idx is None:
        raise HTTPException(status_code=404, detail="item not in cart")
    entries.pop(idx)
    _save(db, cart, entries)
    return get_view(db, cart, token)


def merge(db: Session, user: User, guest_token: str) -> tuple[dict, str]:
    guest = repo.find_guest_cart(db, guest_token)
    cart, token = resolve_cart(db, user, None)
    if guest and guest.id != cart.id:
        merged = {e.get("variantId"): int(e.get("qty", 0)) for e in cart.items or []}
        for e in guest.items or []:
            vid = e.get("variantId")
            if not vid:
                continue
            merged[vid] = min(99, merged.get(vid, 0) + int(e.get("qty", 0)))
        cart.items = [{"variantId": k, "qty": q} for k, q in merged.items()]
        db.delete(guest)
        db.commit()
    token = token or cart.session_id
    return get_view(db, cart, token), token
