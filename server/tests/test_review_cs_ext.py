"""评审修复项自测（CS 扩展）—— 分类成环 / batch-status / variant 日志深链 / weight_gram
工单 3→1 / 聊天 pending_total + 回复 422 + 美甲师作用域 / 文章 cover
（GM_DB=sqlite:///test_review_cs.sqlite + BigInteger→INTEGER 垫片，搭建参照 test_catalog_ext.py）"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DBF = ROOT / "test_review_cs.sqlite"
for suffix in ("", "-wal", "-shm"):
    _f = Path(str(DBF) + suffix)
    if _f.exists():
        _f.unlink()
import os

os.environ["GM_DB"] = "sqlite:///" + str(DBF).replace("\\", "/")
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):
    return "INTEGER"


from app.core.db import SessionLocal, init_db, utcnow  # noqa: E402
from app.core.enums import UserRole  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, Product, Ticket, User  # noqa: E402

PASSED = 0
FAILED = []


def check(name, cond, info=""):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok {PASSED:02d} - {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {PASSED + 1:02d} - {name}  {info}")


init_db()
db = SessionLocal()

# 管理员夹具：运营(role=2) + 两位美甲师(role=4，作用域互斥验证用)
ops = User(email="ops@rvw.test", password_hash=hash_password("x"), name="Rvw Ops",
           role=int(UserRole.OPS))
art1 = User(email="art1@rvw.test", password_hash=hash_password("x"), name="Artist One",
            role=int(UserRole.ARTIST), artist_intro="intro")
art2 = User(email="art2@rvw.test", password_hash=hash_password("x"), name="Artist Two",
            role=int(UserRole.ARTIST), artist_intro="intro")
db.add_all([ops, art1, art2])
cat = Category(slug="rvw-cat", name="Rvw Cat")
db.add(cat)
db.flush()
now = utcnow()
p_d1 = Product(slug="rvw-d1", title="Draft One", category_id=cat.id, status=0,
               price_min=100, price_max=100, hero_image="/img/d1.jpg")
p_live = Product(slug="rvw-live", title="Live One", category_id=cat.id, status=1,
                 price_min=200, price_max=200, hero_image="/img/live.jpg", published_at=now)
p_nocat = Product(slug="rvw-nocat", title="No Cat", category_id=999999, status=2,
                  price_min=300, price_max=300, hero_image="/img/nc.jpg")
db.add_all([p_d1, p_live, p_nocat])
db.commit()

H = {"Authorization": f"Bearer {create_token(ops.id, ops.role)}"}
H_A1 = {"Authorization": f"Bearer {create_token(art1.id, art1.role)}"}
H_A2 = {"Authorization": f"Bearer {create_token(art2.id, art2.role)}"}

with TestClient(app) as client:

    # ===== 1. 分类父子环检测 =====
    print("== 分类父子环 ==")
    r = client.post("/api/admin/catalog/categories", headers=H,
                    json={"slug": "rvw-a", "name": "A"})
    check("建根分类 A", r.status_code == 201, r.text[:120])
    a_id = r.json()["id"]
    r = client.post("/api/admin/catalog/categories", headers=H,
                    json={"slug": "rvw-b", "name": "B", "parent_id": a_id})
    b_id = r.json()["id"]
    r = client.put(f"/api/admin/catalog/categories/{a_id}", headers=H,
                   json={"parent_id": b_id})
    check("A→B→A 成环 → 400 category cycle detected",
          r.status_code == 400 and r.json()["detail"] == "category cycle detected",
          (r.status_code, r.json().get("detail")))
    r = client.post("/api/admin/catalog/categories", headers=H,
                    json={"slug": "rvw-c", "name": "C", "parent_id": b_id})
    c_id = r.json()["id"]
    r = client.put(f"/api/admin/catalog/categories/{a_id}", headers=H,
                   json={"parent_id": c_id})
    check("深层成环 A→C(→B→A) → 400 category cycle detected",
          r.status_code == 400 and r.json()["detail"] == "category cycle detected",
          (r.status_code, r.json().get("detail")))
    r = client.put(f"/api/admin/catalog/categories/{a_id}", headers=H,
                   json={"parent_id": a_id})
    check("直接自父 → 400 parent is self（原语义保留）",
          r.status_code == 400 and r.json()["detail"] == "parent is self",
          (r.status_code, r.json().get("detail")))
    r = client.put(f"/api/admin/catalog/categories/{c_id}", headers=H,
                   json={"parent_id": a_id})
    check("合法换父（C 挂 A，无环）→ 200",
          r.status_code == 200 and r.json()["parent_id"] == a_id, r.text[:120])

    # ===== 2. 批量上下架 POST /products/batch-status =====
    print("== batch-status ==")
    r = client.post("/api/admin/catalog/products/batch-status", headers=H,
                    json={"ids": [p_d1.id, 999999], "status": 1})
    d = r.json()
    db.expire_all()
    check("发布：成功 1 + 失败明细（未知 id）",
          r.status_code == 200 and d["updated"] == 1
          and d["failed"] == [{"id": 999999, "reason": "product not found"}], d)
    check("草稿 0→1 生效且 published_at 落库",
          db.get(Product, p_d1.id).status == 1
          and db.get(Product, p_d1.id).published_at is not None)
    r = client.post("/api/admin/catalog/products/batch-status", headers=H,
                    json={"ids": [p_nocat.id], "status": 1})
    check("发布校验：分类缺失该条失败",
          r.json()["updated"] == 0
          and r.json()["failed"] == [{"id": p_nocat.id, "reason": "category not found"}],
          r.json())
    r = client.post("/api/admin/catalog/products/batch-status", headers=H,
                    json={"ids": [p_d1.id, p_live.id], "status": 2})
    db.expire_all()
    check("归档：任意状态可（1/1→2 双成功）",
          r.json()["updated"] == 2 and r.json()["failed"] == []
          and db.get(Product, p_d1.id).status == 2
          and db.get(Product, p_live.id).status == 2, r.json())
    r = client.post("/api/admin/catalog/products/batch-status", headers=H,
                    json={"ids": [p_d1.id], "status": 0})
    db.expire_all()
    check("恢复草稿：归档 2→0 可",
          r.json()["updated"] == 1 and db.get(Product, p_d1.id).status == 0, r.json())
    r = client.post("/api/admin/catalog/products/batch-status", headers=H,
                    json={"ids": [p_d1.id], "status": 0})
    check("恢复草稿：非归档态（0）该条失败",
          r.json()["updated"] == 0 and r.json()["failed"][0]["reason"]
          == "only archived can be restored to draft", r.json())
    check("status 越界 3 → 422", client.post(
        "/api/admin/catalog/products/batch-status", headers=H,
        json={"ids": [p_d1.id], "status": 3}).status_code == 422)
    check("空 ids → 422", client.post(
        "/api/admin/catalog/products/batch-status", headers=H,
        json={"ids": [], "status": 1}).status_code == 422)
    check("ids 超 100 → 422", client.post(
        "/api/admin/catalog/products/batch-status", headers=H,
        json={"ids": list(range(101)), "status": 1}).status_code == 422)
    for action in ("publish", "unpublish", "restore_draft"):
        r = client.get("/api/admin/ops/logs", headers=H,
                       params={"entity": "product", "action": action})
        check(f"批量操作逐条记 admin log（action={action}）",
              r.status_code == 200 and r.json()["total"] >= 1, r.json().get("total"))

    # ===== 3+4. 变体 weight_gram 可读可改 + 日志 diff 深链 product_id =====
    print("== variant weight_gram / 日志深链 ==")
    r = client.post(f"/api/admin/catalog/products/{p_d1.id}/variants", headers=H,
                    json={"sku": "RVW-V1", "option1_value": "Almond",
                          "option2_value": "24pcs", "price": 999, "stock": 5,
                          "weight_gram": 45})
    check("创建变体带 weight_gram=45", r.status_code == 201
          and r.json()["weight_gram"] == 45, r.text[:150])
    vid = r.json()["id"]
    r = client.put(f"/api/admin/catalog/variants/{vid}", headers=H,
                   json={"weight_gram": 88})
    check("更新 weight_gram=88 生效",
          r.status_code == 200 and r.json()["weight_gram"] == 88, r.text[:150])
    r = client.get("/api/admin/catalog/variants", headers=H,
                   params={"product_id": p_d1.id})
    item = next((i for i in r.json()["items"] if i["id"] == vid), None)
    check("变体列表输出 weight_gram（可读）",
          item is not None and item["weight_gram"] == 88, r.json()["items"])
    check("weight_gram 越界（>100000 / 负数）→ 422",
          client.put(f"/api/admin/catalog/variants/{vid}", headers=H,
                     json={"weight_gram": 100001}).status_code == 422
          and client.put(f"/api/admin/catalog/variants/{vid}", headers=H,
                         json={"weight_gram": -1}).status_code == 422)
    logs = client.get("/api/admin/ops/logs", headers=H,
                      params={"entity": "variant", "size": 50}).json()["items"]
    lg_create = next((i for i in logs if i["entity_id"] == vid
                      and i["action"] == "create"), None)
    check("variant create 日志 diff 含 product_id",
          lg_create is not None and lg_create["diff_json"].get("product_id") == p_d1.id,
          lg_create and lg_create["diff_json"])
    r = client.put(f"/api/admin/catalog/variants/{vid}", headers=H, json={"price": 1001})
    logs = client.get("/api/admin/ops/logs", headers=H,
                      params={"entity": "variant", "size": 50}).json()["items"]
    lg_update = next((i for i in logs if i["entity_id"] == vid
                      and i["action"] == "update"), None)
    check("variant update 日志 diff 含 product_id（entity_id 仍为变体 id）",
          lg_update is not None and lg_update["diff_json"].get("product_id") == p_d1.id
          and lg_update["entity_id"] == vid, lg_update and lg_update["diff_json"])
    r = client.delete(f"/api/admin/catalog/variants/{vid}", headers=H)
    logs = client.get("/api/admin/ops/logs", headers=H,
                      params={"entity": "variant", "size": 50}).json()["items"]
    lg_del = next((i for i in logs if i["entity_id"] == vid
                   and i["action"] == "delete"), None)
    check("variant delete 日志 diff 含 product_id（原行为保留）",
          r.status_code == 200 and lg_del is not None
          and lg_del["diff_json"].get("product_id") == p_d1.id)

    # ===== 5. 工单已解决(3)态重开 =====
    print("== 工单 3→1 ==")
    t3a = Ticket(ticket_no="TKRVW00000001", email="u3a@rvw.test", category=1,
                 subject="resolved a", status=3, closed_at=now, close_reason=1)
    t3b = Ticket(ticket_no="TKRVW00000002", email="u3b@rvw.test", category=1,
                 subject="resolved b", status=3, closed_at=now, close_reason=2)
    t4 = Ticket(ticket_no="TKRVW00000003", email="u4@rvw.test", category=1,
                subject="closed", status=4, closed_at=now, close_reason=1)
    db.add_all([t3a, t3b, t4])
    db.commit()
    r = client.post("/api/support/tickets/TKRVW00000001/messages",
                    json={"email": "u3a@rvw.test", "content": "还有问题"})
    db.expire_all()
    t3a_db = db.query(Ticket).filter(Ticket.ticket_no == "TKRVW00000001").first()
    check("客户在 3 态追加留言 → 回流 1",
          r.status_code == 200 and t3a_db.status == 1, (r.status_code, t3a_db.status))
    check("3→1（留言路径）不清 close 审计字段",
          t3a_db.closed_at is not None and t3a_db.close_reason == 1,
          (t3a_db.closed_at, t3a_db.close_reason))
    r = client.put("/api/admin/support/tickets/TKRVW00000002/status", headers=H,
                   json={"status": 1})
    db.expire_all()
    t3b_db = db.query(Ticket).filter(Ticket.ticket_no == "TKRVW00000002").first()
    check("PUT status=1：3→1 重开成功",
          r.status_code == 200 and r.json()["status"] == 1 and t3b_db.status == 1,
          (r.status_code, r.json().get("status")))
    check("3→1（PUT 路径）不清 close 审计字段",
          t3b_db.closed_at is not None and t3b_db.close_reason == 2,
          (t3b_db.closed_at, t3b_db.close_reason))
    r = client.put("/api/admin/support/tickets/TKRVW00000003/status", headers=H,
                   json={"status": 1})
    db.expire_all()
    t4_db = db.query(Ticket).filter(Ticket.ticket_no == "TKRVW00000003").first()
    check("4→1 重开仍清空关单字段（原语义保留）",
          r.status_code == 200 and t4_db.closed_at is None and t4_db.close_reason is None)
    client.post("/api/admin/ops/tickets/TKRVW00000003/close", headers=H,
                json={"close_reason": 1})
    r = client.post("/api/support/tickets/TKRVW00000003/messages",
                    json={"email": "u4@rvw.test", "content": "closed msg"})
    check("4 态（重新关闭后）客户留言仍 409", r.status_code == 409, r.status_code)
    r = client.post("/api/admin/ops/tickets/TKRVW00000001/reply", headers=H,
                    json={"content": "x" * 2001})
    check("工单客服回复 >2000 → 422", r.status_code == 422, r.status_code)
    r = client.post("/api/support/tickets/TKRVW00000001/messages",
                    json={"email": "u3a@rvw.test", "content": "x" * 2001})
    check("工单客户留言 >2000 → 422", r.status_code == 422, r.status_code)

    # ===== 6+7+8. 聊天：pending_total / 回复超长 422 / 美甲师作用域 =====
    print("== chat pending_total / 422 / role4 作用域 ==")
    r = client.post("/api/chat/conversations",
                    json={"channel": 1, "token": "rvwtokpend1", "email": "hp@rvw.test"})
    H_PEND = r.json()["conv_no"]
    client.post(f"/api/chat/conversations/{H_PEND}/messages",
                json={"token": "rvwtokpend1", "content": "待回复的一条"})
    r = client.post("/api/chat/conversations",
                    json={"channel": 1, "token": "rvwtokrepl1", "email": "hr@rvw.test"})
    H_REPL = r.json()["conv_no"]
    client.post(f"/api/chat/conversations/{H_REPL}/messages",
                json={"token": "rvwtokrepl1", "content": "你好"})
    client.post(f"/api/admin/chat/conversations/{H_REPL}/reply", headers=H,
                json={"content": "客服回复～"})
    r = client.post("/api/chat/conversations",
                    json={"channel": 2, "token": "rvwtokart1x", "email": "a1@rvw.test",
                          "artist_id": art1.id})
    A_ONE = r.json()["conv_no"]
    client.post(f"/api/chat/conversations/{A_ONE}/messages",
                json={"token": "rvwtokart1x", "content": "美甲师会话留言"})
    r = client.post("/api/chat/conversations",
                    json={"channel": 2, "token": "rvwtokart2x", "email": "a2@rvw.test",
                          "artist_id": art2.id})
    A_TWO = r.json()["conv_no"]
    client.post(f"/api/chat/conversations/{A_TWO}/messages",
                json={"token": "rvwtokart2x", "content": "二号美甲师会话留言"})

    r = client.get("/api/admin/chat/conversations", headers=H)
    d = r.json()
    pend_item = next(i for i in d["items"] if i["conv_no"] == H_PEND)
    repl_item = next(i for i in d["items"] if i["conv_no"] == H_REPL)
    check("per-item pending_reply 谓词正确（待回复=红点 / 已回复=无）",
          pend_item["pending_reply"] is True and repl_item["pending_reply"] is False)
    check("列表顶层 pending_total 全局计数（=3：1 人工 + 2 美甲师）",
          d["pending_total"] == 3, d.get("pending_total"))
    r = client.get("/api/admin/chat/conversations", headers=H,
                   params={"channel": 1})
    d = r.json()
    check("pending_total 忽略筛选（channel=1 仍全局 =3）且分页项照常过滤",
          d["pending_total"] == 3 and all(i["channel"] == 1 for i in d["items"])
          and {i["conv_no"] for i in d["items"]} == {H_PEND, H_REPL},
          (d.get("pending_total"), [i["conv_no"] for i in d["items"]]))

    r = client.post(f"/api/admin/chat/conversations/{H_REPL}/reply", headers=H,
                    json={"content": "x" * 2001})
    check("后台回复 >2000 → 422（不再静默截断）",
          r.status_code == 422 and "reply too long" in r.text, (r.status_code, r.text[:150]))
    r = client.post(f"/api/admin/chat/conversations/{H_REPL}/reply", headers=H,
                    json={"content": "y" * 2000})
    check("后台回复恰好 2000 → 200", r.status_code == 200, r.status_code)

    r = client.get("/api/admin/chat/conversations", headers=H_A1)
    d = r.json()
    check("role4 不带 mine 强制只看本人会话",
          d["total"] == 1 and d["items"][0]["conv_no"] == A_ONE,
          (d.get("total"), [i["conv_no"] for i in d.get("items", [])]))
    r = client.get("/api/admin/chat/conversations", headers=H_A1, params={"mine": 0})
    d = r.json()
    check("role4 显式 mine=0 也被忽略（仍仅本人会话）",
          d["total"] == 1 and d["items"][0]["conv_no"] == A_ONE, d.get("total"))
    check("role4 作用域内 pending_total 只计本人（=1）",
          d["pending_total"] == 1, d.get("pending_total"))
    r = client.get("/api/admin/chat/conversations", headers=H_A2)
    check("另一位美甲师同样只见本人（A_TWO）",
          r.json()["total"] == 1 and r.json()["items"][0]["conv_no"] == A_TWO)

    r = client.post(f"/api/admin/chat/conversations/{A_ONE}/reply", headers=H_A2,
                    json={"content": "越权回复"})
    check("role4 回复他人会话 → 403 not your conversation",
          r.status_code == 403 and r.json()["detail"] == "not your conversation",
          (r.status_code, r.json().get("detail")))
    r = client.post(f"/api/admin/chat/conversations/{H_PEND}/take", headers=H_A2)
    check("role4 接单非本人会话 → 403", r.status_code == 403
          and r.json()["detail"] == "not your conversation", r.status_code)
    r = client.post(f"/api/admin/chat/conversations/{A_ONE}/close", headers=H_A2)
    check("role4 关闭他人会话 → 403", r.status_code == 403
          and r.json()["detail"] == "not your conversation", r.status_code)
    r = client.post(f"/api/admin/chat/conversations/{A_ONE}/resume-ai", headers=H_A2)
    check("role4 转回 AI 他人会话 → 403", r.status_code == 403
          and r.json()["detail"] == "not your conversation", r.status_code)
    r = client.get(f"/api/admin/chat/conversations/{A_ONE}", headers=H_A2)
    check("role4 读他人会话 → 403 not your conversation",
          r.status_code == 403 and r.json()["detail"] == "not your conversation",
          (r.status_code, r.json().get("detail")))
    r = client.get(f"/api/admin/chat/conversations/{A_ONE}", headers=H_A1)
    check("role4 读本人会话正常（200 详情）",
          r.status_code == 200 and r.json()["conv_no"] == A_ONE, r.status_code)
    r = client.post(f"/api/admin/chat/conversations/{A_ONE}/reply", headers=H_A1,
                    json={"content": "本人回复"})
    check("美甲师回复本人会话正常（sender=5）",
          r.status_code == 200 and r.json()["messages"][-1]["sender"] == 5, r.text[:150])
    r = client.post(f"/api/admin/chat/conversations/{A_TWO}/reply", headers=H,
                    json={"content": "运营代答不受限"})
    check("运营(role2) 代答美甲师会话不受作用域限制（sender=2）",
          r.status_code == 200 and r.json()["messages"][-1]["sender"] == 2, r.status_code)

    # ===== 9. 文章封面 cover 可维护 =====
    print("== article cover ==")
    r = client.post("/api/admin/ops/articles", headers=H, json={
        "slug": "rvw-cover-1", "title": "Cover Test", "author": "Team",
        "content_md": "# Hi\nbody", "cover": "/img/cover.jpg", "status": 1})
    check("创建文章带 cover", r.status_code == 200
          and r.json()["cover"] == "/img/cover.jpg", r.text[:200])
    art_id = r.json()["id"]
    r = client.get("/api/content/articles/rvw-cover-1")
    check("公开详情回显 cover", r.status_code == 200
          and r.json()["cover"] == "/img/cover.jpg", r.text[:150])
    r = client.put(f"/api/admin/ops/articles/{art_id}", headers=H,
                   json={"cover": "https://img/new-cover.jpg"})
    check("更新 cover 生效", r.status_code == 200
          and r.json()["cover"] == "https://img/new-cover.jpg", r.text[:150])
    r = client.put(f"/api/admin/ops/articles/{art_id}", headers=H, json={"cover": ""})
    check("空串清除 cover", r.status_code == 200 and not r.json()["cover"], r.text[:150])
    r = client.put(f"/api/admin/ops/articles/{art_id}", headers=H,
                   json={"cover": "x" * 501})
    check("cover 超长（>500）→ 422", r.status_code == 422, r.status_code)
    r = client.post("/api/admin/ops/articles", headers=H, json={
        "slug": "rvw-cover-2", "title": "No Cover", "author": "Team",
        "content_md": "body", "status": 0})
    check("不传 cover → 默认空", r.status_code == 200 and not r.json()["cover"])

db.close()

print(f"\nALL PASS: {PASSED}/{PASSED + len(FAILED)}")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
