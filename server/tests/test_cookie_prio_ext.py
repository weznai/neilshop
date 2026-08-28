"""前后台会话隔离回归：Cookie path 隔离 + 身份解析严格互不兜底。

事故背景：运营同一浏览器登着后台（gm_admin_token）再在前台注册/登录新会员，
前台 /api/account/me 曾按 admin 优先解析，把新会员串成 admin@glowmag.com。
本套件验证归一后的隔离语义：
- gm_admin_token path=/api/admin 圈住后台子树，同域双 Cookie 物理不并存
- 前台解析只认 gm_token（残留旧 path=/ 的 admin Cookie 也无济于事）
- 后台解析只认 gm_admin_token / Bearer；纯 admin 会话访问前台 API → 401
- 旧 /api/account/admin/* 路径 307 兜底跳新路径
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DB = "glowmag_test_cc"
import pymysql  # noqa: E402

_cn = pymysql.connect(host="127.0.0.1", user="glowmag", password="glowmag123")
with _cn.cursor() as _cur:
    _cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    _cur.execute(f"CREATE DATABASE {TEST_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
_cn.close()
os.environ["GM_DB"] = f"mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/{TEST_DB}?charset=utf8mb4"
os.environ["GM_COOKIE_AUTH"] = "1"  # Cookie 通道开启：Set-Cookie 进 jar，模拟浏览器 path 匹配
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import User  # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def build_fixtures() -> None:
    db = SessionLocal()
    try:
        db.add(User(email="admin@glowmag.com",
                    password_hash=hash_password("adminpass123"),
                    name="Admin", role=2))
        db.commit()
    finally:
        db.close()


@case
def cookie_isolation_admin_and_member(client, fx):
    """核心回归：登着后台 admin 会话注册新会员，前台 /me 必须是会员本身。"""
    r = client.post("/api/admin/session/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"})
    assert r.status_code == 200, r.text

    r2 = client.post("/api/account/register", json={
        "email": "newbie@glowmag.com", "password": "password8", "name": "Newbie"})
    assert r2.status_code == 201, r2.text

    me = client.get("/api/account/me")
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "newbie@glowmag.com", \
        f"前台身份被后台 admin 会话串号: {me.json()['email']}"

    # 后台端点仍是 admin 身份（同域下 jar 按 path 各自携带，互不干扰）
    dash = client.get("/api/admin/ops/dashboard")
    assert dash.status_code == 200, dash.text
    adm = client.get("/api/admin/session/me")
    assert adm.status_code == 200, adm.text
    assert adm.json()["email"] == "admin@glowmag.com"


@case
def stale_root_path_admin_cookie_harmless(client, fx):
    """浏览器残留历史 path=/ 的旧 admin Cookie：前台身份解析不受影响。"""
    r = client.post("/api/admin/session/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"})
    assert r.status_code == 200
    token = r.json()["token"]
    client.cookies.set("gm_admin_token", token, path="/")
    me = client.get("/api/account/me")
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "newbie@glowmag.com"
    client.cookies.set("gm_admin_token", "", path="/")  # 清理伪造


@case
def admin_only_session_no_front_fallback(client, fx):
    """纯 admin 会话（无 gm_token）访问前台 API → 401：前后台互不兜底。"""
    out = client.post("/api/account/logout")  # 清 gm_token，admin 会话保留
    assert out.status_code == 200
    me = client.get("/api/account/me")
    assert me.status_code == 401, f"前台不应再认 admin 会话: {me.status_code}"


@case
def legacy_paths_307_redirect(client, fx):
    """旧 /api/account/admin/* → 307 新路径（缓存旧前端兜底，保留方法与体）。"""
    r = client.post("/api/account/admin/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"},
        follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/api/admin/session/login"
    r2 = client.get("/api/account/admin/me", follow_redirects=False)
    assert r2.status_code == 307 and r2.headers["location"] == "/api/admin/session/me"
    # 307 跟随后完整可用（老前端零改动能继续工作）
    r3 = client.post("/api/account/admin/login", json={
        "email": "admin@glowmag.com", "password": "adminpass123"})
    assert r3.status_code == 200, r3.text


@case
def bearer_channel_unaffected(client, fx):
    """Bearer 通道：显式会员 token 调前台端点正常（API 客户端/测试套件语义）。"""
    tok = client.post("/api/account/login", json={
        "email": "newbie@glowmag.com", "password": "password8"}).json()["token"]
    me = client.get("/api/account/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "newbie@glowmag.com"


def main() -> int:
    with TestClient(app) as client:
        build_fixtures()
        passed = 0
        failed = 0
        for fn in CASES:
            try:
                fn(client, {})
                passed += 1
                print(f"PASS {fn.__name__}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {fn.__name__}: {exc}")
        print(f"{passed}/{passed + failed} passed")
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
