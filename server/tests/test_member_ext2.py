"""智能体（member/orders/content 域扩展）自测 —— 邮箱修改双步验证 / 用户侧订单改址 /
评价图片上传 / Google·Apple OAuth（dev-login + 回调 mock）。
（GM_DB=sqlite 独立库带随机后缀防并发冲突；BigInteger 垫片同 test_payments.py；
真实外网调用全部 mock，不发真实请求）"""

import os
import re
import secrets
import sys
from datetime import timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, f"test_member_ext2_{secrets.token_hex(4)}.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"  # 纯 Bearer 通道：登录 Cookie 不进 TestClient 会话
os.environ.setdefault("GM_ENV", "dev")  # dev_code / dev_mock / dev-login 均依赖 dev
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient

from app.core.db import SessionLocal, utcnow
from app.core.security import create_token, hash_password
from app.domains.member import service_oauth
from app.main import app
from app.models import Order, OrderTimeline, OutboxEvent, User
from app.models.user import EmailChangeRequest

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


def _register(client, email, password="password8", name="Tester"):
    r = client.post("/api/account/register", json={
        "email": email, "password": password, "name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _login_headers(client, email, password="password8"):
    tok = client.post("/api/account/login", json={
        "email": email, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _mk_order(s, *, order_no, user_id=None, email, status=1,
              shipping_status=0, address=None):
    o = Order(
        order_no=order_no, user_id=user_id, email=email, status=status,
        shipping_status=shipping_status, subtotal=1000, grand_total=1000,
        shipping_address=address or {
            "full_name": "Old Name", "line1": "1 Old St", "line2": "Apt 5",
            "city": "Austin", "state": "TX", "zip": "78701",
            "country": "US", "phone": "555-0100",
        },
        placed_at=utcnow(),
    )
    s.add(o)
    s.commit()
    return o


ADDR_BODY = {
    "full_name": "Maya New", "line1": "99 New Ave", "line2": None,
    "city": "Dallas", "state": "NY", "zip": "10001",
    "country": "US", "phone": "555-0199",
}


with TestClient(app) as client:
    s = SessionLocal()

    # ================= 1. 邮箱修改（双步验证） =================
    _register(client, "changer@glowmag.com", name="Changer")
    _register(client, "other@glowmag.com", name="Other")
    H = _login_headers(client, "changer@glowmag.com")

    r = client.post("/api/account/email-change", headers=H, json={
        "password": "WRONGpass1", "new_email": "fresh@glowmag.com"})
    check("改邮箱：密码错 → 401 invalid_password",
          r.status_code == 401 and r.json()["detail"] == "invalid_password", r.text)

    r = client.post("/api/account/email-change", headers=H, json={
        "password": "password8", "new_email": "changer@glowmag.com"})
    check("改邮箱：同邮箱 → 400 same_email",
          r.status_code == 400 and r.json()["detail"] == "same_email", r.text)

    r = client.post("/api/account/email-change", headers=H, json={
        "password": "password8", "new_email": "other@glowmag.com"})
    check("改邮箱：已被占 → 409 email_taken",
          r.status_code == 409 and r.json()["detail"] == "email_taken", r.text)

    r = client.post("/api/account/email-change", headers=H, json={
        "password": "password8", "new_email": "fresh@glowmag.com"})
    d = r.json()
    row = s.query(EmailChangeRequest).filter(
        EmailChangeRequest.user_id != 0,
        EmailChangeRequest.new_email == "fresh@glowmag.com",
    ).order_by(EmailChangeRequest.id.desc()).first()
    check("改邮箱：成功 → {ok:true} + dev 环境 dev_code（6 位数字）且与落库一致",
          r.status_code == 200 and d.get("ok") is True
          and re.fullmatch(r"\d{6}", d.get("dev_code") or "")
          and row is not None and row.code == d["dev_code"]
          and row.used_at is None
          and row.expires_at > utcnow() + timedelta(minutes=9), d)

    r = client.post("/api/account/email-change/confirm", headers=H,
                    json={"code": "000000"})
    check("改邮箱：错码 → 409 invalid_code",
          r.status_code == 409 and r.json()["detail"] == "invalid_code", r.text)

    r = client.post("/api/account/email-change/confirm", headers=H,
                    json={"code": d["dev_code"]})
    body = r.json()
    s.expire_all()
    u = s.query(User).filter(User.email == "fresh@glowmag.com").first()
    check("改邮箱：确认 → {ok:true, user 与 /me 同形} 且邮箱已更新",
          r.status_code == 200 and body.get("ok") is True
          and body["user"]["email"] == "fresh@glowmag.com"
          and set(body["user"]) >= {"id", "email", "name", "points", "tier",
                                    "total_spent", "birthday", "created_at"}
          and "delete_request" in body["user"]
          and u is not None and u.id == body["user"]["id"], body)

    me = client.get("/api/account/me", headers=H).json()
    check("改邮箱：原 token（基于 user id）无需重签，/me 直读新邮箱",
          me["email"] == "fresh@glowmag.com", me)

    r = client.post("/api/account/email-change/confirm", headers=H,
                    json={"code": d["dev_code"]})
    check("改邮箱：验证码重放 → 409 invalid_code（已消费）",
          r.status_code == 409 and r.json()["detail"] == "invalid_code", r.text)

    r = client.post("/api/account/login", json={
        "email": "fresh@glowmag.com", "password": "password8"})
    r2 = client.post("/api/account/login", json={
        "email": "changer@glowmag.com", "password": "password8"})
    check("改邮箱：新邮箱可登录，旧邮箱 401",
          r.status_code == 200 and r2.status_code == 401, (r.status_code, r2.status_code))

    # 旧码作废：连发两次请求，第一码失效
    H = _login_headers(client, "fresh@glowmag.com")
    c1 = client.post("/api/account/email-change", headers=H, json={
        "password": "password8", "new_email": "fresh2@glowmag.com"}).json()["dev_code"]
    c2 = client.post("/api/account/email-change", headers=H, json={
        "password": "password8", "new_email": "fresh2@glowmag.com"}).json()["dev_code"]
    r1 = client.post("/api/account/email-change/confirm", headers=H, json={"code": c1})
    r2 = client.post("/api/account/email-change/confirm", headers=H, json={"code": c2})
    check("改邮箱：同用户新请求作废旧码（第一码 409，第二码成功）",
          r1.status_code == 409 and r2.status_code == 200
          and r2.json()["user"]["email"] == "fresh2@glowmag.com",
          (r1.text, r2.text))

    # 过期路径：落库后手动拨快 expires_at
    H = _login_headers(client, "fresh2@glowmag.com")
    code = client.post("/api/account/email-change", headers=H, json={
        "password": "password8", "new_email": "fresh3@glowmag.com"}).json()["dev_code"]
    s.query(EmailChangeRequest).filter(
        EmailChangeRequest.code == code).update({"expires_at": utcnow() - timedelta(seconds=1)})
    s.commit()
    r = client.post("/api/account/email-change/confirm", headers=H, json={"code": code})
    check("改邮箱：过期码 → 409 expired",
          r.status_code == 409 and r.json()["detail"] == "expired", r.text)

    check("改邮箱：未登录 → 401",
          client.post("/api/account/email-change", json={
              "password": "x", "new_email": "a@glowmag.com"}).status_code == 401
          and client.post("/api/account/email-change/confirm",
                          json={"code": "123456"}).status_code == 401)

    # ================= 2. 用户侧订单改址 =================
    maya = User(email="maya@glowmag.com",
                password_hash=hash_password("mayapass123"), name="Maya")
    bo = User(email="bo@glowmag.com",
              password_hash=hash_password("bopass1234"), name="Bo")
    s.add_all([maya, bo])
    s.commit()
    H_maya = {"Authorization": f"Bearer {create_token(maya.id, 0)}"}
    H_bo = {"Authorization": f"Bearer {create_token(bo.id, 0)}"}

    o1 = _mk_order(s, order_no="NS260826AA0001", user_id=maya.id,
                   email="maya@glowmag.com", status=1, shipping_status=0)
    o2 = _mk_order(s, order_no="NS260826BB0002", user_id=None,
                   email="guest@glowmag.com", status=0, shipping_status=0)
    o3 = _mk_order(s, order_no="NS260826CC0003", user_id=maya.id,
                   email="maya@glowmag.com", status=3, shipping_status=2)
    o4 = _mk_order(s, order_no="NS260826DD0004", user_id=maya.id,
                   email="maya@glowmag.com", status=8, shipping_status=0)
    o5 = _mk_order(s, order_no="NS260826EE0005", user_id=maya.id,
                   email="maya@glowmag.com", status=2, shipping_status=1)

    r = client.put(f"/api/orders/{o1.order_no}/address", headers=H_maya,
                   json=ADDR_BODY)
    s.expire_all()
    o1db = s.get(Order, o1.id)
    tl = s.query(OrderTimeline).filter(
        OrderTimeline.order_id == o1.id,
        OrderTimeline.event == "address_updated").order_by(
        OrderTimeline.id.desc()).first()
    check("改址：属主 status=1 未发货 → {ok:true}，地址整对象按 body 重建且保留键结构",
          r.status_code == 200 and r.json() == {"ok": True}
          and o1db.shipping_address == {
              "full_name": "Maya New", "line1": "99 New Ave", "line2": None,
              "city": "Dallas", "state": "NY", "zip": "10001",
              "country": "US", "phone": "555-0199",
          }, (r.text, o1db.shipping_address))
    check("改址：timeline address_updated（actor=user，detail 仅 city/country/zip，无完整地址）",
          tl is not None and tl.actor == "user"
          and tl.detail["old"] == {"city": "Austin", "country": "US", "zip": "78701"}
          and tl.detail["new"] == {"city": "Dallas", "country": "US", "zip": "10001"}
          and "line1" not in tl.detail["old"] and "full_name" not in tl.detail["new"],
          tl.detail if tl else None)

    r = client.put(f"/api/orders/{o2.order_no}/address",
                   params={"email": "guest@glowmag.com"}, json=ADDR_BODY)
    check("改址：游客 email 双因子（status=0 待付）→ 成功",
          r.status_code == 200 and r.json() == {"ok": True}, r.text)

    r = client.put(f"/api/orders/{o2.order_no}/address",
                   params={"email": "wrong@glowmag.com"}, json=ADDR_BODY)
    check("改址：游客错 email → 404 order_not_found",
          r.status_code == 404 and r.json()["detail"] == "order_not_found", r.text)

    r = client.put(f"/api/orders/{o1.order_no}/address", headers=H_bo,
                   json=ADDR_BODY)
    check("改址：他人登录态 → 404",
          r.status_code == 404, r.text)

    r = client.put(f"/api/orders/{o3.order_no}/address", headers=H_maya,
                   json=ADDR_BODY)
    check("改址：已发货（status=3）→ 409 not_editable",
          r.status_code == 409 and r.json()["detail"] == "not_editable", r.text)

    r = client.put(f"/api/orders/{o4.order_no}/address", headers=H_maya,
                   json=ADDR_BODY)
    check("改址：已取消（status=8）→ 409 not_editable",
          r.status_code == 409 and r.json()["detail"] == "not_editable", r.text)

    r = client.put(f"/api/orders/{o5.order_no}/address", headers=H_maya,
                   json=ADDR_BODY)
    check("改址：status=2 但部分发货（shipping_status=1）→ 409 not_editable",
          r.status_code == 409 and r.json()["detail"] == "not_editable", r.text)

    bad = dict(ADDR_BODY, country="USA")
    r = client.put(f"/api/orders/{o1.order_no}/address", headers=H_maya,
                   json=bad)
    check("改址：country 超 2 位 → 422（字段宽度校验生效）",
          r.status_code == 422, r.status_code)

    r = client.put(f"/api/orders/{o1.order_no}/address", json=ADDR_BODY)
    check("改址：未登录无 email → 404（不泄露订单存在性）",
          r.status_code == 404, r.status_code)

    # ================= 3. 评价图片上传 =================
    H_up = _login_headers(client, "bo@glowmag.com", "bopass1234")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64

    r = client.post("/api/content/reviews/upload", headers=H_up,
                    files={"file": ("nails.png", png, "image/png")})
    d = r.json()
    m = re.fullmatch(r"/static/uploads/reviews/(\d{6})/([0-9a-f]{32})\.png",
                     d.get("url") or "")
    check("上传：png → 200，URL 形如 /static/uploads/reviews/{yyyymm}/{uuid4hex}.png",
          r.status_code == 200 and m is not None, d)
    if m:
        f = Path(_ROOT) / "static" / "uploads" / "reviews" / m.group(1) / (m.group(2) + ".png")
        check("上传：文件确实落盘且字节一致", f.exists() and f.read_bytes() == png)
        g = client.get(d["url"])
        check("上传：返回 URL 经静态挂载可公开访问（GET 200 + 内容一致）",
              g.status_code == 200 and g.content == png, g.status_code)

    r = client.post("/api/content/reviews/upload", headers=H_up,
                    files={"file": ("note.txt", b"hello", "text/plain")})
    check("上传：非图片类型 → 400 invalid_type",
          r.status_code == 400 and r.json()["detail"] == "invalid_type", r.text)

    r = client.post("/api/content/reviews/upload", headers=H_up,
                    files={"file": ("fake.txt", b"\x89PNG\r\n\x1a\n", "image/png")})
    check("上传：ctype=image/png 但扩展名 .txt 不符 → 400 invalid_type（双校验）",
          r.status_code == 400 and r.json()["detail"] == "invalid_type", r.text)

    big = b"x" * (5 * 1024 * 1024 + 1)
    r = client.post("/api/content/reviews/upload", headers=H_up,
                    files={"file": ("big.png", big, "image/png")})
    check("上传：>5MB → 400 too_large",
          r.status_code == 400 and r.json()["detail"] == "too_large", r.text)

    r = client.post("/api/content/reviews/upload",
                    files={"file": ("x.png", png, "image/png")})
    check("上传：未登录 → 401", r.status_code == 401, r.status_code)

    # ================= 4. OAuth（dev-login + 回调全 mock） =================
    r = client.get("/api/account/oauth/google/authorize")
    check("OAuth authorize：dev 环境 → {url:'', dev_mock:true}",
          r.status_code == 200 and r.json() == {"url": "", "dev_mock": True}, r.text)

    # 非 dev：未配置 → 409 not_configured；已配置 → 返回真实授权 URL（临时切 env，测完还原）
    _env_backup = app_settings.env
    try:
        app_settings.env = "staging"
        r = client.get("/api/account/oauth/google/authorize")
        check("OAuth authorize：非 dev 未配置 → 409 not_configured",
              r.status_code == 409 and r.json()["detail"] == "not_configured", r.text)
        os.environ["GM_GOOGLE_CLIENT_ID"] = "g-client-id"
        os.environ["GM_GOOGLE_CLIENT_SECRET"] = "g-secret"
        r = client.get("/api/account/oauth/google/authorize")
        url = r.json().get("url") or ""
        check("OAuth authorize：google URL 含 client_id/redirect_uri/scope/state",
              r.status_code == 200
              and url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
              and "client_id=g-client-id" in url
              and "redirect_uri=http%3A%2F%2Flocalhost%3A5173"
              "%2Fapi%2Faccount%2Foauth%2Fgoogle%2Fcallback" in url
              and "scope=openid+email+profile" in url
              and "state=" in url, url)
        state = url.split("state=")[-1].split("&")[0]
        check("OAuth state：HMAC 自校验（有效放行/篡改拒绝/跨 provider 拒绝）",
              service_oauth.verify_state(state, "google")
              and not service_oauth.verify_state(state + "x", "google")
              and not service_oauth.verify_state(state, "apple"))
        del os.environ["GM_GOOGLE_CLIENT_ID"]
        del os.environ["GM_GOOGLE_CLIENT_SECRET"]
    finally:
        app_settings.env = _env_backup

    before = s.query(User).count()
    r = client.post("/api/account/oauth/dev-login", json={"provider": "google"})
    d = r.json()
    s.expire_all()
    demo = s.query(User).filter(
        User.email.like("google.demo.%@glowmag.local")).first()
    check("dev-login：无 email → 创建演示账号（google.demo.*@glowmag.local）返回 {token,user}",
          r.status_code == 200 and "token" in d and "user" in d
          and demo is not None and demo.oauth_provider == "google"
          and demo.oauth_subject and demo.id == d["user"]["id"]
          and s.query(User).count() == before + 1, d)
    r_me = client.get("/api/account/me",
                      headers={"Authorization": f"Bearer {d['token']}"})
    check("dev-login：token 与 login 同机制（/me 可用）",
          r_me.status_code == 200 and r_me.json()["id"] == d["user"]["id"], r_me.text)
    welcome = [e.payload.get("email") for e in s.query(OutboxEvent)
               .filter(OutboxEvent.event_type == "user.welcome").all()]
    check("dev-login：建号复用 welcome coupon 钩子（outbox user.welcome）",
          demo.email in welcome, welcome)

    r2 = client.post("/api/account/oauth/dev-login", json={
        "provider": "google", "email": "bindme@glowmag.com", "name": "Bind Me"})
    s.expire_all()
    bound = s.query(User).filter(User.email == "bindme@glowmag.com").first()
    check("dev-login：传 email（新）→ 以该 email 建号并绑定 provider",
          r2.status_code == 200 and bound is not None
          and bound.oauth_provider == "google" and bound.oauth_subject
          and r2.json()["user"]["id"] == bound.id, r2.text)

    r3 = client.post("/api/account/oauth/dev-login", json={
        "provider": "google", "email": "bindme@glowmag.com"})
    check("dev-login：已绑定账号 → 直接登录不重复建号",
          r3.status_code == 200 and r3.json()["user"]["id"] == bound.id)

    r4 = client.post("/api/account/oauth/dev-login", json={
        "provider": "google", "email": "maya@glowmag.com"})
    s.expire_all()
    maya_db = s.query(User).filter(User.email == "maya@glowmag.com").one()
    check("dev-login：email 命中现有账号 → 绑定后登录（不建新号）",
          r4.status_code == 200 and r4.json()["user"]["id"] == maya_db.id
          and maya_db.oauth_provider == "google", r4.text)

    check("dev-login：非法 provider → 422",
          client.post("/api/account/oauth/dev-login",
                      json={"provider": "wechat"}).status_code == 422)

    # ---- google 回调（_google_exchange mock，无真实外网） ----
    os.environ["GM_GOOGLE_CLIENT_ID"] = "g-client-id"
    os.environ["GM_GOOGLE_CLIENT_SECRET"] = "g-secret"
    state = service_oauth.sign_state("google")
    _orig = service_oauth._google_exchange
    service_oauth._google_exchange = lambda cfg, code, site: {
        "sub": "g-sub-001", "email": "googleuser@gmail.com",
        "email_verified": "true", "name": "Google User",
    }
    try:
        users_before = s.query(User).count()
        r = client.get("/api/account/oauth/google/callback", follow_redirects=False,
                       params={"code": "authcode", "state": state})
        loc = r.headers.get("location", "")
        s.expire_all()
        gu = s.query(User).filter(User.email == "googleuser@gmail.com").first()
        check("google 回调：成功建号 → 302 {site}/login?oauth_token=..&email=..",
              r.status_code == 302
              and loc.startswith("http://localhost:5173/login?oauth_token=")
              and "email=googleuser%40gmail.com" in loc
              and gu is not None and gu.oauth_provider == "google"
              and gu.oauth_subject == "g-sub-001"
              and gu.name == "Google User"
              and s.query(User).count() == users_before + 1, loc)
        tok = re.search(r"oauth_token=([^&]+)", loc).group(1)
        r_me = client.get("/api/account/me",
                          headers={"Authorization": f"Bearer {tok}"})
        check("google 回调：跳转 token 可直接调用 /me",
              r_me.status_code == 200 and r_me.json()["email"] == "googleuser@gmail.com",
              r_me.text)

        # 已有账号 email 命中 + email_verified → 绑定不建号
        service_oauth._google_exchange = lambda cfg, code, site: {
            "sub": "g-sub-bo", "email": "bo@glowmag.com",
            "email_verified": True, "name": "Bo G",
        }
        r = client.get("/api/account/oauth/google/callback", follow_redirects=False,
                       params={"code": "authcode", "state": state})
        s.expire_all()
        bo_db = s.query(User).filter(User.email == "bo@glowmag.com").one()
        check("google 回调：email_verified 且 email 命中现有账号 → 绑定 provider/subject",
              bo_db.oauth_provider == "google" and bo_db.oauth_subject == "g-sub-bo")

        # email_verified=false + email 未占用 → 照常建新号
        service_oauth._google_exchange = lambda cfg, code, site: {
            "sub": "g-sub-unv", "email": "unverified@gmail.com",
            "email_verified": "false", "name": "U V",
        }
        n0 = s.query(User).count()
        r = client.get("/api/account/oauth/google/callback", follow_redirects=False,
                       params={"code": "authcode", "state": state})
        s.expire_all()
        unv = s.query(User).filter(User.email == "unverified@gmail.com").first()
        check("google 回调：email 未验证且未被占 → 仍建新号（不绑定他人账号）",
              r.status_code == 302 and unv is not None
              and s.query(User).count() == n0 + 1, r.headers.get("location"))

        # email_verified=false + email 已被占 → 拒绝（oauth_error=email_taken）
        service_oauth._google_exchange = lambda cfg, code, site: {
            "sub": "g-sub-take", "email": "maya@glowmag.com",
            "email_verified": "false", "name": "Takeover",
        }
        n0 = s.query(User).count()
        r = client.get("/api/account/oauth/google/callback", follow_redirects=False,
                       params={"code": "authcode", "state": state})
        loc3 = r.headers.get("location", "")
        s.expire_all()
        check("google 回调：未验证 email 撞已占账号 → oauth_error 且不建号不覆盖绑定",
              r.status_code == 302 and "oauth_error=email_taken" in loc3
              and s.query(User).count() == n0, loc3)

        # 篡改 state → invalid_state
        r = client.get("/api/account/oauth/google/callback", follow_redirects=False,
                       params={"code": "authcode", "state": state + "x"})
        check("google 回调：篡改 state → 302 /login?oauth_error=invalid_state",
              r.status_code == 302
              and "oauth_error=invalid_state" in r.headers.get("location", ""))
        # 缺 code
        r = client.get("/api/account/oauth/google/callback", follow_redirects=False,
                       params={"code": "", "state": state})
        check("google 回调：缺 code → 302 oauth_error=invalid_state",
              r.status_code == 302
              and "oauth_error=invalid_state" in r.headers.get("location", ""))
        # 同 sub 二次登录（命中绑定直登，不再建号）
        service_oauth._google_exchange = lambda cfg, code, site: {
            "sub": "g-sub-001", "email": "googleuser@gmail.com",
            "email_verified": "true", "name": "Google User",
        }
        n0 = s.query(User).count()
        r = client.get("/api/account/oauth/google/callback", follow_redirects=False,
                       params={"code": "authcode", "state": state})
        s.expire_all()
        check("google 回调：subject 命中已绑定账号 → 直接登录不建号",
              r.status_code == 302 and s.query(User).count() == n0
              and "oauth_token=" in r.headers.get("location", ""))
    finally:
        service_oauth._google_exchange = _orig
        del os.environ["GM_GOOGLE_CLIENT_ID"]
        del os.environ["GM_GOOGLE_CLIENT_SECRET"]

    # ---- apple 回调（_apple_exchange mock，form_post） ----
    os.environ["GM_APPLE_CLIENT_ID"] = "a-client-id"
    os.environ["GM_APPLE_TEAM_ID"] = "a-team"
    os.environ["GM_APPLE_KEY_ID"] = "a-key"
    os.environ["GM_APPLE_PRIVATE_KEY"] = "a-private-key"
    state = service_oauth.sign_state("apple")
    _orig_a = service_oauth._apple_exchange
    service_oauth._apple_exchange = lambda cfg, code, site: {
        "sub": "a-sub-001", "email": "appleuser@icloud.com",
        "email_verified": True,
        "name": {"firstName": "Apple", "lastName": "User"},
    }
    try:
        r = client.post("/api/account/oauth/apple/callback", follow_redirects=False,
                        data={"code": "authcode", "state": state})
        loc = r.headers.get("location", "")
        s.expire_all()
        au = s.query(User).filter(User.email == "appleuser@icloud.com").first()
        check("apple 回调（form_post）：成功建号（name 取 firstName+lastName）→ 302 带 token",
              r.status_code == 302
              and loc.startswith("http://localhost:5173/login?oauth_token=")
              and au is not None and au.oauth_provider == "apple"
              and au.oauth_subject == "a-sub-001" and au.name == "Apple User", loc)
        r = client.post("/api/account/oauth/apple/callback", follow_redirects=False,
                        data={"code": "authcode", "state": "bad"})
        check("apple 回调：坏 state → 302 oauth_error=invalid_state",
              r.status_code == 302
              and "oauth_error=invalid_state" in r.headers.get("location", ""))
    finally:
        service_oauth._apple_exchange = _orig_a
        for k in ("GM_APPLE_CLIENT_ID", "GM_APPLE_TEAM_ID",
                  "GM_APPLE_KEY_ID", "GM_APPLE_PRIVATE_KEY"):
            os.environ.pop(k, None)

    # 非 dev 环境 dev-login → 404
    _env_backup = app_settings.env
    try:
        app_settings.env = "prod"
        r = client.post("/api/account/oauth/dev-login", json={"provider": "google"})
        check("dev-login：非 dev 环境 → 404", r.status_code == 404, r.status_code)
        r = client.get("/api/account/oauth/google/authorize")
        check("authorize：非 dev 且未配置 → 409 not_configured",
              r.status_code == 409, r.status_code)
    finally:
        app_settings.env = _env_backup

    s.close()

# 清理上传产物与测试库（reviews 上传目录为本特性专属子目录，整删安全）
import shutil

_reviews_root = Path(_ROOT) / "static" / "uploads" / "reviews"
if _reviews_root.exists():
    shutil.rmtree(_reviews_root, ignore_errors=True)

from app.core.db import engine as _engine

_engine.dispose()
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)

print(f"\n{PASSED} passed, {len(FAILED)} failed")
if FAILED:
    print("failed:", FAILED)
    sys.exit(1)
