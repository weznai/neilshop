"""admin ops 扩展自测 II —— orders 组合状态过滤 / 管理账号列表 / 积分人工调整 /
分类管理补全（更新+删除保护）/ 工单 4→1 重开与客户回复回流 / 集合编辑 banner 校验。
（GM_DB=sqlite:///test_admin_ops_ext.sqlite 独立库；BigInteger 垫片同 test_admin_ext.py；
直跑与 pytest 双兼容：main() 承载全部断言，尾部 __main__ 约定 + pytest 包装函数）"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_admin_ops_ext.sqlite").replace("\\", "/")
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
    AdminLog, Category, Collection, Order, PointsLedger, Product, Ticket, User,
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


def make_order(s, no, *, email="ext2@glow.test", status=1, subtotal=1000):
    o = Order(order_no=no, email=email, status=status, subtotal=subtotal,
              grand_total=subtotal, shipping_address=ADDR, placed_at=utcnow(),
              paid_at=utcnow(), points_earned=0, giftcard_discount=0)
    s.add(o)
    s.flush()
    return o


def main() -> int:
    with TestClient(app) as client:
        s = SessionLocal()
        admin = User(email="ops2@glow.test", password_hash=hash_password("x"),
                     name="Ops2", role=2)
        s.add(admin)
        s.commit()
        H_OPS = {"Authorization": f"Bearer {create_token(admin.id, admin.role)}"}

        # ===== 1. admin orders 组合状态过滤（status=1,2 多值 / 单值 / 非法 422）=====
        for i in range(3):
            make_order(s, f"OPS26ORD1{i:d}", status=1)
        for i in range(2):
            make_order(s, f"OPS26ORD2{i:d}", status=2)
        make_order(s, "OPS26ORD5X", status=5)
        s.commit()
        r = client.get("/api/admin/trade/orders", headers=H_OPS,
                       params={"status": "1,2", "per_page": 50})
        d = r.json()
        check("orders status=1,2 → 5 条且仅含 1/2 两类",
              r.status_code == 200 and d["total"] == 5
              and {o["status"] for o in d["items"]} == {1, 2}, d.get("total"))
        r = client.get("/api/admin/trade/orders", headers=H_OPS,
                       params={"status": "1"})
        d = r.json()
        check("orders 单值 status=1 行为不变（3 条）",
              r.status_code == 200 and d["total"] == 3
              and all(o["status"] == 1 for o in d["items"]), d.get("total"))
        r = client.get("/api/admin/trade/orders", headers=H_OPS,
                       params={"status": "5"})
        check("orders 单值 status=5（1 条）", r.json()["total"] == 1, r.json().get("total"))
        r = client.get("/api/admin/trade/orders", headers=H_OPS)
        check("orders 不带 status → 全量 6 条", r.json()["total"] == 6, r.json().get("total"))
        check("orders 端点需要鉴权",
              client.get("/api/admin/trade/orders").status_code == 401)
        r = client.get("/api/admin/trade/orders", headers=H_OPS,
                       params={"status": "1,abc"})
        check("orders 组合含非法段 → 422 invalid status",
              r.status_code == 422 and r.json()["detail"] == "invalid status",
              (r.status_code, r.json().get("detail")))
        check("orders 单值非数字 → 422 invalid status",
              client.get("/api/admin/trade/orders", headers=H_OPS,
                         params={"status": "abc"}).status_code == 422)
        check("orders 组合状态与 q 检索并存",
              client.get("/api/admin/trade/orders", headers=H_OPS,
                         params={"status": "1,2", "q": "OPS26ORD1"}
                         ).json()["total"] == 3)

        # ===== 2. 管理账号列表（工单指派数据源）=====
        member = User(email="member@glow.test", password_hash=hash_password("x"),
                      name="Member", role=0, points=100)
        cs_user = User(email="cs@glow.test", password_hash=hash_password("x"),
                       name="Cs", role=1)
        super_admin = User(email="super@glow.test", password_hash=hash_password("x"),
                           name="Super", role=9)
        admin_off = User(email="off@glow.test", password_hash=hash_password("x"),
                         name="Off", role=2, status=0)
        s.add_all([member, cs_user, super_admin, admin_off])
        s.commit()
        check("admins 端点需要鉴权（无 token → 401）",
              client.get("/api/admin/ops/admins").status_code == 401)
        r = client.get("/api/admin/ops/admins", headers=H_OPS)
        d = r.json()
        ids = [i["id"] for i in d["items"]]
        check("admins 仅返回 role>=2 且 status=1（运营+超管，排除顾客/客服/禁用）",
              r.status_code == 200 and set(ids) == {admin.id, super_admin.id},
              ids)
        check("admins 行结构 {id,name,email,role} 且按 id 升序",
              all(set(i.keys()) == {"id", "name", "email", "role"} for i in d["items"])
              and ids == sorted(ids), d["items"])

        # ===== 3. 积分人工调整（加/减/余额不足/用户不存在/审计+流水）=====
        r = client.post(f"/api/admin/ops/members/{member.id}/points", headers=H_OPS,
                        json={"delta": 50, "reason": "service compensation"})
        d = r.json()
        check("积分 +50 → {ok, balance=150}",
              r.status_code == 200 and d == {"ok": True, "balance": 150}, d)
        r = client.post(f"/api/admin/ops/members/{member.id}/points", headers=H_OPS,
                        json={"delta": -30, "reason": "order correction"})
        d = r.json()
        s.expire_all()
        check("积分 -30 → balance=120 且 users.points 同步",
              r.status_code == 200 and d["balance"] == 120
              and s.get(User, member.id).points == 120, d)
        r = client.post(f"/api/admin/ops/members/{member.id}/points", headers=H_OPS,
                        json={"delta": -1000, "reason": "too much"})
        s.expire_all()
        check("积分扣成负 → 409 insufficient points（余额不动）",
              r.status_code == 409 and r.json()["detail"] == "insufficient points"
              and s.get(User, member.id).points == 120,
              (r.status_code, r.json().get("detail")))
        r = client.post("/api/admin/ops/members/999999/points", headers=H_OPS,
                        json={"delta": 10, "reason": "ghost"})
        check("不存在用户 → 404 user not found",
              r.status_code == 404 and r.json()["detail"] == "user not found",
              (r.status_code, r.json().get("detail")))
        check("delta=0 / 超限 / 空 reason → 422",
              client.post(f"/api/admin/ops/members/{member.id}/points", headers=H_OPS,
                          json={"delta": 0, "reason": "x"}).status_code == 422
              and client.post(f"/api/admin/ops/members/{member.id}/points", headers=H_OPS,
                              json={"delta": 2_000_000, "reason": "x"}).status_code == 422
              and client.post(f"/api/admin/ops/members/{member.id}/points", headers=H_OPS,
                              json={"delta": 5, "reason": ""}).status_code == 422)
        led = (s.query(PointsLedger).filter(PointsLedger.user_id == member.id)
               .order_by(PointsLedger.id.desc()).all())
        check("流水落库 reason=11/ref_type=admin/ref_id=管理员/balance_after 串接",
              led[0].reason == 11 and led[0].ref_type == "admin"
              and led[0].ref_id == admin.id and led[0].balance_after == 120
              and led[0].change == -30 and led[1].change == 50
              and led[1].balance_after == 150,
              [(x.change, x.balance_after) for x in led[:3]])
        r = client.get("/api/admin/ops/logs", headers=H_OPS,
                       params={"entity": "member", "action": "points_adjust"})
        d = r.json()
        check("审计落库 points_adjust（diff 含 delta/reason）",
              r.status_code == 200 and d["total"] == 2
              and all(i["diff_json"].get("delta") in (50, -30)
                      and i["diff_json"].get("reason") for i in d["items"]),
              d.get("total"))
        check("积分端点需要鉴权",
              client.post(f"/api/admin/ops/members/{member.id}/points",
                          json={"delta": 5, "reason": "x"}).status_code == 401)

        # ===== 4. 分类管理补全（PUT 更新 + DELETE 删除保护）=====
        cat_a = Category(slug="ops2-a", name="A")
        cat_b = Category(slug="ops2-b", name="B")
        s.add_all([cat_a, cat_b])
        s.flush()
        cat_c = Category(slug="ops2-c", name="C", parent_id=cat_a.id)
        s.add(cat_c)
        s.commit()
        r = client.put(f"/api/admin/catalog/categories/{cat_a.id}", headers=H_OPS,
                       json={"name": "A2", "sort_order": 3, "is_active": False})
        d = r.json()
        check("分类 PUT 部分更新（name/sort_order/is_active，未传字段保持）",
              r.status_code == 200 and d["name"] == "A2" and d["sort_order"] == 3
              and d["is_active"] == 0 and d["slug"] == "ops2-a"
              and d["parent_id"] is None, d)
        r = client.put(f"/api/admin/catalog/categories/{cat_a.id}", headers=H_OPS,
                       json={"slug": "ops2-b"})
        check("slug 改成他人已占用 → 409 slug already exists",
              r.status_code == 409 and r.json()["detail"] == "slug already exists",
              (r.status_code, r.json().get("detail")))
        r = client.put(f"/api/admin/catalog/categories/{cat_a.id}", headers=H_OPS,
                       json={"slug": "ops2-a2"})
        check("slug 改新值排除自身查重 → 200",
              r.status_code == 200 and r.json()["slug"] == "ops2-a2", r.text[:120])
        r = client.put(f"/api/admin/catalog/categories/{cat_a.id}", headers=H_OPS,
                       json={"parent_id": cat_a.id})
        check("parent=self → 400 parent is self",
              r.status_code == 400 and r.json()["detail"] == "parent is self",
              (r.status_code, r.json().get("detail")))
        r = client.put(f"/api/admin/catalog/categories/{cat_a.id}", headers=H_OPS,
                       json={"parent_id": 999999})
        check("parent 不存在 → 400 parent category not found",
              r.status_code == 400 and r.json()["detail"] == "parent category not found",
              (r.status_code, r.json().get("detail")))
        r = client.put(f"/api/admin/catalog/categories/{cat_c.id}", headers=H_OPS,
                       json={"parent_id": cat_b.id})
        check("分类换父 → 200 parent_id 生效",
              r.status_code == 200 and r.json()["parent_id"] == cat_b.id, r.text[:120])
        r = client.put(f"/api/admin/catalog/categories/{cat_c.id}", headers=H_OPS,
                       json={"parent_id": None})
        check("parent_id 显式 null → 挂回根级",
              r.status_code == 200 and r.json()["parent_id"] is None, r.text[:120])
        check("未知分类 PUT/DELETE → 404",
              client.put("/api/admin/catalog/categories/999999", headers=H_OPS,
                         json={"name": "x"}).status_code == 404
              and client.delete("/api/admin/catalog/categories/999999",
                                headers=H_OPS).status_code == 404)
        # 删除保护：有商品引用 / 有子分类 / 干净可删
        cat_p = Category(slug="ops2-p", name="P")
        cat_q = Category(slug="ops2-q", name="Q")
        cat_s2 = Category(slug="ops2-s", name="S")
        s.add_all([cat_p, cat_q, cat_s2])
        s.flush()
        s.add(Product(slug="ops2-gel", title="Ops2 Gel", category_id=cat_p.id,
                      status=1, hero_image="https://img/e.jpg",
                      price_min=1000, price_max=1000))
        s.add(Category(slug="ops2-r", name="R", parent_id=cat_q.id))
        s.commit()
        sid = cat_s2.id
        r = client.delete(f"/api/admin/catalog/categories/{cat_p.id}", headers=H_OPS)
        check("有商品引用 → 409 category in use",
              r.status_code == 409 and r.json()["detail"] == "category in use",
              (r.status_code, r.json().get("detail")))
        r = client.delete(f"/api/admin/catalog/categories/{cat_q.id}", headers=H_OPS)
        check("有子分类 → 409 category has children",
              r.status_code == 409 and r.json()["detail"] == "category has children",
              (r.status_code, r.json().get("detail")))
        r = client.delete(f"/api/admin/catalog/categories/{sid}", headers=H_OPS)
        check("空分类删除 → 200 且行消失",
              r.status_code == 200 and r.json() == {"ok": True}
              and s.query(Category).filter(Category.id == sid).first() is None,
              r.text[:120])
        r = client.get("/api/admin/ops/logs", headers=H_OPS,
                       params={"entity": "category"})
        d = r.json()
        check("分类 update/delete 审计落库",
              r.status_code == 200 and d["total"] >= 3
              and {i["action"] for i in d["items"]} >= {"update", "delete"},
              d.get("total"))

        # ===== 5. 工单状态机补全（4→1 重开清空关单字段 / 客户回复回流）=====
        tk_closed = Ticket(ticket_no="OPS26TK0001", email="guest@glow.test",
                           category=1, subject="reopen me", status=4,
                           closed_at=utcnow(), close_reason=1)
        s.add(tk_closed)
        s.commit()
        r = client.put("/api/admin/support/tickets/OPS26TK0001/status", headers=H_OPS,
                       json={"status": 1})
        d = r.json()
        s.expire_all()
        tk_db = s.query(Ticket).filter(Ticket.ticket_no == "OPS26TK0001").first()
        check("4→1 重开成功（status=1）",
              r.status_code == 200 and d["status"] == 1, (r.status_code, d))
        check("重开后 closed_at/close_reason 清空",
              tk_db.closed_at is None and tk_db.close_reason is None
              and d["closed_at"] is None,
              (tk_db.closed_at, tk_db.close_reason))
        r = client.put("/api/admin/support/tickets/OPS26TK0001/status", headers=H_OPS,
                       json={"status": 3})
        check("重开后 1→3 仍走既有状态机", r.status_code == 200, r.status_code)
        # 行为收紧同步修改：3→1 已放开（已解决待关可重开），改用 3→2 验证非法流转仍 409
        r = client.put("/api/admin/support/tickets/OPS26TK0001/status", headers=H_OPS,
                       json={"status": 2})
        check("非法流转（3→2）→ 409 invalid_status_transition",
              r.status_code == 409
              and r.json()["detail"] == "invalid_status_transition",
              (r.status_code, r.json().get("detail")))
        tk_wait = Ticket(ticket_no="OPS26TK0002", email="guest@glow.test",
                         category=2, subject="waiting", status=2)
        s.add(tk_wait)
        s.commit()
        r = client.post("/api/support/tickets/OPS26TK0002/messages",
                        json={"email": "guest@glow.test", "content": "user reply"})
        s.expire_all()
        tk_db2 = s.query(Ticket).filter(Ticket.ticket_no == "OPS26TK0002").first()
        check("status=2 工单客户追加回复 → 自动回流 1（处理中）",
              r.status_code == 200 and tk_db2.status == 1,
              (r.status_code, tk_db2.status))
        tk_open = Ticket(ticket_no="OPS26TK0003", email="guest@glow.test",
                         category=3, subject="still open", status=1)
        s.add(tk_open)
        s.commit()
        client.post("/api/support/tickets/OPS26TK0003/messages",
                    json={"email": "guest@glow.test", "content": "hi again"})
        s.expire_all()
        tk_db3 = s.query(Ticket).filter(Ticket.ticket_no == "OPS26TK0003").first()
        check("status=1 工单追加回复不回流（保持 1）", tk_db3.status == 1, tk_db3.status)

        # ===== 6. CollectionUpdateIn banner_image 校验（与创建同口径）=====
        r = client.post("/api/admin/catalog/collections", headers=H_OPS,
                        json={"slug": "ops2-coll", "title": "Ops2 Coll",
                              "rule_json": {},
                              "banner_image": "https://img/banner.jpg"})
        coll_id = r.json()["id"]
        check("集合创建（http banner 通过）", r.status_code == 201 and coll_id, r.text[:120])
        r = client.put(f"/api/admin/catalog/collections/{coll_id}", headers=H_OPS,
                       json={"banner_image": "/img/rel.jpg"})
        check("集合 PUT 相对路径 banner → 422",
              r.status_code == 422, r.status_code)
        r = client.put(f"/api/admin/catalog/collections/{coll_id}", headers=H_OPS,
                       json={"banner_image": "javascript:alert(1)"})
        check("集合 PUT javascript: banner → 422", r.status_code == 422, r.status_code)
        r = client.put(f"/api/admin/catalog/collections/{coll_id}", headers=H_OPS,
                       json={"banner_image": "https://img/v2.jpg"})
        s.expire_all()
        check("集合 PUT 合法 http banner → 200 落库",
              r.status_code == 200 and r.json()["banner_image"] == "https://img/v2.jpg"
              and s.get(Collection, coll_id).banner_image == "https://img/v2.jpg",
              r.text[:120])

        s.close()

    print(f"\n{PASSED} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed:", FAILED)
        return 1
    return 0


def test_admin_ops_ext():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
