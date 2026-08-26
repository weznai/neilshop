"""营销/内容域修复扩展自测 —— P0-1 UGC re-approve 不重复发分 / P0-2 礼品卡 freeze 状态机穿隧 /
P1-3 max_discount 非负 / P1-4 check_giftcard 过期 / P1-5 弹窗窗口与 scene 校验 /
P1-6 先查后插撞唯一 409 / P1-9 review content 长度 / P2-10 评分 SQL 重算 / P2-11 标签云缓存。
（GM_CACHE=1 覆盖缓存路径；GM_DB=sqlite:///test_promo_content.sqlite 独立库用完清理；
BigInteger 垫片同 test_review_ops_ext.py）"""

import os
import sys
from datetime import timedelta
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_promo_content.sqlite").replace("\\", "/")


def _remove_db_files():
    for _suffix in ("", "-wal", "-shm"):
        _p = _DB + _suffix
        if os.path.exists(_p):
            try:
                os.remove(_p)
            except PermissionError:
                # Windows 下连接可能未完全释放：残留库不影响结果断言，下次运行时再清
                pass


_remove_db_files()
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
os.environ["GM_CACHE"] = "1"  # 开启 TTL 缓存，覆盖标签云缓存/失效路径
sys.path.insert(0, _ROOT)

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):
    return "INTEGER"


from app.core.db import SessionLocal, engine, init_db, utcnow  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.domains.content import service as content_service  # noqa: E402
from app.domains.content.schemas import ArticleCreateIn  # noqa: E402
from app.domains.promo import service as promo_service  # noqa: E402
from app.domains.promo.schemas import (  # noqa: E402
    DiscountCreateIn, GiftcardAdminCreateIn,
)
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    GiftCard, Order, OrderItem, PointsLedger, Product, Review, UgcSubmission, User,
)

PASSED = 0
FAILED = []

ADDR = {"full_name": "T", "line1": "1 Main St", "city": "SF", "state": "CA",
        "zip": "94110", "country": "US"}


def check(name, cond, info=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok {PASSED:02d} - {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {PASSED + 1:02d} - {name}  {info}")


def main() -> int:
    try:
        init_db()
        db = SessionLocal()
        admin = User(email="pcx-admin@glow.test", password_hash=hash_password("x"),
                     name="PcxAdmin", role=2)
        cust = User(email="pcx-cust@glow.test", password_hash=hash_password("x"),
                    name="Pcx Cust", role=1, status=1, points=0)
        db.add_all([admin, cust])
        db.flush()
        prod = Product(slug="pcx-nails", title="PCX Nails", category_id=1, status=1,
                       price_min=1000, price_max=1000, hero_image="/img/pcx.jpg",
                       published_at=utcnow())
        db.add(prod)
        db.commit()
        H = {"Authorization": f"Bearer {create_token(admin.id, admin.role)}"}
        CUST_H = {"Authorization": f"Bearer {create_token(cust.id, cust.role)}"}

        with TestClient(app) as client:

            # ===== P0-1 UGC 奖励：原子发分 + re-approve 不重复薅分 =====
            print("== P0-1 UGC re-approve 不重复发分 ==")
            r = client.post("/api/content/ugc", headers=CUST_H, json={
                "image_url": "https://cdn/pcx.jpg", "caption": "my set",
                "related_product_id": prod.id})
            ugc_id = r.json()["id"]
            r = client.get("/api/points", headers=CUST_H)
            base_balance = r.json()["balance"]
            r = client.post(f"/api/admin/ops/ugc/{ugc_id}/approve", headers=H)
            check("首次过审发 100 分",
                  r.status_code == 200 and r.json()["points_rewarded"] == 100, r.text[:120])
            db.expire_all()
            check("余额 +100 且 ledger 恰 1 条 ugc 奖励",
                  db.get(User, cust.id).points == base_balance + 100
                  and db.query(PointsLedger).filter(
                      PointsLedger.user_id == cust.id,
                      PointsLedger.ref_type == "ugc").count() == 1)
            r = client.post(f"/api/admin/ops/ugc/{ugc_id}/approve", headers=H)
            check("已过审重复 approve → 409", r.status_code == 409, r.status_code)
            # 模拟 unapprove/历史数据回退：DB 直改 status=0 后再 approve，
            # CAS 会放行（状态确为 0），但 ledger 查重必须挡住第二次发分
            u = db.get(UgcSubmission, ugc_id)
            u.status = 0
            db.commit()
            r = client.post(f"/api/admin/ops/ugc/{ugc_id}/approve", headers=H)
            db.expire_all()
            check("re-approve（状态回退后）过审成功但不重复发分",
                  r.status_code == 200 and db.get(User, cust.id).points == base_balance + 100
                  and db.query(PointsLedger).filter(
                      PointsLedger.user_id == cust.id,
                      PointsLedger.ref_type == "ugc").count() == 1,
                  (r.status_code, db.get(User, cust.id).points))
            r = client.post("/api/content/ugc", json={
                "image_url": "https://cdn/anon.jpg"})
            anon_id = r.json()["id"]
            r = client.post(f"/api/admin/ops/ugc/{anon_id}/reject", headers=H)
            check("匿名 UGC 拒绝 200", r.status_code == 200, r.status_code)
            r = client.post(f"/api/admin/ops/ugc/{anon_id}/reject", headers=H)
            check("重复 reject → 409", r.status_code == 409, r.status_code)
            r = client.post(f"/api/admin/ops/ugc/{anon_id}/approve", headers=H)
            check("已拒绝再 approve → 409（状态机不穿隧）", r.status_code == 409, r.status_code)

            # ===== P0-2 礼品卡 freeze/unfreeze 状态机 =====
            print("== P0-2 freeze 穿隧 ==")
            r = client.post("/api/admin/promo/giftcards", headers=H,
                            json={"initial_cents": 5000})
            check("手工发卡 status=1", r.status_code == 200 and r.json()["status"] == 1,
                  r.text[:120])
            gc_ok = db.get(GiftCard, r.json()["id"])
            r = client.put(f"/api/admin/promo/giftcards/{gc_ok.id}/freeze", headers=H)
            check("有效卡 freeze → 200 status=2",
                  r.status_code == 200 and r.json()["status"] == 2, r.text[:120])
            r = client.put(f"/api/admin/promo/giftcards/{gc_ok.id}/freeze", headers=H)
            check("已冻结再 freeze → 幂等 200",
                  r.status_code == 200 and r.json()["status"] == 2, r.status_code)
            r = client.put(f"/api/admin/promo/giftcards/{gc_ok.id}/unfreeze", headers=H)
            check("手工卡（无关联订单）unfreeze → 200 status=1",
                  r.status_code == 200 and r.json()["status"] == 1, r.text[:120])
            # 未支付购卡订单的待激活卡：freeze 不得放行；存量被误冻后 unfreeze 不得复活
            unpaid_order = Order(order_no="NSPCXUNPAID1", email="pcx@glow.test",
                                 user_id=cust.id, status=0, subtotal=2500,
                                 grand_total=2500, shipping_address=ADDR,
                                 placed_at=utcnow())
            db.add(unpaid_order)
            db.flush()
            gc_pending = GiftCard(code="GC-PCX-PEND-1", initial_amount=2500,
                                  balance=2500, status=0, purchaser_email="pcx@glow.test",
                                  purchaser_order_id=unpaid_order.id)
            db.add(gc_pending)
            db.commit()
            r = client.put(f"/api/admin/promo/giftcards/{gc_pending.id}/freeze", headers=H)
            check("待激活(0) freeze → 409 invalid_status",
                  r.status_code == 409 and r.json()["detail"] == "invalid_status",
                  (r.status_code, r.json().get("detail")))
            db.expire_all()
            gc_pending = db.get(GiftCard, gc_pending.id)
            gc_pending.status = 2  # 模拟旧版无守卫时被冻结的待激活卡（存量脏数据）
            db.commit()
            r = client.put(f"/api/admin/promo/giftcards/{gc_pending.id}/unfreeze", headers=H)
            check("未支付购卡订单的冻结卡 unfreeze → 409 unpaid_giftcard",
                  r.status_code == 409 and r.json()["detail"] == "unpaid_giftcard",
                  (r.status_code, r.json().get("detail")))
            db.expire_all()
            db.get(Order, unpaid_order.id).status = 1  # 订单支付完成
            db.commit()
            r = client.put(f"/api/admin/promo/giftcards/{gc_pending.id}/unfreeze", headers=H)
            check("订单已支付后 unfreeze → 200 status=1（合法解冻）",
                  r.status_code == 200 and r.json()["status"] == 1, r.text[:120])
            gc_used = GiftCard(code="GC-PCX-USED-1", initial_amount=1000, balance=0,
                               status=3, purchaser_email="pcx@glow.test")
            gc_void = GiftCard(code="GC-PCX-VOID-1", initial_amount=1000, balance=0,
                               status=4, purchaser_email="pcx@glow.test")
            db.add_all([gc_used, gc_void])
            db.commit()
            check("用尽(3) freeze/unfreeze → 409",
                  client.put(f"/api/admin/promo/giftcards/{gc_used.id}/freeze",
                             headers=H).status_code == 409
                  and client.put(f"/api/admin/promo/giftcards/{gc_used.id}/unfreeze",
                                 headers=H).status_code == 409)
            check("作废(4) freeze/unfreeze → 409",
                  client.put(f"/api/admin/promo/giftcards/{gc_void.id}/freeze",
                             headers=H).status_code == 409
                  and client.put(f"/api/admin/promo/giftcards/{gc_void.id}/unfreeze",
                                 headers=H).status_code == 409)

            # ===== P1-3 max_discount 非负 =====
            print("== P1-3 max_discount 非负 ==")
            r = client.post("/api/admin/ops/discounts", headers=H, json={
                "code": "PCXNEG", "type": 1, "value": 10, "max_discount": -100,
                "starts_at": "2026-01-01T00:00:00Z"})
            check("create max_discount 负值 → 422", r.status_code == 422, r.status_code)
            r = client.post("/api/admin/ops/discounts", headers=H, json={
                "code": "PCXOK", "type": 1, "value": 10, "max_discount": 2000,
                "starts_at": "2026-01-01T00:00:00Z"})
            check("create max_discount 合法值 → 200",
                  r.status_code == 200 and r.json()["max_discount"] == 2000, r.text[:120])
            pcx_dc = r.json()["id"]
            r = client.put(f"/api/admin/ops/discounts/{pcx_dc}", headers=H,
                           json={"max_discount": -1})
            check("update max_discount 负值 → 422", r.status_code == 422, r.status_code)

            # ===== P1-4 check_giftcard 过期 =====
            print("== P1-4 giftcard 过期 ==")
            db.add(GiftCard(code="GC-PCX-EXP-1", initial_amount=1000, balance=1000,
                            status=1, purchaser_email="pcx@glow.test",
                            expires_at=utcnow() - timedelta(days=1)))
            db.commit()
            r = client.post("/api/promo/giftcard", json={"code": "GC-PCX-EXP-1"})
            check("过期卡查询 → 409 gift_card_expired",
                  r.status_code == 409 and r.json()["detail"] == "gift_card_expired",
                  (r.status_code, r.json().get("detail")))
            r = client.post("/api/promo/giftcard", json={"code": gc_ok.code})
            check("未过期有效卡查询 → 200 带余额",
                  r.status_code == 200 and r.json()["balance_cents"] == 5000, r.text[:120])

            # ===== P1-5 弹窗窗口交叉 + scene 校验 =====
            print("== P1-5 popup 窗口/scene ==")
            r = client.post("/api/admin/ops/popups", headers=H, json={
                "scene": "welcome", "title": "T",
                "start_at": "2026-09-02T00:00:00Z", "end_at": "2026-09-01T00:00:00Z"})
            check("create end<start → 422 ends_before_starts",
                  r.status_code == 422 and r.json()["detail"] == "ends_before_starts",
                  (r.status_code, r.json().get("detail")))
            r = client.post("/api/admin/ops/popups", headers=H,
                            json={"scene": "welcome", "title": "T"})
            pcx_pop = r.json()["id"]
            check("create 无窗口（两端皆空）→ 200", r.status_code == 200, r.status_code)
            r = client.post("/api/admin/ops/popups", headers=H, json={
                "scene": "welcome", "title": "T2",
                "start_at": "2026-09-02T00:00:00Z", "end_at": "2026-09-02T00:00:00Z"})
            check("create end==start（允许相等）→ 200", r.status_code == 200, r.status_code)
            r = client.put(f"/api/admin/ops/popups/{pcx_pop}", headers=H, json={
                "start_at": "2026-09-02T00:00:00Z", "end_at": "2026-09-01T00:00:00Z"})
            check("update end<start → 422 ends_before_starts",
                  r.status_code == 422, r.status_code)
            r = client.put(f"/api/admin/ops/popups/{pcx_pop}", headers=H, json={
                "start_at": "2026-09-01T00:00:00Z", "end_at": "2026-09-03T00:00:00Z"})
            check("update 合法窗口 → 200", r.status_code == 200, r.status_code)
            check("scene 空串/超长(31)/纯空格 → 422",
                  client.post("/api/admin/ops/popups", headers=H,
                              json={"scene": "", "title": "T"}).status_code == 422
                  and client.post("/api/admin/ops/popups", headers=H,
                                  json={"scene": "s" * 31, "title": "T"}).status_code == 422
                  and client.post("/api/admin/ops/popups", headers=H,
                                  json={"scene": "   ", "title": "T"}).status_code == 422)
            r = client.post("/api/admin/ops/popups", headers=H,
                            json={"scene": "pcx_scene", "title": "Custom"})
            check("scene 存量自定义值宽松放行 → 200", r.status_code == 200, r.status_code)

            # ===== P1-6 先查后插撞唯一索引 → 409 而非 500 =====
            print("== P1-6 撞唯一索引 409 ==")
            body = GiftcardAdminCreateIn(initial_cents=1000, code="GC-PCX-CLASH")
            promo_service.create_giftcard(db, admin, body)
            with patch.object(promo_service.repo, "giftcard_id_by_code", return_value=None):
                try:
                    promo_service.create_giftcard(db, admin, body)
                    clash = False
                except HTTPException as e:
                    clash = e.status_code == 409 and e.detail == "code_exists"
            check("并发同卡号撞唯一索引 → 409 code_exists", clash)
            dbody = DiscountCreateIn(code="PCXCLASH", type=3, value=0,
                                     starts_at=utcnow())
            promo_service.create_discount(db, admin, dbody)
            with patch.object(promo_service.repo, "discount_id_by_code", return_value=None):
                try:
                    promo_service.create_discount(db, admin, dbody)
                    clash = False
                except HTTPException as e:
                    clash = e.status_code == 409 and e.detail == "code_exists"
            check("并发同折扣码撞唯一索引 → 409 code_exists", clash)
            abody = ArticleCreateIn(slug="pcx-clash", title="Clash", author="T",
                                    content_md="x", status=0)
            content_service.create_article(db, admin, abody)
            with patch.object(content_service.repo, "article_id_by_slug", return_value=None):
                try:
                    content_service.create_article(db, admin, abody)
                    clash = False
                except HTTPException as e:
                    clash = e.status_code == 409 and e.detail == "slug_exists"
            check("并发同文章 slug 撞唯一索引 → 409 slug_exists", clash)

            # ===== P1-9 review content 长度上限 =====
            print("== P1-9 review content 长度 ==")
            rv_order = Order(order_no="NSPCXREVIEW1", email="pcx@glow.test",
                             user_id=cust.id, status=3, subtotal=1000, grand_total=1000,
                             shipping_address=ADDR, placed_at=utcnow())
            db.add(rv_order)
            db.flush()
            rv_item = OrderItem(order_id=rv_order.id, variant_id=0,
                                product_slug="pcx-nails", title_snapshot="PCX",
                                image="", qty=1, unit_price=1000, subtotal=1000)
            db.add(rv_item)
            db.commit()
            r = client.post("/api/content/reviews", headers=CUST_H, json={
                "order_no": "NSPCXREVIEW1", "order_item_id": rv_item.id, "rating": 5,
                "content": "x" * 2001})
            check("review content >2000 → 422", r.status_code == 422, r.status_code)
            r = client.post("/api/content/reviews", headers=CUST_H, json={
                "order_no": "NSPCXREVIEW1", "order_item_id": rv_item.id, "rating": 5,
                "content": "x" * 2000})
            check("review content 恰 2000 → 200", r.status_code == 200, r.text[:120])

            # ===== P2-10 评分重算 SQL 聚合 =====
            print("== P2-10 rating 重算 ==")
            rv2_order = Order(order_no="NSPCXREVIEW2", email="pcx@glow.test",
                              user_id=cust.id, status=3, subtotal=1000, grand_total=1000,
                              shipping_address=ADDR, placed_at=utcnow())
            rv3_order = Order(order_no="NSPCXREVIEW3", email="pcx@glow.test",
                              user_id=cust.id, status=3, subtotal=1000, grand_total=1000,
                              shipping_address=ADDR, placed_at=utcnow())
            db.add_all([rv2_order, rv3_order])
            db.flush()
            it2 = OrderItem(order_id=rv2_order.id, variant_id=0, product_slug="pcx-nails",
                            title_snapshot="PCX", image="", qty=1, unit_price=1000,
                            subtotal=1000, reviewed=1)
            it3 = OrderItem(order_id=rv3_order.id, variant_id=0, product_slug="pcx-nails",
                            title_snapshot="PCX", image="", qty=1, unit_price=1000,
                            subtotal=1000, reviewed=1)
            db.add_all([it2, it3])
            db.flush()  # 先 flush 拿 id，再构造引用它的 Review
            db.add_all([
                Review(product_id=prod.id, user_id=cust.id, order_item_id=it2.id,
                       rating=4, status=1),
                Review(product_id=prod.id, user_id=cust.id, order_item_id=it3.id,
                       rating=5, status=0),
            ])
            db.commit()
            pend_review = db.query(Review).filter(Review.order_item_id == it3.id).one()
            content_service.approve_review(db, admin, pend_review.id)
            db.expire_all()
            p = db.get(Product, prod.id)
            # 过审评分 4+5：avg=round(9*100/2)=450，口径与旧内存求均一致
            check("SQL 重算 rating_avg=450 / count=2",
                  p.rating_avg == 450 and p.rating_count == 2,
                  (p.rating_avg, p.rating_count))
            r = client.post(f"/api/admin/ops/reviews/{pend_review.id}/approve", headers=H)
            check("已过审重复 approve → 409（CAS）", r.status_code == 409, r.status_code)

            # ===== P2-11 标签云 TTL 缓存 + 写路径失效 =====
            print("== P2-11 标签云缓存 ==")
            t1 = content_service.list_articles(db, 1, 10, None)["tags"]
            t2 = content_service.list_articles(db, 1, 10, None)["tags"]
            check("GM_CACHE=1 标签云命中缓存（同引用）", t1 is t2)
            content_service.create_article(db, admin, ArticleCreateIn(
                slug="pcx-cache", title="Cache", author="T", content_md="x",
                tags=["pcxtag"], status=1))
            t3 = content_service.list_articles(db, 1, 10, None)["tags"]
            check("文章写路径失效标签云缓存（新 tag 可见）",
                  any(x["name"] == "pcxtag" for x in t3) and t3 is not t1,
                  [x["name"] for x in t3][:5])

        db.close()

        print(f"\nALL PASS: {PASSED}/{PASSED + len(FAILED)}")
        if FAILED:
            print("FAILED:", FAILED)
            return 1
        return 0
    finally:
        # 用完清理：先释放连接池再删 sqlite 文件（含 WAL/SHM）
        engine.dispose()
        _remove_db_files()


def test_promo_content_ext():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
