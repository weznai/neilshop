"""GLOWMAG 种子数据 —— 对齐 prototype/ 全部基线口径（商品/价格/库存/折扣码/标准订单 $31.10）"""

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func

from app.core.db import Base, SessionLocal, engine, init_db, utcnow
from app.core.enums import (
    DiscountType, OrderStatus, PaymentProvider, PaymentStatus,
    PointsReason, ReferralStatus, RmaReason, RmaStatus, ShipmentStatus,
    ShippingStatus, StockMovementType, TicketCategory, TicketStatus, UserRole,
)
from app.core.security import hash_password
from app.services.referrals import derive_code
from app.models import (
    Article, Category, ChatConversation, ChatMessage, DiscountCode, DiscountRedemption,
    EmailPreference, Faq, GiftCard, NewsletterSubscriber, Order, OrderItem, OrderTimeline,
    Payment, PointsLedger, PopupConfig, Product, Referral, ReplyTemplate, Review, Rma,
    Setting, Shipment, ShippingRate, StockMovement, Ticket, TicketMessage,
    UgcSubmission, User, Variant, VariantImage,
)

IMG = "https://placehold.co/600x600/{bg}/{fg}.png?text={label}"
PALETTES = [
    ("F5D8DA", "6D2E46"), ("E8B4B8", "552338"), ("E8C5D8", "552338"),
    ("DDD6E8", "552338"), ("FBEBD4", "8A6D3B"),
]

# (slug, title, subtitle, cat, price, compare, stock, tags, new, best, rating, rating_n, sold)
CATALOG = [
    ("ma-damn", "Ma Damn", "Classic red creme, instant icon", 1599, None, 34, ["solid", "red"], True, True, 490, 212, 480),
    ("winter-storm", "Winter Storm", "Icy chrome with magnetic cat-eye", 1599, None, 8, ["cat-eye", "chrome"], True, False, 487, 96, 210),
    ("bare-gems", "Bare Gems", "Nude base with crystal accents", 1599, 1999, 120, ["french", "nude", "new"], True, True, 493, 341, 860),
    ("french-kiss", "French Kiss", "The timeless french tip", 1499, None, 56, ["french", "classic"], False, True, 495, 288, 1240),
    ("cherry-bomb", "Cherry Bomb", "Glossy cherry red glaze", 1399, None, 0, ["solid", "red"], False, False, 482, 75, 300),
    ("golden-hour", "Golden Hour", "Warm gold foil shimmer", 1799, None, 23, ["glitter", "gold"], True, False, 491, 154, 420),
    ("cloud-nine", "Cloud Nine", "Dreamy lavender milk", 1599, None, 41, ["solid", "pastel"], False, False, 486, 123, 350),
    ("midnight-muse", "Midnight Muse", "Deep navy with star dust", 1699, None, 3, ["glitter", "dark"], False, False, 489, 68, 190),
    ("peachy-keen", "Peachy Keen", "Soft peach glow", 1299, 1599, 67, ["solid", "pastel"], False, True, 484, 201, 610),
    ("venus", "Venus", "Pearl chrome masterpiece", 1999, None, 88, ["chrome", "pearl"], True, True, 496, 176, 520),
    ("aurora", "Aurora", "Holographic northern lights", 1799, None, 45, ["holo", "glitter"], True, False, 492, 143, 380),
    ("nova", "Nova", "Electric neon mix", 1599, None, 0, ["art", "neon"], False, False, 478, 39, 150),
]

SHAPES = [
    ("Short Almond", "SA"), ("Medium Square", "MS"),
    ("Stiletto", "ST"), ("Coffin", "CF"),
]

# 个性化详情文案（description_md）：材质/场合/搭配建议，每款手写
DESCRIPTIONS = {
    "ma-damn": "**Ma Damn** — A true salon red in a glossy creme finish that photographs like a fresh manicure. "
               "The shade leans cool enough to flatter every skin tone, which is why it is our most-repurchased classic. "
               "Pair it with a little black dress and skip the drying time entirely.",
    "winter-storm": "**Winter Storm** — Icy chrome that shifts into a magnetic cat-eye streak, no salon lamp required. "
                    "The slightly translucent base keeps the shimmer frosty instead of flat. "
                    "Made for winter knits, cold-weather photos and cool-toned statements.",
    "bare-gems": "**Bare Gems** — A soft nude base hand-set with crystal accents along the cuticle line, finished with a wet-look top coat. "
                 "The quiet-luxury pick for office weeks, weddings and close-up photos. "
                 "Short Almond wears especially natural if this is your first press-on set.",
    "french-kiss": "**French Kiss** — The timeless french tip with a modern twist: a softer white smile line over a milky base that brightens any skin tone. "
                   "Interview Monday through bridal-shower Saturday, this set goes with everything. "
                   "Keep the spares from the 24-piece box in your bag for touch-up emergencies.",
    "cherry-bomb": "**Cherry Bomb** — A glossy jelly glaze in ripe cherry red, layered for that just-bitten stain effect. "
                   "Slightly sheerer than a solid creme, it makes short nails look sweet and youthful. "
                   "The date-night set — no UV lamp, no chips, no effort.",
    "golden-hour": "**Golden Hour** — Warm gold foil suspended in champagne shimmer, like the last ten minutes of sunset on your nails. "
                   "The flakes catch light from every angle without ever reading costume-y. "
                   "Especially beautiful on Medium Square shapes over a summer tan.",
    "cloud-nine": "**Cloud Nine** — A dreamy lavender milk with the smooth, high-coverage finish of a two-coat salon application. "
                  "The pastel reads soft and editorial rather than costume purple. "
                  "Pair with grey knitwear or lilac silk for the full soft-girl moment.",
    "midnight-muse": "**Midnight Muse** — A deep navy base scattered with silver star dust that glitters like a clear night sky. "
                     "Dark enough for evening, shimmering enough that it never reads as flat black. "
                     "Built for cocktail parties, concerts and late city-light photos.",
    "peachy-keen": "**Peachy Keen** — A soft peach glow with a creamy finish that warms up any skin tone in seconds. "
                   "Think juiciest-peach manicure without the salon mark-up. "
                   "Our most-gifted shade for moms, teachers and May birthdays.",
    "venus": "**Venus** — A pearl chrome masterpiece: opalescent white shot through with pink and gold reflects. "
             "The layered chrome looks expensive even in flat daylight. "
             "Wear it to graduations, gallery nights and any day you want hands that look sculpted.",
    "aurora": "**Aurora** — Holographic northern lights: a sheer lilac base packed with rainbow prism shimmer. "
              "In direct sunlight the whole nail erupts into color. "
              "Best on Short Almond for a beam of light down each finger.",
    "nova": "**Nova** — An electric neon mix of tangerine, hot pink and lime in a bold color-block design. "
            "This is the festival set: loud, graphic and impossible to miss. "
            "Style with a plain white tee and let the nails do all the talking.",
    "magic-glue": "**Magic Glue** — Professional-grade nail glue in a 5 ml precision-nozzle bottle. "
                  "Holds a full set through dish washing, workouts and up to 2 weeks of wear, yet releases cleanly after a 10-minute warm soak. "
                  "Keep one at home and one in your purse — a spare tube has saved many sets.",
    "velvet-nights": "**Velvet Nights** — Deep velvet matte in smoked plum-black, dusted with midnight shimmer that reads matte indoors and glimmers under party lights. "
                     "The soft-focus finish is the texture salons charge extra for. "
                     "Made for autumn dinners, velvet blazers and dark-lipstick season.",
}

# 磁吸睫毛（magnetic-lashes 分类补挂）：(slug, title, subtitle, price, compare, stock, tags, new, best, rating, rating_n, sold, published_days_ago)
LASHES = [
    ("venus-lash", "Venus Lash", "Pearl cat-eye with magnetic hold", 1299, 1599, 52,
     ["cat-eye", "lashes", "natural"], True, True, 491, 58, 240, 6),
    ("aurora-lash", "Aurora Lash", "Wispy flare, no glue needed", 999, None, 30,
     ["cat-eye", "lashes", "wispy"], True, False, 486, 33, 120, 9),
    ("midnight-lash", "Midnight Lash", "Dramatic volume for night looks", 1599, 1999, 18,
     ["cat-eye", "lashes", "dramatic"], False, True, 488, 47, 190, 12),
]

LASH_STYLES = [("Natural Cat", "NC"), ("Full Glam", "FG")]

_LASH_SLUG_SET = {row[0] for row in LASHES}

LASH_DESCRIPTIONS = {
    "venus-lash": "**Venus Lash** — A pearl-black cat-eye lash with magnetic hold: sandwich your natural lashes "
                  "between the bands and pinch, no glue and no drying time. Dramatic enough for evenings, "
                  "light enough for all-day wear, and reusable for up to 20 wears.",
    "aurora-lash": "**Aurora Lash** — A wispy flare lash with alternating lengths for that fluttery, I-woke-up-like-this effect. "
                   "Magnetic application takes about 60 seconds once the pinch clicks. "
                   "The natural pick for first-timers, school runs and no-makeup makeup days.",
    "midnight-lash": "**Midnight Lash** — Maximum-volume lashes on a dense, layered band for night looks and photo flashes. "
                     "The magnets hold through concerts, weddings and 2 a.m. dancing with no mid-night re-glue. "
                     "Stack over liner for the fullest effect; reusable for up to 20 wears.",
}


def _seed_lashes(s) -> int:
    """磁吸睫毛幂等补种：修复 magnetic-lashes 分类空挂（老库可重复执行；任一 lash slug 已存在即跳过）"""
    slugs = [row[0] for row in LASHES]
    if s.query(Product).filter(Product.slug.in_(slugs)).first():
        return 0
    now = utcnow()
    cat = s.query(Category).filter(Category.slug == "magnetic-lashes").first()
    if cat is None:
        cat = Category(slug="magnetic-lashes", name="Magnetic Lashes", sort_order=2)
        s.add(cat)
        s.flush()
    for i, (slug, title, sub, price, compare, stock, tags,
            is_new, best, rating, rn, sold, ago) in enumerate(LASHES):
        bg, fg = PALETTES[(i + 2) % len(PALETTES)]
        base = title.replace(" ", "+")
        p = Product(
            slug=slug, title=title, subtitle=sub,
            description_md=LASH_DESCRIPTIONS[slug],
            category_id=cat.id, status=1,
            compare_at_price=compare, price_min=price, price_max=price + 200,
            hero_image=IMG.format(bg=bg, fg=fg, label=base),
            images=[IMG.format(bg=bg, fg=fg, label=base + "+Side"),
                    IMG.format(bg=bg, fg=fg, label=base + "+Swatch")],
            tags=tags, is_new=is_new, is_best_seller=best,
            rating_avg=rating, rating_count=rn, sold_count=sold,
            published_at=now - timedelta(days=ago),
        )
        s.add(p)
        s.flush()
        for j, (style, code) in enumerate(LASH_STYLES):
            s.add(Variant(
                product_id=p.id, sku=f"{slug[:3].upper()}-{code}-PR",
                option1_value=style, option2_value="1 pair",
                price=price if j == 0 else price + 200,
                stock=stock if j == 0 else max(3, stock // 3),
                safety_stock=5,
            ))
        s.flush()
    s.commit()
    return len(LASHES)


def seed() -> None:
    init_db()
    # 存量库幂等 DDL 守卫（create_all 不改旧表；缺列/窄列在此补齐，重复执行零副作用）
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ensure_schema import ensure_schema

    ensure_schema()
    s = SessionLocal()

    # 磁吸睫毛幂等补种（老库空挂修复；新库随主流程一起建，主流程复用已建分类）
    had_products = s.query(Product).count() > 0
    if _seed_lashes(s):
        print("seed: magnetic lashes backfilled")

    if had_products:
        print("seed: products exist, skip")
        s.close()
        return

    now = utcnow()

    # ===== 分类 =====
    cat_nails = Category(slug="press-on-nails", name="Press-on Nails", sort_order=1)
    cat_lashes = s.query(Category).filter(Category.slug == "magnetic-lashes").first() \
        or Category(slug="magnetic-lashes", name="Magnetic Lashes", sort_order=2)
    cat_acc = Category(slug="accessories", name="Accessories", sort_order=3)
    s.add_all([cat_nails, cat_lashes, cat_acc])
    s.flush()

    # ===== 商品 + 变体（GM_CATALOG 基线）=====
    variant_ids = {}
    for i, (slug, title, sub, price, compare, stock, tags, is_new, best, rating, rn, sold) in enumerate(CATALOG):
        bg, fg = PALETTES[i % len(PALETTES)]
        base = title.replace(" ", "+")
        p = Product(
            slug=slug, title=title, subtitle=sub,
            description_md=DESCRIPTIONS[slug],
            category_id=cat_nails.id, status=1,
            compare_at_price=compare, price_min=price, price_max=price + 200,
            hero_image=IMG.format(bg=bg, fg=fg, label=base),
            images=[IMG.format(bg=bg, fg=fg, label=base + "+Side"),
                    IMG.format(bg=bg, fg=fg, label=base + "+Swatch")],
            tags=tags, is_new=is_new, is_best_seller=best,
            rating_avg=rating, rating_count=rn, sold_count=sold,
            published_at=now - timedelta(days=30 - i),
        )
        s.add(p)
        s.flush()
        for j, (shape, code) in enumerate(SHAPES):
            v = Variant(
                product_id=p.id, sku=f"{slug[:3].upper()}-{code}-24",
                option1_value=shape, option2_value="24 pcs",
                price=price if j == 0 else price + 200,
                stock=stock if j == 0 else max(3, stock // 4 or 0),
                safety_stock=5,
            )
            s.add(v)
        s.flush()
        variant_ids[slug] = (s.query(Variant).filter(Variant.product_id == p.id)
                             .order_by(Variant.id).first().id, price)

    # 配件（胶水）
    glue = Product(
        slug="magic-glue", title="Magic Glue", subtitle="Hold-fast nail glue, 5ml",
        description_md=DESCRIPTIONS["magic-glue"],
        category_id=cat_acc.id, status=1, price_min=1399, price_max=1399,
        hero_image=IMG.format(bg="DDD6E8", fg="552338", label="Magic+Glue"),
        images=[IMG.format(bg="DDD6E8", fg="552338", label="Magic+Glue")],
        tags=["tool"], is_best_seller=True, rating_avg=481, rating_count=95, sold_count=700,
        published_at=now - timedelta(days=60),
    )
    s.add(glue)
    s.flush()
    s.add(Variant(product_id=glue.id, sku="MG-STD", option1_value="Standard", option2_value="5 ml",
                  price=1399, stock=50))
    s.flush()

    # 定时上架演示：status=1 但 published_at=now+7d → 前台查询时不可见（列表/详情 404），
    # admin 可见 scheduled=true；到点自动可见（worker publish_scheduled 到点发 product.published）
    vn_bg, vn_fg = PALETTES[3]
    velvet = Product(
        slug="velvet-nights", title="Velvet Nights", subtitle="Deep velvet matte with midnight shimmer",
        description_md=DESCRIPTIONS["velvet-nights"],
        category_id=cat_nails.id, status=1,
        price_min=1699, price_max=1899,
        hero_image=IMG.format(bg=vn_bg, fg=vn_fg, label="Velvet+Nights"),
        images=[IMG.format(bg=vn_bg, fg=vn_fg, label="Velvet+Nights+Side"),
                IMG.format(bg=vn_bg, fg=vn_fg, label="Velvet+Nights+Swatch")],
        tags=["velvet", "dark"], is_new=1,
        published_at=now + timedelta(days=7),
    )
    s.add(velvet)
    s.flush()
    for j, (shape, code) in enumerate(SHAPES):
        s.add(Variant(
            product_id=velvet.id, sku=f"VN-{code}-24",
            option1_value=shape, option2_value="24 pcs",
            price=1699 if j == 0 else 1899,
            stock=60 if j == 0 else 20, safety_stock=5,
        ))
    s.flush()

    # ===== 用户 =====
    admin = User(email="admin@glowmag.com", password_hash=hash_password("glowmag123"),
                 name="Glow Admin", role=int(UserRole.SUPER), email_verified_at=now)
    ops = User(email="ops@glowmag.com", password_hash=hash_password("glowmag123"),
               name="Ops Team", role=int(UserRole.OPS), email_verified_at=now)
    cs = User(email="cs@glowmag.com", password_hash=hash_password("glowmag123"),
              name="CS Team", role=int(UserRole.CS), email_verified_at=now)
    emma = User(email="emma@glowmag.com", password_hash=hash_password("glowmag123"),
                name="Emma Rodriguez", role=0, points=611, email_verified_at=now,
                total_spent=3110, last_order_at=now - timedelta(days=18))
    s.add_all([admin, ops, cs, emma])
    s.flush()

    # 美甲师（role=4）：前台聊天窗美甲师列表 + 后台受限工作台（仅在线客服菜单）
    for a_email, a_name, a_intro in [
        ("mia@glowmag.com", "Mia Chen", "法式与裸色系专精 · 8 年穿戴甲定制经验，擅长婚礼/日常通勤款"),
        ("yuki@glowmag.com", "Yuki Tanaka", "猫眼/铬色光泽控 · 擅长猫眼、极光与短甲定制"),
        ("luna@glowmag.com", "Luna Park", "手绘艺术甲担当 · 花卉、节日主题与渐变晕染都可以聊"),
    ]:
        s.add(User(email=a_email, password_hash=hash_password("glowmag123"),
                   name=a_name, role=int(UserRole.ARTIST), artist_intro=a_intro,
                   email_verified_at=now))
    s.flush()

    # ===== settings =====
    for k, v, desc in [
        ("free_shipping_threshold", 3500, "满额免邮（美分）"),
        ("tax_rate", 0.0735, "综合税率"),
        ("shipping_standard", 499, "标准运费"),
        ("shipping_express", 1499, "快递运费"),
        ("return_days", 30, "退货窗口（天）"),
        ("points_per_dollar_earn", 10, "消费 $1 赚积分"),
        ("site_url", "http://localhost:5173", "前台站点根地址（重置链接等邮件外链前缀）"),
    ]:
        s.add(Setting(key=k, value=v, description=desc))

    # ===== 折扣码 =====
    s.add_all([
        DiscountCode(code="WELCOME20", name="新客 8 折（max $10）", type=int(DiscountType.PERCENT),
                     value=20, max_discount=1000, first_order_only=1, per_user_limit=1, starts_at=now),
        DiscountCode(code="EARLYBIRD", name="新品早鸟 75 折", type=int(DiscountType.PERCENT),
                     value=25, starts_at=now),
        DiscountCode(code="BYE2025", name="年终大促（max $15）", type=int(DiscountType.PERCENT),
                     value=25, max_discount=1500, starts_at=now),
        DiscountCode(code="FREESHIP", name="免邮码", type=int(DiscountType.FREE_SHIPPING),
                     value=0, starts_at=now),
        DiscountCode(code="ABANDON10", name="弃购挽回第1封 9 折", type=int(DiscountType.PERCENT),
                     value=10, starts_at=now),
        DiscountCode(code="ABANDON15", name="弃购挽回第2封 85 折", type=int(DiscountType.PERCENT),
                     value=15, starts_at=now),
    ])

    # ===== 运费表 =====
    s.add_all([
        ShippingRate(dest_country="US", carrier="usps", method="standard", max_weight_g=500,
                     price=499, free_over=3500, eta_min_days=3, eta_max_days=6),
        ShippingRate(dest_country="US", carrier="ups", method="express", max_weight_g=500,
                     price=1499, eta_min_days=1, eta_max_days=3),
        ShippingRate(dest_country="*", carrier="dhl", method="standard", max_weight_g=500,
                     price=1299, eta_min_days=6, eta_max_days=12),
    ])

    # ===== 标准演示订单 NS260728D4E5F6（$31.10 对齐原型 4 页）=====
    bg_v, bg_price = variant_ids["bare-gems"]
    cb_v, cb_price = variant_ids["cherry-bomb"]
    subtotal = bg_price + cb_price            # 2998
    discount = 600                            # WELCOME20 20% → 599.6 → 600（四舍五入）
    shipping = 499
    tax = int((subtotal - discount + shipping) * 0.0735 + 0.5)  # 213
    grand = subtotal - discount + shipping + tax                # 3110
    placed = now - timedelta(days=18)
    demo = Order(
        order_no="NS260728D4E5F6", user_id=emma.id, email=emma.email,
        status=int(OrderStatus.DELIVERED), shipping_status=int(ShippingStatus.ALL),
        subtotal=subtotal, discount_total=discount, shipping_fee=shipping, tax=tax,
        grand_total=grand, points_earned=grand // 10,
        shipping_address={"full_name": "Emma Rodriguez", "line1": "535 Market St", "city": "San Francisco",
                          "state": "CA", "zip": "94105", "country": "US", "phone": "+14155550188"},
        shipping_method="standard", source="web",
        placed_at=placed, paid_at=placed + timedelta(minutes=3),
        fulfilled_at=placed + timedelta(hours=20), shipped_at=placed + timedelta(days=1),
        delivered_at=placed + timedelta(days=5),
    )
    s.add(demo)
    s.flush()
    s.add_all([
        OrderItem(order_id=demo.id, variant_id=bg_v, product_slug="bare-gems",
                  title_snapshot="Bare Gems · Short Almond", qty=1, unit_price=bg_price, subtotal=bg_price),
        OrderItem(order_id=demo.id, variant_id=cb_v, product_slug="cherry-bomb",
                  title_snapshot="Cherry Bomb · Short Almond", qty=1, unit_price=cb_price, subtotal=cb_price),
    ])
    s.add(Payment(order_id=demo.id, stripe_payment_intent="PI_demo_4E5F6",
                  amount=grand, status=int(PaymentStatus.SUCCESS),
                  created_at=placed + timedelta(minutes=3)))
    s.add(Shipment(shipment_no="SP2607290001", order_id=demo.id, carrier="usps",
                   tracking_no="9400111899560000000001", status=int(ShipmentStatus.DELIVERED),
                   item_json=[], shipped_at=placed + timedelta(days=1),
                   delivered_at=placed + timedelta(days=5)))
    for ev, at in [("checkout_created", placed), ("payment_succeeded", placed + timedelta(minutes=3)),
                   ("shipment_created", placed + timedelta(days=1)),
                   ("tracking_updated", placed + timedelta(days=3)), ("status_changed", placed + timedelta(days=5))]:
        s.add(OrderTimeline(order_id=demo.id, event=ev, actor="system", created_at=at))
    s.add(PointsLedger(user_id=emma.id, change=grand // 10, reason=int(PointsReason.ORDER_EARN_FROZEN),
                       balance_after=grand // 10 + 300, ref_type="order", ref_id=demo.id,
                       frozen=1, expires_at=now + timedelta(days=30)))

    # ===== 内容 =====
    faqs = [
        (1, "How do I find my nail size?", "Use our interactive sizer or printable chart..."),
        (1, "Can short or bitten nails wear press-ons?", "Absolutely — Short Almond is made for shorter nail beds."),
        (2, "How long does one set last?", "Up to 2 weeks with proper prep; reuse up to 3 wears."),
        (3, "When will my order ship?", "Packed within 24h, delivered in 3-6 business days (US)."),
        (3, "Do you ship internationally?", "Yes — 6-12 days via DHL to 40+ countries."),
        (4, "What's your return policy?", "30-day window on unopened sets; quality issues fully covered."),
        (5, "How do I remove them safely?", "Soak 10 min in warm soapy water, gently lift from the side. Never pry."),
        (6, "How do points work?", "Earn 10 pts per $1, redeem 100 pts = $1 at checkout."),
    ]
    for cat, q, a in faqs:
        s.add(Faq(category=cat, question=q, answer_md=a, sort_order=cat))

    for i, (slug, title, author, tag) in enumerate([
        ("press-on-nails-101", "Press-on Nails 101: Your First Set", "Maya Chen", "howto"),
        ("5-minute-mani", "The 5-Minute Mani Routine", "Jordan Lee", "care"),
        ("best-nail-shapes", "Best Nail Shapes for Your Hands", "Team GLOWMAG", "guides"),
    ]):
        bg, fg = PALETTES[i % len(PALETTES)]
        s.add(Article(slug=slug, title=title, author=author, tags=[tag, "nails"], status=1,
                      cover=IMG.format(bg=bg, fg=fg, label=title.replace(" ", "+")[:20]),
                      content_md=f"# {title}\n\nSalon-grade glamour at home — the GLOWMAG guide.",
                      published_at=now - timedelta(days=7 - i)))

    s.add(GiftCard(code="GC-DEMO-2026-0001", initial_amount=5000, balance=3499, status=1,
                   purchaser_email="admin@glowmag.com", expires_at=now + timedelta(days=365)))
    s.add(PopupConfig(scene="welcome", title="Get 20% off your first set",
                      content_md="Join the glam crew — code **WELCOME20** inside.",
                      coupon_code="WELCOME20",
                      trigger_rules={"delaySec": 7, "exitIntent": False, "mobileOnly": False},
                      active=1, stats_shown=2418, stats_converted=634))
    for i, (cat, t, c) in enumerate([
        (3, "Return label", "Hi! Here's your prepaid return label. Refund lands 3-5 days after we receive it."),
        (1, "Where is my order", "Your order shipped via USPS, tracking {tracking_no}. Expected in 2-4 days."),
        (2, "Quality issue", "So sorry! We'll replace it right away — no return needed."),
        (1, "运费/时效说明", "美国境内标准运费 $4.99（3–6 天送达），快递 $14.99（1–3 天）；满 $35 包邮～"),
        (3, "退换流程引导", "签收后 30 天内未拆封可退换：账户 → 订单 → 发起退换即可，质量问题运费全免。"),
        (4, "账户/密码帮助", "可以用注册邮箱点「忘记密码」重置；如收不到邮件，把邮箱发我帮你查～"),
        (5, "选码建议", "先到尺码指南 60 秒量甲；两手常混 2–3 个码，介于两码之间选大一号再修边。"),
        (5, "新品/推荐话术", "跟你说下最近卖得最好的：Bare Gems 和 French Kiss 都是回购率 TOP～要帮你推荐组合吗？"),
        (6, "结束语", "还有其他问题随时找我，祝你今天愉快 💜"),
    ]):
        s.add(ReplyTemplate(category=cat, title=t, content=c))

    s.commit()
    print(f"seed done: products={s.query(Product).count()} variants={s.query(Variant).count()} "
          f"users={s.query(User).count()} faqs={s.query(Faq).count()} demo order NS260728D4E5F6 grand={grand}")

    # ================================================================
    # 运营态追加：历史用户 / 历史订单 / 评价 / RMA / 工单 / UGC / 流水
    # ================================================================
    P = {p.slug: p for p in s.query(Product).all()}
    glue_v = (s.query(Variant).filter(Variant.product_id == P["magic-glue"].id)
              .order_by(Variant.id).first())
    variant_ids["magic-glue"] = (glue_v.id, 1399)
    # 睫毛首变体也入 variant_ids（供历史订单/评价复用既有链路）
    for _slug in (row[0] for row in LASHES):
        _v0 = (s.query(Variant).filter(Variant.product_id == P[_slug].id)
               .order_by(Variant.id).first())
        variant_ids[_slug] = (_v0.id, P[_slug].price_min)
    dc_map = {c.code: c for c in s.query(DiscountCode).all()}

    ADDRS = [
        ("412 Maple Ave", "Austin", "TX", "78701"), ("88 Harbor View Ln", "Boston", "MA", "02110"),
        ("1720 Pine St", "Denver", "CO", "80202"), ("590 Sunset Blvd", "Los Angeles", "CA", "90026"),
        ("33 Lakeshore Dr", "Chicago", "IL", "60601"), ("77 Peachtree St", "Atlanta", "GA", "30303"),
        ("915 Fremont St", "Portland", "OR", "97209"), ("240 Rivington St", "Brooklyn", "NY", "11211"),
        ("618 River Rd", "Nashville", "TN", "37203"), ("1301 Alaskan Way", "Seattle", "WA", "98101"),
        ("45 Palmetto Ave", "Miami", "FL", "33131"), ("2 Beacon Hill Rd", "Charlotte", "NC", "28202"),
    ]

    # (key, name, email, points, risk, created_days_ago)
    HIST_USERS = [
        ("u1", "Olivia Bennett", "olivia.bennett@gmail.com", 480, 0, 110),
        ("u2", "Mason Carter", "mason.carter@outlook.com", 1240, 0, 95),
        ("u3", "Sophia Nguyen", "sophia.nguyen@yahoo.com", 620, 0, 88),
        ("u4", "Liam Rodriguez", "liam.rodriguez@icloud.com", 90, 1, 80),
        ("u5", "Ava Thompson", "ava.thompson@gmail.com", 2400, 0, 75),
        ("u6", "Noah Patel", "noah.patel@proton.me", 310, 0, 70),
        ("u7", "Mia Foster", "mia.foster@comcast.net", 150, 0, 120),
        ("u8", "Ethan Brooks", "ethan.brooks@aol.com", 0, 1, 130),
        ("u9", "Isabella Martinez", "bella.martinez@att.net", 75, 0, 115),
        ("u10", "Lucas Gray", "lucas.gray@msn.com", 1860, 0, 60),
        ("u11", "Harper Reed", "harper.reed@gmail.com", 520, 0, 45),
        ("u12", "Evelyn Cox", "evelyn.cox@me.com", 940, 0, 40),
    ]
    hist = {}
    for (uk, name, email, pts, risk, ago), (line1, city, st, zip_) in zip(HIST_USERS, ADDRS):
        u = User(email=email, password_hash=hash_password("glowmag123"), name=name,
                 role=0, points=pts, risk_flag=risk, email_verified_at=now - timedelta(days=ago),
                 created_at=now - timedelta(days=ago))
        s.add(u)
        hist[uk] = (u, {"full_name": name, "line1": line1, "city": city, "state": st,
                        "zip": zip_, "country": "US", "phone": f"+1{500 + len(uk) % 10}55501{len(name) % 10}"})
    s.flush()

    # (user_key, days_ago, status, method, code, items[(slug, qty)], cancel_reason)
    C, S_, X, R = (OrderStatus.COMPLETED, OrderStatus.SHIPPED,
                   OrderStatus.CANCELED, OrderStatus.REFUNDED)
    HIST_ORDERS = [
        ("u1", 2, C, "standard", "WELCOME20", [("bare-gems", 1), ("magic-glue", 1)], None),
        ("u2", 3, S_, "express", None, [("french-kiss", 1), ("peachy-keen", 1), ("magic-glue", 1)], None),
        ("u3", 4, C, "standard", None, [("ma-damn", 2), ("golden-hour", 1), ("cloud-nine", 1)], None),
        ("u7", 4, C, "standard", None, [("magic-glue", 1), ("venus-lash", 1), ("aurora-lash", 1)], None),
        ("u5", 5, C, "standard", None, [("bare-gems", 2), ("venus", 3), ("magic-glue", 1)], None),
        ("u9", 5, C, "standard", None, [("aurora-lash", 1), ("midnight-lash", 1)], None),
        ("u3", 6, S_, "standard", None, [("magic-glue", 1), ("midnight-lash", 1), ("venus-lash", 1)], None),
        ("u10", 7, S_, "standard", "WELCOME20", [("cloud-nine", 1), ("aurora", 1), ("peachy-keen", 1)], None),
        ("u4", 9, X, "standard", None, [("ma-damn", 1)], "user"),
        ("u6", 10, C, "standard", "WELCOME20", [("winter-storm", 1), ("magic-glue", 1)], None),
        ("u11", 12, S_, "standard", None, [("bare-gems", 1), ("french-kiss", 1), ("venus", 1)], None),
        ("u1", 13, C, "standard", None, [("peachy-keen", 1), ("ma-damn", 1)], None),
        ("u12", 16, R, "standard", None, [("golden-hour", 1), ("cloud-nine", 1)], None),
        ("u5", 19, C, "standard", None, [("french-kiss", 2), ("bare-gems", 2), ("magic-glue", 1)], None),
        ("u2", 23, C, "standard", "EARLYBIRD", [("venus", 1), ("aurora", 1)], None),
        ("u6", 27, C, "standard", None, [("midnight-muse", 1), ("cherry-bomb", 1)], None),
        ("u10", 31, C, "standard", None, [("peachy-keen", 1), ("magic-glue", 1)], None),
        ("u2", 33, C, "standard", None, [("venus", 2), ("magic-glue", 1), ("bare-gems", 1)], None),
        ("u3", 36, C, "standard", None, [("ma-damn", 1), ("french-kiss", 1)], None),
        ("u11", 41, C, "express", "EARLYBIRD", [("aurora", 1), ("venus", 1), ("magic-glue", 1)], None),
        ("u4", 45, R, "standard", None, [("cloud-nine", 1)], None),
        ("u12", 49, C, "standard", "WELCOME20", [("bare-gems", 1), ("peachy-keen", 1)], None),
        ("emma", 52, C, "standard", None, [("venus", 1), ("magic-glue", 1)], None),
        ("u1", 55, X, "standard", None, [("cherry-bomb", 1)], "user"),
        ("u5", 58, C, "standard", None, [("golden-hour", 3), ("aurora", 3)], None),
        ("u7", 72, C, "standard", "WELCOME20", [("french-kiss", 1), ("bare-gems", 1), ("magic-glue", 1)], None),
        ("u8", 78, R, "standard", None, [("ma-damn", 1), ("golden-hour", 1)], None),
        ("u9", 85, C, "standard", None, [("peachy-keen", 1), ("cloud-nine", 1)], None),
    ]

    sn = 100
    hist_orders = []          # [(order, {slug: OrderItem})]
    orders_by_key = {}        # (user_key, days) -> (order, {slug: OrderItem})
    for uk, days, st_enum, method, code, items, cancel in HIST_ORDERS:
        u, addr = hist[uk] if uk != "emma" else (emma, {
            "full_name": "Emma Rodriguez", "line1": "535 Market St", "city": "San Francisco",
            "state": "CA", "zip": "94105", "country": "US", "phone": "+14155550188"})
        placed = now - timedelta(days=days)
        paid = placed + timedelta(minutes=3)
        sub = sum(variant_ids[sl][1] * q for sl, q in items)
        disc = 0
        if code == "WELCOME20":
            disc = min(sub * 20 // 100, 1000)
        elif code == "EARLYBIRD":
            disc = sub * 25 // 100
        ship_fee = 0 if sub - disc >= 3500 else (1499 if method == "express" else 499)
        tax = int((sub - disc + ship_fee) * 0.0735 + 0.5)
        total = sub - disc + ship_fee + tax
        st = int(st_enum)
        sn += 1
        ymd = placed.strftime("%y%m%d")
        kw = {}
        if st == int(X):
            kw = dict(canceled_at=placed + timedelta(hours=1))
        elif st == int(R):
            kw = dict(fulfilled_at=placed + timedelta(hours=20), shipped_at=placed + timedelta(days=1),
                      delivered_at=placed + timedelta(days=5), shipping_status=int(ShippingStatus.ALL),
                      canceled_at=placed + timedelta(days=7))
        elif st == int(S_):
            kw = dict(fulfilled_at=placed + timedelta(hours=20), shipped_at=placed + timedelta(days=1),
                      shipping_status=int(ShippingStatus.ALL))
        else:
            kw = dict(fulfilled_at=placed + timedelta(hours=20), shipped_at=placed + timedelta(days=1),
                      delivered_at=placed + timedelta(days=5), completed_at=placed + timedelta(days=7),
                      shipping_status=int(ShippingStatus.ALL))
        o = Order(
            order_no=f"NS{ymd}{0xA00000 + sn:06X}", user_id=u.id, email=u.email, status=st,
            subtotal=sub, discount_total=disc, shipping_fee=ship_fee, tax=tax, grand_total=total,
            discount_code_id=dc_map[code].id if code else None,
            shipping_address=addr, shipping_method=method, source="web",
            placed_at=placed, paid_at=paid, cancel_reason=cancel, points_earned=total // 10, **kw,
        )
        s.add(o)
        s.flush()
        items_map = {}
        for sl, q in items:
            shape = ("Standard" if sl == "magic-glue"
                     else "Natural Cat" if sl in _LASH_SLUG_SET
                     else "Short Almond")
            it = OrderItem(order_id=o.id, variant_id=variant_ids[sl][0], product_slug=sl,
                           title_snapshot=f"{P[sl].title} · {shape}", image=P[sl].hero_image,
                           qty=q, unit_price=variant_ids[sl][1], subtotal=variant_ids[sl][1] * q)
            s.add(it)
            items_map[sl] = it
        s.flush()
        pay_status = int(PaymentStatus.SUCCESS)
        refunded = 0
        if st in (int(X), int(R)):
            pay_status, refunded = int(PaymentStatus.REFUNDED), total
        s.add(Payment(order_id=o.id, stripe_payment_intent=f"PI_hist_{o.order_no[2:]}",
                      amount=total, status=pay_status, refunded_amount=refunded, created_at=paid))
        if st in (int(S_), int(C)):
            carrier = "ups" if method == "express" else "usps"
            tracking = (f"1Z5W860A{sn:08d}" if carrier == "ups" else f"940011189956{sn:010d}")
            s.add(Shipment(shipment_no=f"SP{ymd}{sn:04d}", order_id=o.id, carrier=carrier,
                           tracking_no=tracking, status=int(ShipmentStatus.DELIVERED if st == int(C)
                                                            else ShipmentStatus.IN_TRANSIT),
                           item_json=[{"orderItemId": it.id, "qty": it.qty} for it in items_map.values()],
                           label_url=f"https://placehold.co/200x100/EEE/333.png?text={carrier.upper()}",
                           label_cost=1499 if carrier == "ups" else 380,
                           shipped_at=placed + timedelta(days=1),
                           delivered_at=placed + timedelta(days=5) if st == int(C) else None))
        events = [("checkout_created", placed, "user"), ("payment_succeeded", paid, "system")]
        if st in (int(S_), int(C)):
            events.append(("shipment_created", placed + timedelta(days=1), "system"))
        if st == int(C):
            events += [("tracking_updated", placed + timedelta(days=3), "system"),
                       ("status_changed", placed + timedelta(days=7), "system")]
        if st == int(X):
            events.append(("status_changed", placed + timedelta(hours=1), "user"))
        if st == int(R):
            events.append(("refund_issued", placed + timedelta(days=7), "admin"))
        for ev, at, actor in events:
            s.add(OrderTimeline(order_id=o.id, event=ev, actor=actor, created_at=at))
        if code:
            s.add(DiscountRedemption(code_id=dc_map[code].id, order_id=o.id, user_id=u.id,
                                     email=u.email, discount_amount=disc, created_at=placed))
        hist_orders.append((o, items_map))
        orders_by_key[(uk, days)] = (o, items_map)

    # 用户冗余口径：total_spent 仅计完成/发货单；tier ≥$100 银 / ≥$300 金
    for uk, (u, _addr) in hist.items():
        mine = [o for o, _ in hist_orders if o.user_id == u.id]
        spent = sum(o.grand_total for o in mine if o.status in (int(C), int(S_)))
        u.total_spent = spent
        u.tier = 2 if spent >= 30000 else (1 if spent >= 10000 else 0)
        u.tier_updated_at = max(o.placed_at for o in mine)
        u.last_order_at = max(o.placed_at for o in mine)
    s.flush()

    # ===== 评价（完成/发货单 items，一单一评）=====
    lines = [(o, sl, it) for o, im in hist_orders if o.status in (int(C), int(S_))
             for sl, it in im.items()]
    lines.sort(key=lambda x: (x[0].placed_at, x[2].id), reverse=True)
    n = len(lines)
    slots = [5] * 15 + [4] * 6 + [3] * 3 + [2] * 1          # 25 槽位 ≈ 60/24/12/4%
    ratings = [slots[(i * 7 + 3) % 25] for i in range(n)]
    TEXTS = {
        5: ["Obsessed! The Short Almond fits my nail beds perfectly and the color is exactly like the photos. Day 10 and zero lifting.",
            "Third set from GLOWMAG and the quality never misses. Sizing chart was spot on, wore them a full two weeks.",
            "Got so many compliments. The glue held up through dish washing and a beach trip. Color payoff is unreal.",
            "Perfect tips without the salon price. Matched my size with the sizer tool and they stayed flawless for 12 days.",
            "The shimmer shifts in the light, even prettier in person. The prep kit made application take 15 minutes.",
            "These lasted two full weeks including gym sessions and gardening. Zero chips, zero regrets.",
            "My go-to gift now. Sizing ran true to the chart and the nude base looks so natural on."],
        4: ["Great color and wear, but I sized up when I should have stayed with Medium Square. Still wore them 10 days.",
            "Beautiful finish and easy application. One nail popped off on day 4 but the spare glue saved it.",
            "Love the shade, slightly more sheer than pictured. Held up well for 12 days of constant typing.",
            "Quality is solid though shipping took the full 6 days. The color flatters my skin tone perfectly.",
            "Almost perfect, the glitter takes extra effort to file down. Longevity is impressive though."],
        3: ["Nice color but the size run was slightly big on my pinkies. Lasted about 8 days before the edges lifted.",
            "Decent for the price. The shade is darker in person and I had to re-glue two nails mid-week.",
            "They look good from a distance. Sizing was tricky and wear time was closer to a week for me."],
        2: ["Color chipped on day 3 and the sizing guide confused me. Expected more for the price.",
            "Two nails in my set had visible bubbles under the surface. They did send a replacement eventually."],
        1: ["Arrived with the wrong size entirely and support was slow to reply. Not for me."],
    }
    # 睫毛专用评价语料（磁吸/无胶水/佩戴体验口径，避免甲片文案串场）
    LASH_TEXTS = {
        5: ["The magnetic hold is no joke — wore mine through a wedding and a gym session, zero sliding. "
            "Second try and the application just clicked.",
            "No glue, no raccoon eyes at midnight, and they peel off clean. "
            "The cat-eye flare opens up my hooded eyes more than any mascara ever did.",
            "Second pair already. The magnet bands hide perfectly under a thin liner "
            "and they still look new after 15+ wears."],
        4: ["Beautiful flare and genuinely comfortable. Took a few tries to get the pinch right — "
            "watch the 60-second tutorial first.",
            "Hold lasts my whole workday and they feel lighter than strip lashes. "
            "I was expecting fuss and got none.",
            "Gorgeous for nights out and surprisingly natural in daylight. "
            "One magnet loosened on day one but pinching it back tight fixed it."],
        3: ["Pretty and easy once you get the hang of it, though the band felt slightly long on my smaller eyes.",
            "Nice natural look, but I expected a bit more drama for the price. Wears fine for a full workday."],
        2: ["Magnets didn't line up with my lash line and one slid off at dinner. "
            "Might work better with the applicator tool."],
    }
    PENDING_IDX, REJECT_IDX, IMG_IDX = {0, 1, 2}, 7, {2, 6, 11, 17, 23, 31}
    new_reviews = []
    for i, (o, sl, it) in enumerate(lines):
        rating = ratings[i]
        status = 0 if i in PENDING_IDX else (2 if i == REJECT_IDX else 1)
        pool = LASH_TEXTS if sl in _LASH_SLUG_SET else TEXTS
        content = pool[rating][i % len(pool[rating])]
        reject_reason = None
        if i == REJECT_IDX:
            rating, content = 1, ("BEST NAILS EVER!!! Actually buy from my shop instead, link in bio, "
                                  "way cheaper!!! Free shipping worldwide!!!")
            reject_reason = "promotional spam"
        images = []
        if i in IMG_IDX:
            bg, fg = PALETTES[i % len(PALETTES)]
            images = [IMG.format(bg=bg, fg=fg, label="Review+Proof"),
                      IMG.format(bg=fg, fg=bg,
                                 label="Lash+Closeup" if sl in _LASH_SLUG_SET else "Nail+Closeup")]
        kw = dict(product_id=P[sl].id, user_id=o.user_id, order_item_id=it.id,
                  rating=rating, content=content, images=images or None, status=status,
                  reject_reason=reject_reason,
                  created_at=min(o.placed_at + timedelta(days=6 + i % 4), now - timedelta(hours=1)))
        if not images:
            del kw["images"]          # 传 None 会落 JSON 'null'，删键才存 SQL NULL
        rv = Review(**kw)
        s.add(rv)
        it.reviewed = 1
        new_reviews.append((sl, rv))
    s.flush()

    # 重算商品 rating_avg(×100)/rating_count（仅 status=1）
    agg: dict = {}
    for sl, rv in new_reviews:
        if rv.status == 1:
            agg.setdefault(sl, []).append(rv.rating)
    for sl, rs in agg.items():
        P[sl].rating_avg = round(sum(rs) * 100 / len(rs))
        P[sl].rating_count = len(rs)

    # ===== RMA 5 条（3 在途/4 已收货/5 已退款/6 拒绝/0 申请中）=====
    rma_seed = [
        # (user_key, days, slug, reason, qty, status, extra)
        ("u1", 2, "magic-glue", RmaReason.DAMAGED, 1, RmaStatus.REQUESTED,
         "Bottle cap cracked in transit, glue dried out on arrival."),
        ("u2", 23, "venus", RmaReason.SIZE, 1, RmaStatus.IN_TRANSIT,
         "Medium Square runs long on me, requesting Short Almond exchange size guidance."),
        ("u12", 49, "peachy-keen", RmaReason.DISLIKE, 1, RmaStatus.RECEIVED,
         "Shade reads more coral than peach on my skin tone."),
        ("u5", 19, "french-kiss", RmaReason.QUALITY, 1, RmaStatus.REFUNDED,
         "Two tips had uneven edges that caught on fabric."),
        ("u3", 36, "ma-damn", RmaReason.DISLIKE, 1, RmaStatus.REJECTED,
         "Worn set returned outside hygiene window."),
    ]
    for i, (uk, days, sl, reason, qty, st_enum, detail) in enumerate(rma_seed):
        o, im = orders_by_key[(uk, days)]
        it = im[sl]
        created = o.delivered_at or o.placed_at + timedelta(days=5)
        created = created + timedelta(days=i + 1)
        refund = refund_ship = restock = 0
        received_at = refunded_at = None
        st = int(st_enum)
        if st == int(RmaStatus.REFUNDED):
            share = it.unit_price * qty / o.subtotal
            refund = int(share * o.grand_total + 0.5)
            if reason == RmaReason.QUALITY:
                refund_ship = 499
                refund += 499
            refund += 0
            received_at = created + timedelta(days=4)
            refunded_at = created + timedelta(days=6)
            restock = qty
            pay = s.query(Payment).filter(Payment.order_id == o.id).first()
            pay.status = int(PaymentStatus.PARTIAL_REFUNDED)
            pay.refunded_amount = refund
        elif st == int(RmaStatus.RECEIVED):
            received_at = created + timedelta(days=3)
            restock = qty
        s.add(Rma(rma_no=f"RMA{created.strftime('%y%m%d')}{i:04X}", order_id=o.id,
                  order_item_id=it.id, qty=qty, reason=int(reason), reason_detail=detail,
                  status=st, refund_amount=refund or None, refund_shipping=refund_ship,
                  restock_qty=restock, received_at=received_at, refunded_at=refunded_at,
                  handled_by=cs.id if st in (int(RmaStatus.REFUNDED), int(RmaStatus.RECEIVED),
                                             int(RmaStatus.REJECTED)) else None,
                  label_url=None if st == 0 else
                  "https://placehold.co/200x100/EEE/333.png?text=RETURN+LABEL",
                  label_cost=None if st == 0 else 599, created_at=created))

    # ===== 工单 7 条（分类 1/2/3/5；状态 0/1/2/4 各覆盖）=====
    TICKETS = [
        ("u1", 1, "Tracking hasn't moved in 2 days", TicketCategory.SHIPPING, TicketStatus.NEW,
         None, ("u1", 2), None, None, None, [
             "Hi! Tracking for my order hasn't updated in two days. Is that normal for USPS?",
             "Thanks for reaching out! USPS often skips weekend scans. Your parcel is on schedule for Wednesday and I'm watching it on our side."]),
        ("u6", 9, "Order stuck on 'label created'", TicketCategory.SHIPPING, TicketStatus.PROCESSING,
         "cs", ("u6", 10), None, None, None, [
             "My order has been stuck on 'label created' for 5 days. Can someone check where the package is?",
             "So sorry about the wait! I pinged USPS and the parcel missed a scan in Memphis. It is moving again and should arrive by Friday.",
             "Thanks for checking. It did move last night, but the ETA jumped again.",
             "I'm flagging it for priority re-ship if there is no delivery scan within 48 hours."]),
        ("u4", 44, "Color looks different from photos", TicketCategory.QUALITY, TicketStatus.PROCESSING,
         "cs", ("u4", 45), None, None, None, [
             "The color of my set looks way warmer than the product photos on the site.",
             "Sorry it didn't match! Studio lighting can shift tones. I can set up a free exchange for a cooler shade, want me to?"]),
        ("u12", 15, "Return label never arrived", TicketCategory.RETURN, TicketStatus.WAITING_USER,
         "cs", ("u12", 16), None, None, None, [
             "I requested a return but never got the prepaid label email.",
             "Apologies! Our label provider had an outage. I have re-issued it, could you confirm it lands in your inbox?",
             "Nothing yet, I checked spam too.",
             "I have sent a direct link as well. Please confirm once you see it and I'll extend your return window by a week."]),
        ("u5", 17, "Refund amount seems short", TicketCategory.QUALITY, TicketStatus.WAITING_USER,
         "cs", ("u5", 19), None, None, None, [
             "My refund seems short, I paid more than what landed back on my card.",
             "Good catch! Partial returns are refunded per item including the tax share plus a return shipping credit.",
             "I returned the french tips but kept the other two items, if that helps.",
             "That is exactly right. I've emailed the full breakdown, could you confirm it matches your statement?"]),
        ("u3", 33, "Exchange for a smaller size?", TicketCategory.RETURN, TicketStatus.CLOSED,
         "cs", ("u3", 36), 30, 4, 1, [
             "The Short Almond runs wide on me, can I exchange my order for Medium Square?",
             "Absolutely, exchanges are free within 30 days. Want me to email the exchange label?",
             "Yes please. Do I need to keep the original box?",
             "Any padded envelope works! Your exchange ships today and tracking follows shortly."]),
        ("u11", 40, "Which set for short bitten nails?", TicketCategory.PRESALE, TicketStatus.CLOSED,
         "cs", None, 38, 5, 1, [
             "I bite my nails pretty short. Which set would actually fit me?",
             "Short Almond in the 24-piece box was designed for shorter nail beds, most biters start there. The included sizer helps fine-tune!"]),
    ]
    for i, (uk, ago, subject, cat, st_enum, assign_key, order_key,
            close_ago, satisfaction, close_reason, msgs) in enumerate(TICKETS):
        u, _addr = hist[uk]
        created = now - timedelta(days=ago)
        order_no = orders_by_key[order_key][0].order_no if order_key else None
        tk = Ticket(ticket_no=f"TK{created.strftime('%y%m%d')}{i + 1:04d}", user_id=u.id,
                    email=u.email, order_no=order_no, category=int(cat), priority=1,
                    subject=subject, status=int(st_enum),
                    assignee_admin_id=cs.id if assign_key == "cs" else None,
                    first_reply_at=created + timedelta(hours=3) if len(msgs) > 1 else None,
                    closed_at=now - timedelta(days=close_ago) if close_ago else None,
                    close_reason=close_reason, satisfaction=satisfaction, created_at=created)
        s.add(tk)
        s.flush()
        for j, content in enumerate(msgs):
            s.add(TicketMessage(ticket_id=tk.id, sender=1 if j % 2 == 0 else 2,
                                content=content, created_at=created + timedelta(hours=3 * j + 1)))

    # ===== 在线聊天演示会话（人工待接入 / 美甲师进行中 / AI 已问一轮）=====
    artists_map = {a.email.split("@")[0]: a for a in
                   s.query(User).filter(User.role == int(UserRole.ARTIST)).all()}
    for i, (uk, channel, artist_key, agent, st, msgs) in enumerate([
        ("u2", 1, None, ops, 0, [  # 人工：客户问折扣码，客服已接入
            (1, "Hi! Do you have any promo codes active right now?"),
            (3, "Agent Ops Team joined the chat."),
            (2, "Hey Mason! Yes — WELCOME20 for 20% off your first order, and free shipping over $35 💜")]),
        ("u5", 1, None, None, 0, [  # 合并客服：AI 对话中客户要求转人工 → 原地升级（记录保留，待接入）
            (4, "Hi, glam! 💅 I'm GlowBot — how can I help today?"),
            (1, "My package arrived with one nail broken 😢"),
            (4, "So sorry to hear that! Quality issues are fully covered — want me to connect a human agent for a replacement?"),
            (1, "Yes please, talk to a human"),
            (3, "Switched to a human agent — your chat history stays with you."),
            (3, "Connecting you to a human agent 💜 Average first reply is under 4 hours; you can keep typing.")]),
        ("u3", 2, "mia", None, 0, [  # 美甲师：定制咨询进行中
            (3, "Nail artist Mia Chen joined the chat."),
            (1, "Hi Mia! I'm getting married in June — thinking soft french with tiny pearls?"),
            (5, "Congrats Sophia!! Bare Gems with pearl accents would be PERFECT for that. "
                "Let's map your sizes first — do you have our sizer kit?")]),
        ("u9", 0, None, None, 1, [  # AI：已关闭的历史会话
            (4, "Hi, glam! 💅 I'm GlowBot — how can I help today?"),
            (1, "how long does shipping take?"),
            (4, "Shipping: US standard $4.99 (3–6 days), express $14.99 (1–3 days); free over $35.00."),
            (3, "Conversation closed. Tap any channel to start a new one.")]),
    ]):
        u = hist[uk][0]
        created = now - timedelta(days=i, hours=i + 1)
        artist = artists_map.get(artist_key)
        conv = ChatConversation(
            conv_no=f"CV{created.strftime('%y%m%d')}{i + 1:04d}", channel=channel,
            user_id=u.id, guest_token=f"seed-{uk}-{i + 1:04d}", email=u.email, name=u.name,
            lang="en", artist_id=artist.id if artist else None,
            agent_admin_id=agent.id if agent else None, status=st,
            created_at=created,
            closed_at=now - timedelta(days=i) if st == 1 else None,
        )
        s.add(conv)
        s.flush()
        last_at = created
        for j, (sender, content) in enumerate(msgs):
            last_at = created + timedelta(minutes=7 * j + 2)
            s.add(ChatMessage(conversation_id=conv.id, sender=sender, content=content,
                              created_at=last_at))
        conv.last_message_at = last_at

    # ===== UGC 4 条（2 待审 + 2 上墙）=====
    for i, (uk, handle, sl, st, caption) in enumerate([
        ("u1", "@olivia.bennett", "bare-gems", 1, "Sunday reset with Bare Gems, three weeks in and still flawless."),
        ("u3", "@sophia.naildiary", "ma-damn", 1, "Ma Damn over a nude base. The red is PERFECT."),
        ("u5", "@ava.wearsit", "french-kiss", 0, "First try at french tips and I'm never going back to the salon."),
        ("u11", "@harper.reed", "golden-hour", 0, "Golden Hour in golden hour lighting. Enough said."),
    ]):
        bg, fg = PALETTES[i % len(PALETTES)]
        s.add(UgcSubmission(user_id=hist[uk][0].id, instagram_handle=handle,
                            image_url=IMG.format(bg=bg, fg=fg, label="UGC+Glam"),
                            caption=caption, related_product_id=P[sl].id, status=st,
                            points_rewarded=100 if st == 1 else 0,
                            created_at=now - timedelta(days=8 + i * 3)))

    # ===== 博客补齐（6 篇发布 + 1 篇草稿）=====
    for i, (slug, title, author, tag, st, ago) in enumerate([
        ("cat-eye-trends-2026", "Cat-Eye Nails Are Everywhere: The 2026 Trend Report",
         "Maya Chen", "trends", 1, 2),
        ("nail-care-routine", "The 10-Minute Nail Care Routine Pros Swear By",
         "Jordan Lee", "care", 1, 9),
        ("magnetic-lashes-guide", "Magnetic Lashes: The Complete Beginner's Guide",
         "Team GLOWMAG", "guides", 1, 14),
        ("velvet-nails-fall-preview", "Velvet Nails: Your Fall 2026 Preview (Draft)",
         "Maya Chen", "trends", 0, 1),
    ]):
        bg, fg = PALETTES[(i + 2) % len(PALETTES)]
        body = (
            f"# {title}\n\n"
            f"Salon results at home are no longer a promise, they are **the baseline**. "
            f"After scanning thousands of customer photos and wear-test diaries, we distilled "
            f"what actually matters into this guide.\n\n"
            f"**Why it works**\n\n"
            f"- Prep beats product: 60 seconds with the included buffer doubles wear time\n"
            f"- Thin, even layers of glue outperform one thick bead\n"
            f"- Keep a spare set in your bag, momentum killers are optional\n\n"
            f"We tested every tip across **oily, dry and normal nail beds** for three weeks straight. "
            f"The winners held for a full 14 days of typing, dish washing and gym sessions.\n\n"
            f"## The takeaway\n\n"
            f"Pick one habit from the list above and keep it for a month. Your sets will last longer, "
            f"look better and cost less per wear than any salon alternative."
        )
        s.add(Article(slug=slug, title=title, author=author, tags=[tag, "nails"], status=st,
                      cover=IMG.format(bg=bg, fg=fg, label=title.replace(" ", "+")[:20]),
                      content_md=body,
                      published_at=now - timedelta(days=ago) if st == 1 else None,
                      created_at=now - timedelta(days=ago + 2)))

    # ===== 库存流水（每商品 1 采购 + 低库存 2 手工调整 + 售罄 2 损耗）=====
    MV_EXTRA = {"winter-storm": (11, -3, 7), "midnight-muse": (5, -2, 7),
                "cherry-bomb": (40, -40, 8), "nova": (25, -25, 8)}
    for slug, p in P.items():
        v = s.query(Variant).filter(Variant.product_id == p.id).order_by(Variant.id).first()
        purch, adj, adj_type = MV_EXTRA.get(slug, (v.stock, 0, 7))
        s.add(StockMovement(variant_id=v.id, change=purch, stock_after=purch,
                            type=int(StockMovementType.PURCHASE), ref_type="purchase",
                            operator="seed", created_at=now - timedelta(days=45)))
        if adj:
            s.add(StockMovement(variant_id=v.id, change=adj, stock_after=purch + adj,
                                type=int(adj_type), ref_type="count", operator="seed",
                                created_at=now - timedelta(days=20)))

    # ===== newsletter 8 + email_preferences（1 退订）=====
    for i, (email, source, synced) in enumerate([
        ("olivia.bennett@gmail.com", "popup", 1), ("mason.carter@outlook.com", "popup", 0),
        ("ava.thompson@gmail.com", "checkout", 1), ("noah.patel@proton.me", "footer", 0),
        ("harper.reed@gmail.com", "popup", 0), ("evelyn.cox@me.com", "checkout", 0),
        ("lucas.gray@msn.com", "footer", 0), ("glamfan.kay@duck.com", "popup", 0),
    ]):
        s.add(NewsletterSubscriber(email=email, source=source, klaviyo_synced=synced,
                                   created_at=now - timedelta(days=5 + i)))
    s.add(EmailPreference(email="evelyn.cox@me.com", user_id=hist["u12"][0].id, sub_promo=0,
                          sub_new_arrival=0, sub_cart_abandon=0,
                          unsubscribed_at=now - timedelta(days=10), source="account"))

    # ===== emma UNFREEZE 流水（reason=2 +311 frozen=0）=====
    s.add(PointsLedger(user_id=emma.id, change=311, reason=int(PointsReason.UNFREEZE),
                       balance_after=emma.points + 311, ref_type="order", ref_id=demo.id,
                       frozen=0, created_at=now - timedelta(days=3)))

    # ===== 推荐 1 条（emma → u1，REGISTERED）：/refer stats 有数；幂等（uk code+email）=====
    emma_code = derive_code(emma.id)
    if s.query(Referral).filter(Referral.code == emma_code,
                                Referral.invited_email == hist["u1"][0].email).first() is None:
        s.add(Referral(code=emma_code, referrer_user_id=emma.id,
                       invited_email=hist["u1"][0].email,
                       invited_user_id=hist["u1"][0].id,
                       status=int(ReferralStatus.REGISTERED),
                       created_at=now - timedelta(days=20)))

    # 折扣码 used_count 同步核销历史
    dc_map["WELCOME20"].used_count = s.query(DiscountRedemption).filter(
        DiscountRedemption.code_id == dc_map["WELCOME20"].id).count()
    dc_map["EARLYBIRD"].used_count = s.query(DiscountRedemption).filter(
        DiscountRedemption.code_id == dc_map["EARLYBIRD"].id).count()

    # ===== P0-B 追加：变体图（bare-gems 2 变体各 2 / venus 首 2 / ma-damn 首 1）=====
    VAR_IMG_PLAN = {"bare-gems": (2, 2), "venus": (2, 0), "ma-damn": (1, 0)}
    VAR_VIEWS = ["Macro", "On+Hand"]
    for slug, (n_first, n_second) in VAR_IMG_PLAN.items():
        p0 = P[slug]
        bg, fg = PALETTES[[c[0] for c in CATALOG].index(slug) % len(PALETTES)]
        base = p0.title.replace(" ", "+")
        for vi, v0 in enumerate(s.query(Variant).filter(Variant.product_id == p0.id)
                                .order_by(Variant.id).all()[:2]):
            shape = v0.option1_value.replace(" ", "+")
            for k in range(n_first if vi == 0 else n_second):
                s.add(VariantImage(
                    variant_id=v0.id, sort_order=k,
                    image_url=IMG.format(bg=bg, fg=fg,
                                         label=f"{base}+{shape}+{VAR_VIEWS[k % len(VAR_VIEWS)]}")))

    # P0-B 追加：UGC 上墙补 2 条（既有 2 条上墙 related_product_id 均已关联有效商品）
    for i, (uk, handle, sl, caption) in enumerate([
        ("u2", "@mason.carter", "venus",
         "Venus pearl chrome for date night. Day 9 and still glassy."),
        ("u7", "@mia.foster", "peachy-keen",
         "Peachy Keen right after the beach. My whole summer in one set."),
    ]):
        bg, fg = PALETTES[(i + 3) % len(PALETTES)]
        s.add(UgcSubmission(user_id=hist[uk][0].id, instagram_handle=handle,
                            image_url=IMG.format(bg=bg, fg=fg, label="UGC+Wall"),
                            caption=caption, related_product_id=P[sl].id, status=1,
                            points_rewarded=100,
                            created_at=now - timedelta(days=4 + i)))

    # ===== 商品中文翻译（product_translations 影子表 · title 对齐 prototype/assets/app.js GM_CATALOG.titleZh）=====
    from app.models import ProductTranslation
    for slug, zh_title, zh_sub, zh_desc in [
        ("bare-gems", "裸钻", "裸色打底缀水晶，法式温柔天花板",
         "**裸钻** —— 裸色基底缀以水晶点缀，24 片含工具套装，salon 级穿戴甲，单次佩戴可达 2 周。"),
        ("french-kiss", "法式之吻", "永不过时的经典法式白边",
         "**法式之吻** —— 经典法式指尖一贴即得，24 片含工具套装，salon 级穿戴甲，单次佩戴可达 2 周。"),
        ("venus", "维纳斯", "珍珠铬猫眼甲面，指尖上的雕塑感",
         "**维纳斯** —— 珍珠铬猫眼甲面流转粉金光泽，日光下也层次分明；24 片含工具套装，单次佩戴可达 2 周。"),
        ("venus-lash", "维纳斯睫毛", "珍珠黑猫眼款，磁吸一夹即贴",
         "**维纳斯睫毛** —— 珍珠黑猫眼走向，磁吸设计无需胶水，轻夹即贴；日常到晚宴都撑得住，妥善保养可重复佩戴约 20 次。"),
        ("aurora-lash", "极光睫毛", "仙子款渐长睫毛，裸感自然",
         "**极光睫毛** —— 长短交错的仙子款，眨眼自带 flutter 效果；磁吸上手约 60 秒，新手也能一次成功，是日常淡妆的天然搭子。"),
        ("midnight-lash", "午夜睫毛", "浓密大眼款，夜场拍照必备",
         "**午夜睫毛** —— 高密度分层 Band，夜场灯光与闪光灯下都是大眼担当；磁吸一整晚不跑位，叠画眼线效果更炸，可重复佩戴约 20 次。"),
    ]:
        s.add(ProductTranslation(product_id=P[slug].id, locale="zh-CN",
                                 title=zh_title, subtitle=zh_sub, description_md=zh_desc))

    s.commit()

    # ===== 汇总 =====
    dormant = sum(1 for uk, (u, _a) in hist.items()
                  if u.last_order_at and u.last_order_at < now - timedelta(days=60))
    silver = sum(1 for uk, (u, _a) in hist.items() if u.tier == 1)
    gold = sum(1 for uk, (u, _a) in hist.items() if u.tier == 2)
    def stat(m, *f):
        q = s.query(func.count()).select_from(m)
        if f:
            q = q.filter(*f)
        return q.scalar() or 0
    print("operational seed summary:")
    print(f"  users={s.query(User).count()} (hist=12 risk=2 dormant>60d={dormant} silver={silver} gold={gold})")
    print(f"  orders={s.query(Order).count()} hist_items={s.query(OrderItem).count() - 2} "
          f"(completed={stat(Order, Order.status == 5)} shipped={stat(Order, Order.status == 3)} "
          f"canceled={stat(Order, Order.status == 8)} refunded={stat(Order, Order.status == 9)})")
    print(f"  payments={s.query(Payment).count()} shipments={s.query(Shipment).count()} "
          f"timeline={s.query(OrderTimeline).count()}")
    print(f"  reviews={s.query(Review).count()} (approved={stat(Review, Review.status == 1)} "
          f"pending={stat(Review, Review.status == 0)} rejected={stat(Review, Review.status == 2)} "
          f"with_images={stat(Review, Review.images.isnot(None))})")
    print("  lash reviews(approved): " + ", ".join(
        f"{sl}={len(rs)}" for sl, rs in sorted(agg.items()) if sl in _LASH_SLUG_SET))
    dist = [stat(Review, Review.rating == r) for r in (5, 4, 3, 2, 1)]
    print(f"  rating dist 5/4/3/2/1 = {dist}")
    print(f"  rmas={s.query(Rma).count()} tickets={s.query(Ticket).count()} "
          f"ticket_messages={s.query(TicketMessage).count()} "
          f"ugc={s.query(UgcSubmission).count()} (wall={stat(UgcSubmission, UgcSubmission.status == 1)})")
    print(f"  variant_images={s.query(VariantImage).count()} "
          f"(bare-gems=4 venus=2 ma-damn=1)")
    scheduled = stat(Product, Product.status == 1, Product.published_at > now)
    print(f"  scheduled_products={scheduled} (velvet-nights published_at=now+7d, 前台查询时不可见)")
    print(f"  articles={s.query(Article).count()} (published={stat(Article, Article.status == 1)}) "
          f"redemptions={s.query(DiscountRedemption).count()} "
          f"(WELCOME20={dc_map['WELCOME20'].used_count} EARLYBIRD={dc_map['EARLYBIRD'].used_count})")
    print(f"  stock_movements={s.query(StockMovement).count()} newsletter={s.query(NewsletterSubscriber).count()} "
          f"(klaviyo_synced={stat(NewsletterSubscriber, NewsletterSubscriber.klaviyo_synced == 1)}) "
          f"email_prefs={s.query(EmailPreference).count()} points_ledger={s.query(PointsLedger).count()}")
    print(f"  translations={s.query(ProductTranslation).count()} "
          f"(zh-CN: bare-gems/french-kiss/venus + 3 睫毛)")
    print(f"  referrals={s.query(Referral).count()} (emma→u1 REGISTERED)")
    s.close()


if __name__ == "__main__":
    if "--reset" in sys.argv[1:]:
        Base.metadata.drop_all(engine)
        print("seed: --reset → drop_all done")
    seed()
