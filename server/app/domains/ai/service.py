"""AI 域服务 —— 推荐算法（相关/热销/新品兜底）+ 客服 Agent（意图识别/FAQ 检索/订单查询脱敏）"""

import re

from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.enums import DiscountType
from app.models import DiscountCode, Product
from app.domains.ai import repository as repo
from app.domains.ai.schemas import (
    ChatIn, FALLBACK_REPLY, FAQ_CATEGORY, RULES, STATUS_TEXT, SUGGESTIONS,
)
from app.services.cache import cached


def _card(p: Product, reason: str) -> dict:
    return {
        "id": p.id,
        "slug": p.slug,
        "title": p.title,
        "price_min": p.price_min,
        "hero_image": p.hero_image,
        "rating": round(p.rating_avg / 100, 2),
        "sold_count": p.sold_count,
        "tags": p.tags or [],
        "reason": reason,
    }


@cached("ai:recommend")
def recommend_items(db: Session, *, product_id: int | None, cart_ids: list[int], size: int) -> list[dict]:
    items: list[dict] = []
    used: set[int] = set()

    def _take(rows, reason):
        for p in rows:
            if len(items) >= size:
                return
            if p.id in used:
                continue
            used.add(p.id)
            items.append(_card(p, reason))

    if product_id:
        base = repo.product_by_id(db, product_id)
        if base:
            used.add(base.id)
            _take(repo.same_category_bestsellers(db, base.category_id, base.id), "related")
    elif cart_ids:
        carts = repo.active_by_ids(db, cart_ids)
        used.update(c.id for c in carts)
        tags: set[str] = set()
        for c in carts:
            tags.update(c.tags or [])
        scored = []
        if tags:
            for p in repo.all_active(db):
                if p.id in used:
                    continue
                hits = len(tags & set(p.tags or []))
                if hits:
                    scored.append((-hits, -p.sold_count, p.id, p))
            scored.sort(key=lambda x: x[:3])
        if scored:
            _take([x[3] for x in scored], "related")
        elif carts:
            cats = {c.category_id for c in carts}
            _take(repo.category_bestsellers(db, cats), "related")

    _take(repo.hot_all(db), "hot")
    _take(repo.new_all(db), "new")
    return items


@cached("ai:hot")
def hot_items(db: Session, *, size: int) -> list[dict]:
    return [_card(p, "hot") for p in repo.hot_top(db, size)]


def _money(cents: int) -> str:
    return f"${cents / 100:.2f}"


def _faq_reply(db: Session, category: int) -> str | None:
    rows = repo.faq_top3(db, category)
    if not rows:
        return None
    return "\n\n".join(f"**{r.question}**\n{r.answer_md}" for r in rows)


def _code_summary_en(c: DiscountCode) -> str:
    if c.type == int(DiscountType.PERCENT):
        s = f"{c.value}% off"
        if c.max_discount:
            s += f" (max {_money(c.max_discount)})"
    elif c.type == int(DiscountType.FIXED):
        s = f"{_money(c.value)} off"
    else:
        s = "Free shipping"
    if c.min_subtotal:
        s += f", min spend {_money(c.min_subtotal)}"
    if c.first_order_only:
        s += ", first order only"
    return s


def _code_summary_zh(c: DiscountCode) -> str:
    if c.type == int(DiscountType.PERCENT):
        s = f"{(100 - c.value) / 10:g} 折"
        if c.max_discount:
            s += f"，最高减 {_money(c.max_discount)}"
    elif c.type == int(DiscountType.FIXED):
        s = f"立减 {_money(c.value)}"
    else:
        s = "免邮"
    if c.min_subtotal:
        s += f"，满 {_money(c.min_subtotal)} 可用"
    if c.first_order_only:
        s += "，限首单"
    return s


def _order_reply(db: Session, msg: str, order_no: str | None, zh: bool) -> tuple[str, dict | None]:
    no = (order_no or "").strip().upper()
    if not no:
        m = re.search(r"NS[0-9A-Z]{6,}", msg.upper())
        no = m.group(0) if m else ""
    if not no:
        reply = (
            "帮你查订单 📦 请把订单号（NS 开头）发给我，"
            "或到 track.html 用订单号 + 邮箱免登录查询。",
            "Happy to check 📦 Send me your order number (starts with NS), "
            "or track it at track.html — no login needed.",
        )
        return reply[int(not zh)], None
    order = repo.order_by_no(db, no)
    if not order:
        reply = (
            f"没有找到订单 {no} 🤔 请核对订单号（支付成功邮件里可查），"
            "或到 track.html 用订单号 + 邮箱查询。",
            f"I couldn't find order {no} 🤔 Double-check the number (it's in your confirmation email), "
            "or look it up at track.html with the order number + email.",
        )
        return reply[int(not zh)], None
    st_en, st_zh = STATUS_TEXT.get(order.status, ("Unknown", "未知"))
    ships = repo.shipments_asc(db, order.id)
    lines = []
    data = {"order_no": no, "status": order.status, "status_text": st_zh if zh else st_en, "tracking": []}
    for s in ships:
        tail = s.tracking_no[-4:] if s.tracking_no else ""
        data["tracking"].append({"carrier": s.carrier, "tracking_no_tail": tail})
        if zh:
            lines.append(f"物流：{s.carrier.upper()} · 运单号尾号 {tail}")
        else:
            lines.append(f"Shipped via {s.carrier.upper()} · tracking no. ending {tail}")
    if not lines:
        lines.append("包裹尚在处理，付款后 24 小时内发出" if zh else "Your parcel is being packed — ships within 24h of payment")
    head = f"订单 {no} · {st_zh} 📦" if zh else f"Order {no} · {st_en} 📦"
    return head + "\n" + "\n".join(lines), data


def chat(db: Session, body: ChatIn) -> dict:
    msg = (body.message or "").strip()
    zh = bool(re.search(r"[\u4e00-\u9fff]", msg))
    intent = next((name for name, rx in RULES if rx.search(msg)), "fallback")
    data: dict | None = None

    if intent in FAQ_CATEGORY:
        reply = _faq_reply(db, FAQ_CATEGORY[intent])
        if reply is None:
            intent, reply = "fallback", FALLBACK_REPLY[int(not zh)]
    elif intent == "order":
        reply, data = _order_reply(db, msg, body.order_no, zh)
    elif intent == "code":
        rows = repo.active_codes(db, utcnow())
        data = {"codes": [{"code": c.code, "summary": _code_summary_en(c)} for c in rows]}
        if not rows:
            reply = (
                "暂时没有可用折扣码，去 sale.html 看看直降款吧～",
                "No active codes right now — check sale.html for markdowns.",
            )[int(not zh)]
        else:
            lines = [f"**{c.code}** — {_code_summary_zh(c) if zh else _code_summary_en(c)}" for c in rows]
            head = "当前可用折扣码 🎟️\n\n" if zh else "Codes you can use right now 🎟️\n\n"
            reply = head + "\n".join(lines)
    elif intent == "recommend":
        items = recommend_items(db, product_id=None, cart_ids=[], size=3)
        data = {"items": items}
        head = "最近卖得最好的三款 💅\n\n" if zh else "Top picks right now 💅\n\n"
        if zh:
            lines = [f"{i + 1}. {it['title']} · ${it['price_min'] / 100:.2f} · 已售 {it['sold_count']}" for i, it in enumerate(items)]
        else:
            lines = [f"{i + 1}. {it['title']} · ${it['price_min'] / 100:.2f} · {it['sold_count']} sold" for i, it in enumerate(items)]
        reply = head + "\n".join(lines)
    elif intent == "human":
        reply = (
            "好的，正在为你转接人工客服 💜 也可以到 contact.html 提交工单，平均 4 小时内首次回复。",
            "Sure — connecting you to a human 💜 You can also open a ticket at contact.html; average first reply is under 4 hours.",
        )[int(not zh)]
    else:
        reply = FALLBACK_REPLY[int(not zh)]

    out = {"intent": intent, "reply": reply, "suggestions": SUGGESTIONS[intent][int(not zh)]}
    if data is not None:
        out["data"] = data
    return out
