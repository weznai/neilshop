"""工单/运营域并发 CAS 回归自测 —— P0-1 状态机流转 / P0-2 认领 / 关单 /
P0-3 GDPR 数据请求三方竞态 / P1-8 对账核销（service 层 ThreadPoolExecutor 直调，
独立 session 模拟并发请求）+ P1 顺序回归（单号熵/入参上限/close_reason 白名单/
priority 激活/P0-4 bulk 409 容错/P1-9 GMV 口径/P1-10 未关工单口径）。
（GM_DB=sqlite 独立库；BigInteger 垫片同 test_admin_ext.py；直跑与 pytest 双兼容）"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_tickets_cas_ext.sqlite").replace("\\", "/")
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

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, utcnow  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AdminLog, Category, DataRequest, Order, Product, ReconciliationDaily,
    Review, Ticket, User,
)
from app.domains.support import service as support_svc  # noqa: E402
from app.domains.support.schemas import (  # noqa: E402
    AssignIn, CloseIn, ReplyIn, TicketStatusIn,
)
from app.domains.ops import service as ops_svc  # noqa: E402
from app.domains.ops.schemas import ReviewBulkIn  # noqa: E402
from app.domains.content import service as content_service  # noqa: E402

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


def in_session(fn):
    """线程体：独立 session 直调 service 层（模拟并发请求落到不同会话）；
    结果归一为 ("ok",) / ("http", status, detail) / ("error", repr)"""
    s = SessionLocal()
    try:
        fn(s)
        return ("ok",)
    except HTTPException as exc:
        return ("http", exc.status_code, exc.detail)
    except Exception as exc:  # 并发 sqlite 锁等异常显式暴露，不算通过
        return ("error", repr(exc))
    finally:
        s.close()


def run_concurrent(fns):
    """fns: list[callable(session)]，逐个映射到独立线程并发执行"""
    with ThreadPoolExecutor(max_workers=len(fns)) as ex:
        return list(ex.map(in_session, fns))


def main() -> int:
    with TestClient(app) as client:
        s = SessionLocal()
        ops_admin = User(email="casops@glow.test", password_hash=hash_password("x"),
                         name="CasOps", role=2)
        cs_admin = User(email="cascs@glow.test", password_hash=hash_password("x"),
                        name="CasCs", role=1)
        member = User(email="casm@glow.test", password_hash=hash_password("x"),
                      name="CasM", points=0)
        s.add_all([ops_admin, cs_admin, member])
        s.commit()
        # 并发线程内只用裸 id 重建对象：避免跨线程访问主会话 ORM 实例（过期刷新竞态）
        A_OPS, A_CS = ops_admin.id, cs_admin.id
        H_OPS = {"Authorization": f"Bearer {create_token(ops_admin.id, ops_admin.role)}"}

        # ===== 1. 单号熵 + 入参上限（P1-5 / P1-6）=====
        r = client.post("/api/support/tickets", json={
            "email": "guest@glow.test", "category": 1,
            "subject": "cas ext", "content": "hello"})
        no = r.json().get("ticket_no", "")
        check("ticket_no = TK+yymmdd+6位HEX（长 14，撞库概率 24bit）",
              r.status_code == 200 and no.startswith("TK") and len(no) == 14, no)
        base = {"email": "guest@glow.test", "category": 1,
                "subject": "s", "content": "c"}
        check("subject>200 → 422", client.post("/api/support/tickets", json={
            **base, "subject": "x" * 201}).status_code == 422)
        check("content>20000 → 422", client.post("/api/support/tickets", json={
            **base, "content": "x" * 20001}).status_code == 422)
        check("order_no>20 → 422", client.post("/api/support/tickets", json={
            **base, "order_no": "N" * 21}).status_code == 422)
        check("email>191 → 422", client.post("/api/support/tickets", json={
            **base, "email": "a" * 182 + "@glow.test"}).status_code == 422)

        # ===== 2. priority 激活（reply/close 可选字段，P1-11）=====
        tk_p = Ticket(ticket_no="CASTKPRIO001", email="p@glow.test", category=1,
                      subject="prio", status=0)
        s.add(tk_p)
        s.commit()
        r = client.post("/api/admin/ops/tickets/CASTKPRIO001/reply", headers=H_OPS,
                        json={"content": "hi", "priority": 0})
        s.expire_all()
        check("reply 带 priority=0 → 顺带更新（响应与落库一致）",
              r.status_code == 200 and r.json()["priority"] == 0
              and s.query(Ticket).filter_by(ticket_no="CASTKPRIO001").first().priority == 0,
              r.text[:120])
        check("priority=3 越界 → 422", client.post(
            "/api/admin/ops/tickets/CASTKPRIO001/reply", headers=H_OPS,
            json={"content": "hi", "priority": 3}).status_code == 422)
        tk_p2 = Ticket(ticket_no="CASTKPRIO002", email="p@glow.test", category=1,
                       subject="prio2", status=1)
        s.add(tk_p2)
        s.commit()
        r = client.post("/api/admin/ops/tickets/CASTKPRIO002/close", headers=H_OPS,
                        json={"close_reason": 1, "priority": 0})
        check("close 带 priority=0 → 顺带更新",
              r.status_code == 200 and r.json()["priority"] == 0, r.text[:120])

        # ===== 3. close_reason 白名单（P1-7）=====
        for i, (tk_no, reason) in enumerate([
                ("CASTKRS000001", 5), ("CASTKRS000002", "重复提交"), ("CASTKRS000003", 2)]):
            s.add(Ticket(ticket_no=tk_no, email="r@glow.test", category=1,
                         subject=f"cr{i}", status=1))
        s.commit()
        for tk_no, reason, want in [("CASTKRS000001", 5, 9),
                                    ("CASTKRS000002", "重复提交", 9),
                                    ("CASTKRS000003", 2, 2)]:
            r = client.post(f"/api/admin/ops/tickets/{tk_no}/close", headers=H_OPS,
                            json={"close_reason": reason})
            s.expire_all()
            got = s.query(Ticket).filter_by(ticket_no=tk_no).first().close_reason
            check(f"close_reason={reason!r} → 落库 {want}", r.status_code == 200
                  and got == want, (r.status_code, got))

        # ===== 4. 非法流转仍 409（回归保护）=====
        tk_inv = Ticket(ticket_no="CASTKINV0001", email="i@glow.test", category=1,
                        subject="inv", status=3)
        s.add(tk_inv)
        s.commit()
        r = client.put("/api/admin/support/tickets/CASTKINV0001/status", headers=H_OPS,
                       json={"status": 2})
        check("非法流转（3→2）→ 409 invalid_status_transition",
              r.status_code == 409 and r.json()["detail"] == "invalid_status_transition",
              (r.status_code, r.json().get("detail")))

        # ===== 5. P0-1 并发状态流转 CAS =====
        tk_s = Ticket(ticket_no="CASTKST00001", email="s@glow.test", category=1,
                      subject="st", status=1)
        s.add(tk_s)
        s.commit()
        results = run_concurrent([
            lambda sess: support_svc.admin_set_status(
                sess, sess.get(User, A_OPS), "CASTKST00001",
                TicketStatusIn(status=2))
        ] * 8)
        ok_n = sum(1 for x in results if x[0] == "ok")
        # 输家两种 409 均合法：读到陈旧 prev=1 → CAS rowcount=0（status_conflict）；
        # 读到赢家已提交的新状态 → (2,2) 非法边（invalid_status_transition）
        rejected_n = sum(
            1 for x in results
            if x[:2] == ("http", 409)
            and x[2] in ("status_conflict", "invalid_status_transition"))
        s.expire_all()
        t_db = s.query(Ticket).filter_by(ticket_no="CASTKST00001").first()
        n_status_logs = (s.query(AdminLog).filter_by(
            entity="ticket", entity_id=tk_s.id, action="status").count())
        check("8 并发 1→2：恰 1 成功，其余全 409（CAS 冲突或非法边，无重复生效）",
              ok_n == 1 and rejected_n == 7, results)
        check("并发流转终态 status=2 且审计仅 1 条（无双击重复审计）",
              t_db.status == 2 and n_status_logs == 1,
              (t_db.status, n_status_logs))

        tk_d = Ticket(ticket_no="CASTKDIV0001", email="d@glow.test", category=1,
                      subject="div", status=1)
        s.add(tk_d)
        s.commit()
        results = run_concurrent([
            lambda sess: support_svc.admin_set_status(
                sess, sess.get(User, A_OPS), "CASTKDIV0001",
                TicketStatusIn(status=2)),
            lambda sess: support_svc.admin_set_status(
                sess, sess.get(User, A_OPS), "CASTKDIV0001",
                TicketStatusIn(status=3)),
        ])
        s.expire_all()
        t_db = s.query(Ticket).filter_by(ticket_no="CASTKDIV0001").first()
        winners = [x for x in results if x[0] == "ok"]
        check("并发异边（1→2 vs 1→3）：恰 1 成功，终态 ∈ {2,3}",
              len(winners) == 1 and t_db.status in (2, 3)
              and sum(1 for x in results if x[:2] == ("http", 409)) == 1,
              (results, t_db.status))

        # ===== 6. 并发关单 CAS（护住 closed_at/close_reason 审计）=====
        tk_c = Ticket(ticket_no="CASTKCL00001", email="c@glow.test", category=1,
                      subject="cl", status=1)
        s.add(tk_c)
        s.commit()
        results = run_concurrent([
            lambda sess: support_svc.admin_close(
                sess, sess.get(User, A_OPS), "CASTKCL00001",
                CloseIn(close_reason=1))
        ] * 4)
        ok_n = sum(1 for x in results if x[0] == "ok")
        close_409 = sum(1 for x in results if x[:2] == ("http", 409)
                        and x[2] == "ticket_already_closed")
        s.expire_all()
        n_close_logs = (s.query(AdminLog).filter_by(
            entity="ticket", entity_id=tk_c.id, action="close").count())
        check("4 并发关单：恰 1 成功 + 3 个 409 ticket_already_closed",
              ok_n == 1 and close_409 == 3, results)
        check("关单审计仅 1 条（closed_at/close_reason 不被覆盖）", n_close_logs == 1,
              n_close_logs)

        # ===== 7. P0-2 并发认领 + 显式改派审计 =====
        tk_a = Ticket(ticket_no="CASTKAS00001", email="a@glow.test", category=1,
                      subject="as", status=0)
        s.add(tk_a)
        s.commit()

        def claim_as(admin_id):
            return lambda sess: support_svc.admin_assign(
                sess, sess.get(User, admin_id), "CASTKAS00001",
                AssignIn(admin_id=admin_id))

        results = run_concurrent([claim_as(A_CS), claim_as(A_OPS)])
        s.expire_all()
        t_db = s.query(Ticket).filter_by(ticket_no="CASTKAS00001").first()
        check("两管理员并发「指派给我」：1 成功 + 1 个 409 already_assigned",
              sum(1 for x in results if x[0] == "ok") == 1
              and sum(1 for x in results if x[:2] == ("http", 409)
                      and x[2] == "already_assigned") == 1, results)
        winner_id = t_db.assignee_admin_id
        loser_id = A_OPS if winner_id == A_CS else A_CS
        check("认领终态唯一（胜者落库）", winner_id in (A_CS, A_OPS), winner_id)
        r2 = in_session(claim_as(loser_id))
        check("败者再「指派给我」→ 409 already_assigned（已被他人认领）",
              r2[:2] == ("http", 409) and r2[2] == "already_assigned", r2)
        # 显式改派（管理员指定他人）保留覆盖，审计记录原指派人；
        # 操作者须 ≠ 目标（否则命中「指派给我」409 分支），取胜者操作改派败者
        r3 = in_session(lambda sess: support_svc.admin_assign(
            sess, sess.get(User, winner_id), "CASTKAS00001",
            AssignIn(admin_id=loser_id)))
        s.expire_all()
        t_db = s.query(Ticket).filter_by(ticket_no="CASTKAS00001").first()
        last_log = (s.query(AdminLog).filter_by(
            entity="ticket", entity_id=tk_a.id, action="assign")
            .order_by(AdminLog.id.desc()).first())
        check("显式改派覆盖成功且审计 diff 记录原指派人",
              r3[0] == "ok" and t_db.assignee_admin_id == loser_id
              and last_log.diff_json.get("from") == winner_id
              and last_log.diff_json.get("admin_id") == loser_id,
              (r3, last_log.diff_json if last_log else None))

        # ===== 8. P0-3 GDPR 数据请求三方竞态（execute vs reject）=====
        req = DataRequest(user_id=member.id, type=1, status=0, created_at=utcnow())
        s.add(req)
        s.commit()
        req_id = req.id
        results = run_concurrent([
            lambda sess: ops_svc.execute_data_request(
                sess, sess.get(User, A_OPS), req_id),
            lambda sess: ops_svc.reject_data_request(
                sess, sess.get(User, A_OPS), req_id),
        ])
        s.expire_all()
        req_db = s.get(DataRequest, req.id)
        n_dr_logs = (s.query(AdminLog).filter_by(
            entity="data_request", entity_id=req.id).count())
        check("并发 execute vs reject：1 成功 + 1 个 409 request not pending",
              sum(1 for x in results if x[0] == "ok") == 1
              and sum(1 for x in results if x[:2] == ("http", 409)
                      and x[2] == "request not pending") == 1, results)
        check("数据请求终态唯一（1 或 2）且审计仅 1 条",
              req_db.status in (1, 2) and n_dr_logs == 1,
              (req_db.status, n_dr_logs))

        # ===== 9. P1-8 并发对账核销 =====
        rec = ReconciliationDaily(reconcile_date=date(2026, 8, 25),
                                  payments_gross=2000, orders_paid_total=1900,
                                  diff_payment=100, status=1, checked_at=utcnow())
        s.add(rec)
        s.commit()
        rec_id = rec.id
        results = run_concurrent([
            lambda sess: ops_svc.resolve_reconciliation(
                sess, sess.get(User, A_OPS), rec_id)
        ] * 2)
        s.expire_all()
        rec_db = s.get(ReconciliationDaily, rec.id)
        n_rec_logs = (s.query(AdminLog).filter_by(
            entity="reconcile", entity_id=rec.id, action="resolve").count())
        check("并发核销：1 成功 + 1 个 409 already resolved，审计仅 1 条",
              sum(1 for x in results if x[0] == "ok") == 1
              and sum(1 for x in results if x[:2] == ("http", 409)
                      and x[2] == "already resolved") == 1
              and rec_db.status == 2 and n_rec_logs == 1,
              (results, rec_db.status, n_rec_logs))

        # ===== 10. P0-4 bulk 逐条容错（409 并发冲突 → skipped 继续）=====
        cat = Category(slug="cas-cat", name="CasCat")
        s.add(cat)
        s.flush()
        prod = Product(slug="cas-prod", title="Cas Prod", category_id=cat.id,
                       status=1, hero_image="https://img/c.jpg",
                       price_min=1000, price_max=1000)
        s.add(prod)
        s.flush()
        r1 = Review(product_id=prod.id, user_id=member.id, order_item_id=9001,
                    rating=5, content="bulk1", status=0)
        r2 = Review(product_id=prod.id, user_id=member.id, order_item_id=9002,
                    rating=4, content="bulk2", status=0)
        s.add_all([r1, r2])
        s.commit()
        # 定向注入：r1 在批查询后、单条处理时撞 409（模拟被并发处理）
        _orig_approve = content_service.approve_review

        def _approve_conflict_first(db, admin, review_id):
            if review_id == r1.id:
                raise HTTPException(status_code=409, detail="review not pending")
            return _orig_approve(db, admin, review_id)

        content_service.approve_review = _approve_conflict_first
        try:
            out = ops_svc.bulk_reviews(s, ops_admin, ReviewBulkIn(
                ids=[r1.id, r2.id], action="approve"))
        finally:
            content_service.approve_review = _orig_approve
        s.expire_all()
        r1_db, r2_db = s.get(Review, r1.id), s.get(Review, r2.id)
        check("bulk 409 容错：{updated:1, skipped:1}，冲突条保持待审、其余照常处理",
              out == {"updated": 1, "skipped": 1}
              and r1_db.status == 0 and r2_db.status == 1,
              (out, r1_db.status, r2_db.status))

        # ===== 11. P1-9 GMV 口径 / P1-10 未关工单口径 =====
        s.add_all([
            Order(order_no="CASGMV000001", email="g@glow.test",
                  status=1, subtotal=1000, grand_total=1000,
                  shipping_address=ADDR, placed_at=utcnow(), paid_at=utcnow()),
            Order(order_no="CASGMV000008", email="g@glow.test", status=8,
                  subtotal=500, grand_total=500, shipping_address=ADDR,
                  placed_at=utcnow(), paid_at=utcnow()),
            Order(order_no="CASGMV000009", email="g@glow.test", status=9,
                  subtotal=700, grand_total=700, shipping_address=ADDR,
                  placed_at=utcnow(), paid_at=utcnow()),
        ])
        s.commit()
        d = client.get("/api/admin/ops/dashboard", headers=H_OPS).json()
        s.expire_all()
        expect_open = (s.query(Ticket)
                       .filter(Ticket.status.in_([0, 1, 2, 3])).count())
        n_resolved = (s.query(Ticket).filter(Ticket.status == 3).count())
        check("GMV 净口径：排除已取消(8)/已退款(9)，today gmv=1000 / paid=1",
              d["today"]["gmv_cents"] == 1000 and d["today"]["paid_count"] == 1,
              d.get("today"))
        check("未关工单口径含 3（已解决待关）：dashboard == DB in_(0,1,2,3)",
              d["open_tickets"] == expect_open and n_resolved >= 1,
              (d.get("open_tickets"), expect_open, n_resolved))

        s.close()

    print(f"\n{PASSED} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed:", FAILED)
        return 1
    return 0


def test_tickets_cas_ext():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
