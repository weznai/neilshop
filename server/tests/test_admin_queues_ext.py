"""admin 队列扩展自测 —— 低库存口径 / 列表 pages 契约 / 订阅盒管理 / 弃购队列 /
对账历史 / GDPR 数据请求队列 / Newsletter 订阅者 / 管理员账号管理（超管）/ 媒体库列表与删除。
（GM_DB=sqlite:///test_admin_queues_ext.sqlite 独立库；BigInteger 垫片同 test_admin_ops_ext.py；
直跑与 pytest 双兼容：main() 承载全部断言，尾部 __main__ 约定 + pytest 包装函数）"""

import os
import shutil
import sys
from datetime import date, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_admin_queues_ext.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
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

from app.core.db import SessionLocal, utcnow  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AdminLog, Article, Cart, Category, DataRequest, DiscountCode,
    DiscountRedemption, Faq, GiftCard, GiftCardLedger, NewsletterSubscriber,
    Order, Product, ReconciliationDaily, Review, Subscription, UgcSubmission,
    User, Variant,
)

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
        "zip": "94110", "country": "US"}

MEDIA_DIR = os.path.join(_ROOT, "static", "uploads", "999901")


def main() -> int:
    with TestClient(app) as client:
        s = SessionLocal()
        admin = User(email="qops@glow.test", password_hash=hash_password("x"),
                     name="QOps", role=2)
        super_admin = User(email="qsuper@glow.test", password_hash=hash_password("x"),
                           name="QSuper", role=9)
        s.add_all([admin, super_admin])
        s.commit()
        H_OPS = {"Authorization": f"Bearer {create_token(admin.id, admin.role)}"}
        H_SUP = {"Authorization": f"Bearer {create_token(super_admin.id, super_admin.role)}"}

        # ===== 1. 低库存统一口径 stock <= max(safety_stock, 8) 且仅 is_active =====
        cat = Category(slug="qcat", name="QCat")
        s.add(cat)
        s.flush()
        prod = Product(slug="qprod", title="Q Prod", category_id=cat.id, status=1,
                       hero_image="https://img/q.jpg", price_min=1599, price_max=1599)
        s.add(prod)
        s.flush()
        v_low_safety = Variant(product_id=prod.id, sku="Q-SAF20", option1_value="A",
                               option2_value="24pcs", price=1599, stock=15, safety_stock=20)
        v_low_plain = Variant(product_id=prod.id, sku="Q-SAF8", option1_value="B",
                              option2_value="24pcs", price=1599, stock=8, safety_stock=0)
        v_boundary = Variant(product_id=prod.id, sku="Q-SAF9", option1_value="E",
                             option2_value="24pcs", price=1599, stock=9, safety_stock=0)
        v_inactive = Variant(product_id=prod.id, sku="Q-OFF", option1_value="C",
                             option2_value="24pcs", price=1599, stock=9, safety_stock=0,
                             is_active=0)
        v_enough = Variant(product_id=prod.id, sku="Q-OK", option1_value="D",
                           option2_value="24pcs", price=1599, stock=50, safety_stock=5)
        s.add_all([v_low_safety, v_low_plain, v_boundary, v_inactive, v_enough])
        s.commit()
        r = client.get("/api/admin/ops/dashboard", headers=H_OPS)
        d = r.json()
        check("低库存口径：safety=20/库存15 计入 + 库存8/safety0 计入（边界含）",
              r.status_code == 200 and d["low_stock"] == 2, d.get("low_stock"))
        top_skus = {t["sku"] for t in d["low_stock_top"]}
        check("库存9/safety0 不计（9>max(0,8)=8）+ is_active=0 不计",
              "Q-SAF9" not in top_skus and "Q-OFF" not in top_skus, top_skus)
        check("low_stock_top 命中同口径 SKU（升序首行 stock=8）",
              top_skus == {"Q-SAF20", "Q-SAF8"}
              and d["low_stock_top"][0]["stock"] == 8, d.get("low_stock_top"))

        # ===== 2. pages 契约矩阵（ops + promo + content）=====
        m1 = User(email="qm1@glow.test", password_hash=hash_password("x"), name="M1")
        m2 = User(email="qm2@glow.test", password_hash=hash_password("x"), name="M2")
        m3 = User(email="qm3@glow.test", password_hash=hash_password("x"), name="M3")
        s.add_all([m1, m2, m3])
        s.commit()
        d = client.get("/api/admin/ops/members", headers=H_OPS,
                       params={"size": 2}).json()
        check("ops members pages=ceil(3/2)=2",
              d["total"] == 3 and d["pages"] == 2 and len(d["items"]) == 2,
              (d.get("total"), d.get("pages")))
        for i in range(3):
            s.add(Review(product_id=prod.id, user_id=m1.id, order_item_id=100 + i,
                         rating=5, content=f"r{i}", status=0))
        for i in range(3):
            s.add(UgcSubmission(user_id=m1.id, image_url=f"https://img/u{i}.png",
                                caption=f"u{i}", status=0))
        for i in range(3):
            s.add(Article(slug=f"qart{i}", title=f"A{i}", author="Team",
                          content_md="x" * 20, status=1))
        for i in range(3):
            s.add(Faq(category=1, question=f"Q{i}", answer_md="a", sort_order=i))
        for i in range(3):
            s.add(AdminLog(admin_id=admin.id, action="seed", entity="member",
                           entity_id=i + 1))
        s.commit()
        d = client.get("/api/admin/ops/reviews", headers=H_OPS,
                       params={"size": 2}).json()
        check("ops reviews pages=2", d["total"] == 3 and d["pages"] == 2,
              (d.get("total"), d.get("pages")))
        d = client.get("/api/admin/ops/ugc", headers=H_OPS,
                       params={"size": 2}).json()
        check("ops ugc pages=2", d["total"] == 3 and d["pages"] == 2,
              (d.get("total"), d.get("pages")))
        d = client.get("/api/admin/ops/logs", headers=H_OPS,
                       params={"size": 2}).json()
        check("ops logs pages 与 total 自洽（先垫 3 条审计）",
              d["total"] == 3 and d["pages"] == 2,
              (d.get("total"), d.get("pages")))
        d = client.get("/api/admin/ops/articles", headers=H_OPS,
                       params={"size": 2}).json()
        check("content articles pages=2", d["total"] == 3 and d["pages"] == 2,
              (d.get("total"), d.get("pages")))
        d = client.get("/api/admin/ops/faqs", headers=H_OPS,
                       params={"size": 2}).json()
        check("content faqs pages=2", d["total"] == 3 and d["pages"] == 2,
              (d.get("total"), d.get("pages")))
        dc = DiscountCode(code="QPAGE10", type=1, value=10, starts_at=utcnow())
        s.add(dc)
        s.flush()
        for i in range(3):
            o = Order(order_no=f"QPG{i}", email=f"qp{i}@glow.test", status=1,
                      subtotal=2000, grand_total=1800, shipping_address=ADDR,
                      placed_at=utcnow(), paid_at=utcnow())
            s.add(o)
            s.flush()
            s.add(DiscountRedemption(code_id=dc.id, order_id=o.id,
                                     email=o.email, discount_amount=200))
        for i in range(3):
            s.add(DiscountCode(code=f"QDC{i}", type=1, value=5, starts_at=utcnow()))
        gc = GiftCard(code="GC-Q-PAGE-001", initial_amount=3000, balance=3000,
                      status=1, purchaser_email="q@glow.test")
        s.add(gc)
        s.flush()
        for i in range(3):
            s.add(GiftCardLedger(gift_card_id=gc.id, change_type=3, amount=100 * (i + 1),
                                 balance_after=3000 - 100 * (i + 1)))
        s.commit()
        d = client.get("/api/admin/ops/discounts", headers=H_OPS,
                       params={"size": 2}).json()
        check("promo discounts pages=2", d["total"] == 4 and d["pages"] == 2,
              (d.get("total"), d.get("pages")))
        d = client.get("/api/admin/promo/giftcards", headers=H_OPS,
                       params={"size": 2}).json()
        check("promo giftcards pages=1（单卡）", d["total"] == 1 and d["pages"] == 1,
              (d.get("total"), d.get("pages")))
        d = client.get(f"/api/admin/promo/discounts/{dc.id}/usages", headers=H_OPS,
                       params={"size": 2}).json()
        check("promo discount usages pages=2", d["total"] == 3 and d["pages"] == 2,
              (d.get("total"), d.get("pages")))
        d = client.get(f"/api/admin/promo/giftcards/{gc.id}/ledger", headers=H_OPS,
                       params={"size": 2}).json()
        check("promo giftcard ledger pages=2", d["total"] == 3 and d["pages"] == 2,
              (d.get("total"), d.get("pages")))

        # ===== 3. 订阅盒管理（/api/admin/member/subscriptions）=====
        sub_user = User(email="qsub@glow.test", password_hash=hash_password("x"),
                        name="SubUser")
        s.add(sub_user)
        s.commit()
        base = utcnow()
        sub_active = Subscription(user_id=sub_user.id, stripe_subscription_id="SUBMOCKqa",
                                  plan=1, style_mode=1, status=1,
                                  next_billing_at=base + timedelta(days=28),
                                  created_at=base - timedelta(days=2))
        sub_paused = Subscription(user_id=sub_user.id, stripe_subscription_id="SUBMOCKqb",
                                  plan=2, style_mode=2, status=2,
                                  next_billing_at=base + timedelta(days=42),
                                  created_at=base - timedelta(days=1))
        sub_canceled = Subscription(user_id=sub_user.id, stripe_subscription_id="SUBMOCKqc",
                                    plan=3, style_mode=1, status=5,
                                    next_billing_at=base + timedelta(days=56),
                                    cancel_reason=1, created_at=base)
        s.add_all([sub_active, sub_paused, sub_canceled])
        s.commit()
        r = client.get("/api/admin/member/subscriptions", headers=H_OPS,
                       params={"size": 2})
        d = r.json()
        check("订阅列表分页 pages=2 且 created_at 倒序（canceled 最前）",
              r.status_code == 200 and d["total"] == 3 and d["pages"] == 2
              and d["items"][0]["id"] == sub_canceled.id,
              (d.get("total"), d.get("pages")))
        check("订阅行含 email/方案/金额/下一期（plan_text + price_cents）",
              d["items"][0]["email"] == "qsub@glow.test"
              and d["items"][0]["price_cents"] == 1499
              and d["items"][0]["next_billing_at"] is not None, d["items"][0])
        d = client.get("/api/admin/member/subscriptions", headers=H_OPS,
                       params={"status": 2}).json()
        check("订阅列表 status 过滤（仅暂停 1 条）",
              d["total"] == 1 and d["items"][0]["id"] == sub_paused.id, d.get("total"))
        check("订阅端点需要鉴权",
              client.get("/api/admin/member/subscriptions").status_code == 401)
        r = client.post(f"/api/admin/member/subscriptions/{sub_active.id}/pause",
                        headers=H_OPS, json={})
        check("管理端暂停生效中 → 200 status=2",
              r.status_code == 200 and r.json()["status"] == 2, r.text[:120])
        r = client.post(f"/api/admin/member/subscriptions/{sub_active.id}/pause",
                        headers=H_OPS, json={})
        check("重复暂停 → 409 not active（对齐用户侧）",
              r.status_code == 409 and r.json()["detail"] == "not active",
              (r.status_code, r.json().get("detail")))
        r = client.post(f"/api/admin/member/subscriptions/{sub_active.id}/resume",
                        headers=H_OPS)
        check("管理端恢复已暂停 → 200 status=1",
              r.status_code == 200 and r.json()["status"] == 1, r.text[:120])
        r = client.post(f"/api/admin/member/subscriptions/{sub_active.id}/resume",
                        headers=H_OPS)
        check("恢复生效中 → 409 not paused",
              r.status_code == 409 and r.json()["detail"] == "not paused",
              (r.status_code, r.json().get("detail")))
        r = client.post(f"/api/admin/member/subscriptions/{sub_paused.id}/cancel",
                        headers=H_OPS, json={"cancel_reason": 2})
        check("管理端取消已暂停 → 200 status=5 reason=2",
              r.status_code == 200 and r.json()["status"] == 5
              and r.json()["cancel_reason"] == 2, r.text[:120])
        r = client.post(f"/api/admin/member/subscriptions/{sub_canceled.id}/cancel",
                        headers=H_OPS, json={})
        check("取消已取消 → 409 not cancellable",
              r.status_code == 409 and r.json()["detail"] == "not cancellable",
              (r.status_code, r.json().get("detail")))
        check("未知订阅 → 404 subscription not found",
              client.post("/api/admin/member/subscriptions/999999/cancel",
                          headers=H_OPS, json={}).status_code == 404)
        d = client.get("/api/admin/ops/logs", headers=H_OPS,
                       params={"entity": "subscription", "size": 10}).json()
        check("订阅代操作审计落库（pause/resume/cancel）",
              d["total"] == 3 and {i["action"] for i in d["items"]}
              >= {"pause", "resume", "cancel"}, d.get("total"))

        # ===== 4. 弃购队列（口径对齐 worker：有商品 + 超 1 小时未动）=====
        now = utcnow()
        s.add_all([
            Cart(session_id="tok-q-old", email="qold@glow.test",
                 items=[{"variantId": v_low_safety.id, "qty": 2}],
                 created_at=now - timedelta(days=3), updated_at=now - timedelta(days=3)),
            Cart(session_id="tok-q-fresh", email="qfresh@glow.test",
                 items=[{"variantId": v_low_plain.id, "qty": 1}],
                 created_at=now - timedelta(minutes=40), updated_at=now - timedelta(minutes=30)),
            Cart(session_id="tok-q-empty", email="qempty@glow.test",
                 items=[], created_at=now - timedelta(days=5), updated_at=now - timedelta(days=5)),
        ])
        s.commit()
        r = client.get("/api/admin/ops/abandoned-carts", headers=H_OPS)
        d = r.json()
        check("弃购队列：仅「有商品 + 超 1h」cart（1 条）",
              r.status_code == 200 and d["total"] == 1
              and d["items"][0]["email"] == "qold@glow.test",
              (r.status_code, d.get("total")))
        row = d["items"][0]
        check("弃购行结构：件数/金额/最后活跃/距今天数",
              row["items_count"] == 1 and row["total_qty"] == 2
              and row["amount_cents"] == 2 * 1599 and row["updated_at"] is not None
              and 2.9 < (row["days_ago"] or 0) < 3.1, row)
        check("弃购端点需要鉴权",
              client.get("/api/admin/ops/abandoned-carts").status_code == 401)

        # ===== 5. 对账历史 =====
        s.add_all([
            ReconciliationDaily(reconcile_date=date(2026, 8, 21), payments_gross=1000,
                                orders_paid_total=1000, diff_payment=0, diff_refund=0,
                                points_ledger_sum=0, users_points_sum=0, diff_points=0,
                                status=0, checked_at=utcnow()),
            ReconciliationDaily(reconcile_date=date(2026, 8, 22), payments_gross=2000,
                                orders_paid_total=1900, diff_payment=100, diff_refund=0,
                                points_ledger_sum=10, users_points_sum=10, diff_points=0,
                                status=1, checked_at=utcnow()),
            ReconciliationDaily(reconcile_date=date(2026, 8, 23), payments_gross=3000,
                                orders_paid_total=3000, diff_payment=0, diff_refund=0,
                                points_ledger_sum=0, users_points_sum=0, diff_points=0,
                                status=0, checked_at=utcnow()),
        ])
        s.commit()
        r = client.get("/api/admin/ops/reconciliations", headers=H_OPS,
                       params={"size": 2})
        d = r.json()
        check("对账历史分页 pages=2 按日期倒序",
              r.status_code == 200 and d["total"] == 3 and d["pages"] == 2
              and str(d["items"][0]["reconcile_date"]).startswith("2026-08-23"),
              (d.get("total"), d.get("pages"), d.get("items")[:1]))
        check("对账行含 GMV/笔数字段（payments_gross/差异）",
              d["items"][0]["payments_gross"] == 3000
              and "diff_payment" in d["items"][0] and "status" in d["items"][0],
              d["items"][0] if d.get("items") else None)
        d = client.get("/api/admin/ops/reconciliations", headers=H_OPS,
                       params={"date_from": "2026-08-22"}).json()
        check("对账 date_from 过滤（2 条）", d["total"] == 2, d.get("total"))
        d = client.get("/api/admin/ops/reconciliations", headers=H_OPS,
                       params={"date_from": "2026-08-22", "date_to": "2026-08-22"}).json()
        check("对账 date_from+date_to 闭区间（1 条）", d["total"] == 1, d.get("total"))

        # ===== 6. GDPR 数据请求队列 =====
        gdpr_user = User(email="qgdpr@glow.test", password_hash=hash_password("x"),
                         name="GdprU", points=77)
        s.add(gdpr_user)
        s.flush()
        req_exec = DataRequest(user_id=gdpr_user.id, type=2, status=0,
                               created_at=utcnow() - timedelta(days=1))
        req_rej = DataRequest(user_id=gdpr_user.id, type=2, status=0,
                              created_at=utcnow() - timedelta(days=2))
        req_export = DataRequest(user_id=gdpr_user.id, type=1, status=1,
                                 fulfilled_at=utcnow(), created_at=utcnow())
        s.add_all([req_exec, req_rej, req_export])
        s.commit()
        r = client.get("/api/admin/ops/data-requests", headers=H_OPS,
                       params={"size": 2})
        d = r.json()
        check("数据请求分页 pages=2 含 email/类型/状态",
              r.status_code == 200 and d["total"] == 3 and d["pages"] == 2
              and d["items"][0]["email"] == "qgdpr@glow.test",
              (r.status_code, d.get("total"), d.get("pages")))
        d = client.get("/api/admin/ops/data-requests", headers=H_OPS).json()
        row_export = d["items"][0]
        row_exec = next(i for i in d["items"] if i["id"] == req_exec.id)
        check("数据请求行：类型文本 + 申请时间 + 计划执行时间（删除类）",
              row_export["type"] == 1 and row_export["type_text"] == "导出"
              and row_export["scheduled_at"] is None
              and row_exec["type"] == 2 and row_exec["scheduled_at"] is not None
              and row_exec["created_at"] is not None,
              (row_export, row_exec))
        d = client.get("/api/admin/ops/data-requests", headers=H_OPS,
                       params={"type": 2, "status": 0}).json()
        check("数据请求 type/status 组合过滤（2 条 pending 删除）",
              d["total"] == 2 and all(i["type"] == 2 and i["status"] == 0
                                      for i in d["items"]), d.get("total"))
        r = client.post(f"/api/admin/ops/data-requests/{req_exec.id}/execute",
                        headers=H_OPS)
        d = r.json()
        s.expire_all()
        u_db = s.get(User, gdpr_user.id)
        req_db = s.get(DataRequest, req_exec.id)
        check("execute 立即执行 → 200 + 用户匿化（deleted+ 前缀/清分/注销）",
              r.status_code == 200 and d == {"id": req_exec.id, "status": 1,
                                             "anonymized": True}
              and u_db.email == f"deleted+{gdpr_user.id}@anonymized.local"
              and u_db.points == 0 and u_db.status == -1,
              (r.status_code, r.text[:120]))
        check("execute 后 DataRequest status=1 + fulfilled_at 落库",
              req_db.status == 1 and req_db.fulfilled_at is not None,
              (req_db.status, req_db.fulfilled_at))
        r = client.post(f"/api/admin/ops/data-requests/{req_exec.id}/execute",
                        headers=H_OPS)
        check("重复 execute → 409",
              r.status_code == 409 and r.json()["detail"] == "request not pending",
              (r.status_code, r.json().get("detail")))
        r = client.post(f"/api/admin/ops/data-requests/{req_rej.id}/reject",
                        headers=H_OPS)
        check("reject 待处理 → 200 status=2（驳回）",
              r.status_code == 200 and r.json() == {"id": req_rej.id, "status": 2},
              r.text[:120])
        r = client.post(f"/api/admin/ops/data-requests/{req_rej.id}/reject",
                        headers=H_OPS)
        check("重复 reject → 409",
              r.status_code == 409, r.status_code)
        r = client.post(f"/api/admin/ops/data-requests/{req_export.id}/execute",
                        headers=H_OPS)
        check("已完成的导出单 execute → 409",
              r.status_code == 409, r.status_code)
        check("数据请求 404 与鉴权",
              client.post("/api/admin/ops/data-requests/999999/reject",
                          headers=H_OPS).status_code == 404
              and client.get("/api/admin/ops/data-requests").status_code == 401)
        d = client.get("/api/admin/ops/logs", headers=H_OPS,
                       params={"entity": "data_request", "size": 10}).json()
        check("GDPR 审计落库（execute/reject）",
              d["total"] == 2 and {i["action"] for i in d["items"]} == {"execute", "reject"},
              d.get("total"))

        # ===== 7. Newsletter 订阅者 =====
        s.add_all([
            NewsletterSubscriber(email="qa@glow.test", source="popup",
                                 created_at=now - timedelta(days=3)),
            NewsletterSubscriber(email="qb@glow.test", source="checkout",
                                 created_at=now - timedelta(days=2)),
            NewsletterSubscriber(email="qc@glow.test", source="footer",
                                 created_at=now - timedelta(days=1)),
        ])
        s.commit()
        r = client.get("/api/admin/ops/newsletters", headers=H_OPS,
                       params={"size": 2})
        d = r.json()
        check("newsletter 分页 pages=2 按订阅时间倒序（qc 最前）",
              r.status_code == 200 and d["total"] == 3 and d["pages"] == 2
              and d["items"][0]["email"] == "qc@glow.test",
              (d.get("total"), d.get("pages")))
        check("newsletter 行含 source/订阅时间",
              d["items"][0]["source"] == "footer"
              and d["items"][0]["created_at"] is not None, d["items"][0])
        d = client.get("/api/admin/ops/newsletters", headers=H_OPS,
                       params={"q": "qb@glow"}).json()
        check("newsletter q 搜索命中 1 条",
              d["total"] == 1 and d["items"][0]["email"] == "qb@glow.test",
              d.get("total"))
        d = client.get("/api/admin/ops/newsletters", headers=H_OPS,
                       params={"q": "nope@none"}).json()
        check("newsletter q 无命中 → 空", d["total"] == 0 and d["items"] == [],
              d.get("total"))

        # ===== 8. 管理员账号管理（仅超管）=====
        r = client.post("/api/admin/ops/admins", headers=H_SUP,
                        json={"email": "qnewops@glowmag.com", "name": "NewOps",
                              "password": "strongpass9", "role": 2})
        d = r.json()
        check("超管建号 → 200 role=2 status=1",
              r.status_code == 200 and d["role"] == 2 and d["status"] == 1
              and d["email"] == "qnewops@glowmag.com", r.text[:160])
        new_ops_id = d.get("id")
        s.expire_all()
        check("建号密码 bcrypt 落库（可登录）",
              client.post("/api/account/login", json={
                  "email": "qnewops@glowmag.com", "password": "strongpass9"}
              ).status_code == 200)
        r = client.post("/api/admin/ops/admins", headers=H_SUP,
                        json={"email": "qnewops@glowmag.com", "name": "Dup",
                              "password": "strongpass9", "role": 3})
        check("重复 email → 409 email exists",
              r.status_code == 409 and r.json()["detail"] == "email exists",
              (r.status_code, r.json().get("detail")))
        r = client.post("/api/admin/ops/admins", headers=H_OPS,
                        json={"email": "x2@glow.test", "name": "X",
                              "password": "strongpass9", "role": 2})
        check("非超管建号 → 403 superadmin required",
              r.status_code == 403 and r.json()["detail"] == "superadmin required",
              (r.status_code, r.json().get("detail")))
        check("非法 role=5 / 短密码 → 422",
              client.post("/api/admin/ops/admins", headers=H_SUP,
                          json={"email": "x3@glow.test", "name": "X",
                                "password": "strongpass9", "role": 5}).status_code == 422
              and client.post("/api/admin/ops/admins", headers=H_SUP,
                              json={"email": "x4@glow.test", "name": "X",
                                    "password": "short", "role": 2}).status_code == 422)
        r = client.put(f"/api/admin/ops/admins/{super_admin.id}", headers=H_SUP,
                       json={"role": 2})
        check("改自己 role → 400 cannot modify self",
              r.status_code == 400 and r.json()["detail"] == "cannot modify self",
              (r.status_code, r.json().get("detail")))
        r = client.put(f"/api/admin/ops/admins/{super_admin.id}", headers=H_SUP,
                       json={"status": 0})
        check("停用自己 → 400 cannot modify self",
              r.status_code == 400 and r.json()["detail"] == "cannot modify self",
              (r.status_code, r.json().get("detail")))
        r = client.put(f"/api/admin/ops/admins/{super_admin.id}", headers=H_SUP,
                       json={"name": "QSuper2"})
        check("改自己 name 允许 → 200",
              r.status_code == 200 and r.json()["name"] == "QSuper2", r.text[:120])
        r = client.put(f"/api/admin/ops/admins/{new_ops_id}", headers=H_SUP,
                       json={"role": 3, "status": 0})
        check("改他人 role+status → 200 生效",
              r.status_code == 200 and r.json()["role"] == 3
              and r.json()["status"] == 0, r.text[:120])
        r = client.get(f"/api/admin/ops/admins/{new_ops_id}", headers=H_SUP)
        check("管理员详情含 last_login_at（建号即登录过）",
              r.status_code == 200 and "last_login_at" in r.json()
              and r.json()["last_login_at"] is not None, r.text[:160])
        check("详情非超管 → 403 / 未知 id → 404",
              client.get(f"/api/admin/ops/admins/{new_ops_id}",
                         headers=H_OPS).status_code == 403
              and client.get("/api/admin/ops/admins/999999",
                             headers=H_SUP).status_code == 404)
        d = client.get("/api/admin/ops/logs", headers=H_OPS,
                       params={"entity": "admin", "size": 10}).json()
        check("管理员建号/更新审计落库（create/update）",
              d["total"] >= 3 and {i["action"] for i in d["items"]}
              >= {"create", "update"}, d.get("total"))

        # ===== 9. 媒体库列表与删除 =====
        os.makedirs(MEDIA_DIR, exist_ok=True)
        try:
            files = {"qq1.png": b"a", "qq2.png": b"bb", "qq3.png": b"ccc"}
            for name, blob in files.items():
                with open(os.path.join(MEDIA_DIR, name), "wb") as fh:
                    fh.write(blob)
            r = client.get("/api/admin/media", headers=H_OPS,
                           params={"q": "qq", "size": 2})
            d = r.json()
            check("媒体列表 q 过滤 + 分页 pages=2",
                  r.status_code == 200 and d["total"] == 3 and d["pages"] == 2
                  and len(d["items"]) == 2, (r.status_code, d.get("total")))
            row = client.get("/api/admin/media", headers=H_OPS,
                             params={"q": "qq1"}).json()["items"][0]
            check("媒体行结构：name/bytes/modified_at/url",
                  row["name"] == "999901/qq1.png" and row["bytes"] == 1
                  and row["modified_at"]
                  and row["url"] == "/static/uploads/999901/qq1.png", row)
            d = client.get("/api/admin/media", headers=H_OPS,
                           params={"q": "qq2"}).json()
            check("媒体 q 精确子串命中 1 条", d["total"] == 1, d.get("total"))
            check("媒体端点需要鉴权",
                  client.get("/api/admin/media").status_code == 401)
            # 引用检查：UGC 图占用 → 409
            ugc_ref = UgcSubmission(user_id=m1.id,
                                    image_url="/static/uploads/999901/qq2.png",
                                    caption="ref", status=1)
            s.add(ugc_ref)
            s.commit()
            r = client.delete("/api/admin/media/999901/qq2.png", headers=H_OPS)
            check("媒体被 UGC 引用 → 409 media in use",
                  r.status_code == 409 and r.json()["detail"] == "media in use",
                  (r.status_code, r.json().get("detail")))
            check("409 时文件未删", os.path.exists(os.path.join(MEDIA_DIR, "qq2.png")))
            s.delete(ugc_ref)
            s.commit()
            r = client.delete("/api/admin/media/999901/qq2.png", headers=H_OPS)
            check("解除引用后删除 → 200 且文件消失",
                  r.status_code == 200 and r.json()["ok"] is True
                  and not os.path.exists(os.path.join(MEDIA_DIR, "qq2.png")),
                  r.text[:120])
            r = client.delete("/api/admin/media/999901/nope.png", headers=H_OPS)
            check("删除不存在的合法文件名 → 404",
                  r.status_code == 404 and r.json()["detail"] == "file not found",
                  (r.status_code, r.json().get("detail")))
            # 路径穿越/非法名：service 单元面（穿越必须带 /，HTTP 路由层天然吃不到）
            from fastapi import HTTPException as _HttpErr

            from app.domains.media import service as _media_svc

            for bad in ("../app.py", "/etc/passwd", "a/b/../../x", "a/b/c/d/e.png",
                        "C:/win.ini", "qq*.png"):
                try:
                    _media_svc._safe_relpath(bad)
                    check(f"service 路径校验拒绝 {bad!r}", False)
                    break
                except _HttpErr as exc:
                    if exc.status_code != 400:
                        check(f"service 路径校验 {bad!r} → 400", False, exc.status_code)
                        break
            else:
                check("service 路径校验拒绝穿越/绝对/盘符/通配/超深（400 invalid filename）",
                      True)
            r = client.delete("/api/admin/media/qq%2A.png", headers=H_OPS)
            check("HTTP 非法文件名（通配符）→ 400 invalid filename",
                  r.status_code == 400 and r.json()["detail"] == "invalid filename",
                  (r.status_code, r.text[:80]))
            r = client.delete("/api/admin/media/999901%2F..%2F..%2Fx.py",
                              headers=H_OPS)
            check("HTTP 编码穿越段 → 400 invalid filename",
                  r.status_code == 400 and r.json()["detail"] == "invalid filename",
                  (r.status_code, r.text[:80]))
            d = client.get("/api/admin/ops/logs", headers=H_OPS,
                           params={"entity": "media", "action": "delete"}).json()
            check("媒体删除审计落库", d["total"] >= 1, d.get("total"))
        finally:
            shutil.rmtree(MEDIA_DIR, ignore_errors=True)

        s.close()

    print(f"\n{PASSED} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed:", FAILED)
        return 1
    return 0


def test_admin_queues_ext():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
