"""RBAC 权限矩阵自测 —— core/permissions 角色权限 + require_perm 守卫收口。
（GM_DB=sqlite:///test_rbac.sqlite 独立库；BigInteger 垫片同 test_payments.py）

覆盖：
- 后台登录闸门：客服/美甲师可登录，顾客 403
- /admin/me 下发实时权限集
- 客服：工单/订单只读/会员只读放行，退款/设置/商品写 403
- 仓库：发货/库存放行，退款/改地址/商品写/设置 403
- 运营：业务面全放行，管理员账号写 403
- 美甲师：仅 chat 放行，其余 403 artist scope
- 顾客 token 访问后台 → 403 Admin only
"""

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DBF = ROOT / "test_rbac.sqlite"
for suffix in ("", "-wal", "-shm"):
    _f = Path(str(DBF) + suffix)
    if _f.exists():
        _f.unlink()
os.environ["GM_DB"] = "sqlite:///" + str(DBF).replace("\\", "/")
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):
    return "INTEGER"


from app.core.db import SessionLocal, init_db  # noqa: E402
from app.core.enums import UserRole  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

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
roles = {
    "cs": int(UserRole.CS),
    "ops": int(UserRole.OPS),
    "wh": int(UserRole.WAREHOUSE),
    "art": int(UserRole.ARTIST),
    "sup": int(UserRole.SUPER),
}
users = {}
for key, role in roles.items():
    u = User(email=f"{key}@glowrbac.com", password_hash=hash_password("rbacpass123"),
             name=key.upper(), role=role, status=1)
    db.add(u)
    users[key] = u
customer = User(email="guest@glowrbac.com", password_hash=hash_password("rbacpass123"),
                name="Guest", role=0, status=1)
db.add(customer)
db.commit()

H = {k: {"Authorization": f"Bearer {create_token(u.id, u.role)}"}
     for k, u in users.items()}
H_CUST = {"Authorization": f"Bearer {create_token(customer.id, customer.role)}"}

client = TestClient(app)

print("== 登录闸门与会话 ==")
r = client.post("/api/account/admin/login",
                json={"email": "cs@glowrbac.com", "password": "rbacpass123"})
check("客服可登录后台（200 + permissions 下发）",
      r.status_code == 200 and "ticket:manage" in r.json()["user"].get("permissions", []),
      r.text[:160])
r = client.post("/api/account/admin/login",
                json={"email": "art@glowrbac.com", "password": "rbacpass123"})
check("美甲师可登录后台（permissions 仅 chat:manage）",
      r.status_code == 200
      and r.json()["user"].get("permissions") == ["chat:manage"],
      r.text[:160])
r = client.post("/api/account/admin/login",
                json={"email": "guest@glowrbac.com", "password": "rbacpass123"})
check("顾客登录后台 → 403 admin only",
      r.status_code == 403 and r.json()["detail"] == "admin only", r.text[:120])

print("== 客服（CS）作用域 ==")
r = client.get("/api/admin/ops/tickets", headers=H["cs"])
check("工单列表 200", r.status_code == 200, r.text[:120])
r = client.get("/api/admin/trade/orders", headers=H["cs"])
check("订单只读 200", r.status_code == 200, r.text[:120])
r = client.get("/api/admin/ops/members", headers=H["cs"])
check("会员只读 200", r.status_code == 200, r.text[:120])
r = client.post("/api/admin/trade/orders/NOPE/refund", headers=H["cs"], json={})
check("客服退款 → 403 permission denied: trade:refund",
      r.status_code == 403 and "trade:refund" in r.json()["detail"], r.text[:120])
r = client.put("/api/admin/ops/settings", headers=H["cs"],
               json={"key": "free_shipping_threshold", "value": 1})
check("客服改设置 → 403", r.status_code == 403, r.text[:120])
r = client.post("/api/admin/catalog/products", headers=H["cs"], json={})
check("客服建商品 → 403（而非 422，守卫先于校验）",
      r.status_code == 403, r.status_code)

print("== 仓库（WAREHOUSE）作用域 ==")
r = client.get("/api/admin/trade/orders", headers=H["wh"])
check("订单只读 200", r.status_code == 200, r.text[:120])
r = client.post("/api/admin/trade/stock/adjust", headers=H["wh"],
                json={"variant_id": 999999, "change": 5, "reason": "rbac probe"})
check("库存调整进业务层（非 403，404 variant 即守卫通过）",
      r.status_code == 404, r.text[:120])
r = client.put("/api/admin/trade/orders/NOPE/address", headers=H["wh"], json={})
check("仓库改收货地址 → 403 permission denied: trade:manage",
      r.status_code == 403 and "trade:manage" in r.json()["detail"], r.text[:120])
r = client.post("/api/admin/trade/orders/NOPE/refund", headers=H["wh"], json={})
check("仓库退款 → 403 trade:refund",
      r.status_code == 403 and "trade:refund" in r.json()["detail"], r.text[:120])
r = client.get("/api/admin/catalog/products", headers=H["wh"])
check("商品只读 200", r.status_code == 200, r.text[:120])
r = client.post("/api/admin/catalog/products", headers=H["wh"], json={})
check("仓库建商品/改价 → 403 catalog:manage",
      r.status_code == 403 and "catalog:manage" in r.json()["detail"], r.text[:120])
r = client.put("/api/admin/ops/settings", headers=H["wh"],
               json={"key": "free_shipping_threshold", "value": 1})
check("仓库改设置 → 403", r.status_code == 403, r.text[:120])
r = client.get("/api/admin/ops/settings", headers=H["wh"])
check("仓库读设置 → 403", r.status_code == 403, r.text[:120])

print("== 运营（OPS）作用域 ==")
r = client.get("/api/admin/ops/dashboard", headers=H["ops"])
check("看板 200", r.status_code == 200, r.text[:120])
r = client.get("/api/admin/ops/settings", headers=H["ops"])
check("设置读 200", r.status_code == 200, r.text[:120])
r = client.post("/api/admin/ops/admins", headers=H["ops"],
                json={"email": "x@glowrbac.com", "name": "X",
                      "password": "strongpass9", "role": 2})
check("运营建管理员 → 403 superadmin required",
      r.status_code == 403 and r.json()["detail"] == "superadmin required", r.text[:120])

print("== 美甲师（ARTIST）作用域 ==")
r = client.get("/api/admin/chat/conversations", headers=H["art"])
check("chat 会话列表 200", r.status_code == 200, r.text[:120])
r = client.get("/api/admin/ops/dashboard", headers=H["art"])
check("看板 → 403 artist scope",
      r.status_code == 403 and r.json()["detail"] == "artist scope", r.text[:120])
r = client.get("/api/admin/ops/tickets", headers=H["art"])
check("工单 → 403 artist scope", r.status_code == 403
      and r.json()["detail"] == "artist scope", r.text[:120])

print("== 顾客 token 访问后台 ==")
r = client.get("/api/admin/trade/orders", headers=H_CUST)
check("顾客读订单 → 403 Admin only",
      r.status_code == 403 and r.json()["detail"] == "Admin only", r.text[:120])
r = client.get("/api/admin/chat/conversations", headers=H_CUST)
check("顾客读 chat → 403 Admin only", r.status_code == 403, r.text[:120])

print("== 超管（SUPER）与账号管理 ==")
r = client.get("/api/admin/ops/admins", headers=H["sup"])
ids = [i["id"] for i in r.json()["items"]]
check("admins 列表含客服/运营/仓库/超管、排除美甲师与顾客",
      r.status_code == 200 and set(ids) == {users[k].id for k in ("cs", "ops", "wh", "sup")},
      ids)
r = client.post("/api/admin/ops/admins", headers=H["sup"],
                json={"email": "newcs@glowrbac.com", "name": "NewCs",
                      "password": "strongpass9", "role": 1})
check("超管建客服账号 → 201/200 且可登录后台",
      r.status_code in (200, 201)
      and client.post("/api/account/admin/login",
                      json={"email": "newcs@glowrbac.com", "password": "strongpass9"}
                      ).status_code == 200, r.text[:160])

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
