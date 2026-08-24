"""支付通道配置（settings key=payment_config）回归 —— 后台配置 > 环境变量，保存热生效。
覆盖：
- resolve_pay_config：env 兜底 / DB 覆盖 / DB 空串回落 env / DB 异常静默回退
- get_provider 缓存签名失效：保存 DB 配置后不重启即切换（stripe > paypal > mock 链）
- GET /api/admin/trade/payments/config：掩码回显 + source 标记 + package 探测 + webhook_url
- PUT：字段级保存 / 前缀校验 422 / 空串清除回落 env / 普通管理员 403（仅超管）
- POST /payments/test：stripe 伪包连通（Balance 外呼）/ 未配置给原因 / mock 默认链拒绝
- webhook 门禁走 provider 生效配置（DB 配 secret 后非 dev 通过门禁）
- 通用 settings 列表 payment_config 脱敏（stripe_key/paypal_secret 掩码）"""

import os
import sys
import types
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_ROOT, "test_paycfg.sqlite").replace("\\", "/")
for _suffix in ("", "-wal", "-shm"):
    _p = _DB + _suffix
    if os.path.exists(_p):
        os.remove(_p)
os.environ["GM_DB"] = f"sqlite:///{_DB}"
os.environ["GM_COOKIE_AUTH"] = "0"
sys.path.insert(0, _ROOT)

from app.core.config import settings as app_settings  # noqa: E402

if app_settings.db_url.startswith("sqlite"):
    from sqlalchemy import BigInteger
    from sqlalchemy.ext.compiler import compiles

    @compiles(BigInteger, "sqlite")
    def _bigint_as_integer(type_, compiler, **kw):
        return "INTEGER"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import create_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Setting, User  # noqa: E402
from app.services import payment_provider as pp  # noqa: E402

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


def build_fake_stripe():
    calls = []
    state = {"balance": SimpleNamespace(available=[{"amount": 12345, "currency": "usd"}])}

    class FakeBalance:
        @classmethod
        def retrieve(cls):
            calls.append("balance")
            if isinstance(state["balance"], Exception):
                raise state["balance"]
            return state["balance"]

    stripe = types.ModuleType("stripe")
    stripe.Balance = FakeBalance
    stripe.api_key = ""
    return stripe, calls, state


fake_stripe, stripe_calls, stripe_state = build_fake_stripe()

try:
    with TestClient(app) as client:
        s = SessionLocal()

        ops = User(email="ops@glow.test", password_hash=hash_password("x"),
                   name="Ops", role=2, points=0)
        root = User(email="root@glow.test", password_hash=hash_password("x"),
                    name="Root", role=9, points=0)
        s.add_all([ops, root])
        s.commit()
        ops_tok = {"Authorization": f"Bearer {create_token(ops.id, 2)}"}
        root_tok = {"Authorization": f"Bearer {create_token(root.id, 9)}"}

        # ===== resolve_pay_config：env 兜底 / DB 覆盖 / DB 空串回落 env =====
        pp.reset_provider_cache()
        cfg_env = pp.resolve_pay_config(s)
        check("resolve: env 兜底（无 DB 行）", cfg_env["stripe_key"] == ""
              and cfg_env["paypal_base"] == "https://api-m.sandbox.paypal.com"
              and cfg_env["stripe_klarna"] is False, cfg_env)

        s.add(Setting(key="payment_config", value={
            "stripe_key": "sk_test_dbkey123456", "stripe_klarna": True,
            "paypal_client_id": "",  # 空串不入库语义，但 resolve 侧等价：跳过回落 env
        }, updated_by=root.id))
        s.commit()
        cfg_db = pp.resolve_pay_config(s)
        check("resolve: DB 覆盖 stripe_key/klarna，paypal 空回落 env",
              cfg_db["stripe_key"] == "sk_test_dbkey123456"
              and cfg_db["stripe_klarna"] is True
              and cfg_db["paypal_client_id"] == "", cfg_db)

        # DB 故障静默回退：传一个坏 session（无 get 属性的对象会抛 → 被 except 吞）
        class _BadDB:
            def get(self, *a, **k):
                raise RuntimeError("db down")
        cfg_bad = pp.resolve_pay_config(_BadDB())
        check("resolve: DB 异常静默回退 env", cfg_bad["stripe_key"] == "", cfg_bad)

        # ===== get_provider 缓存签名失效：DB 配置热切换 =====
        sys.modules.pop("stripe", None)
        pp.reset_provider_cache()
        check("provider: 仅 DB stripe_key 无包 → mock 降级",
              pp.get_provider(s).name == "mock")

        sys.modules["stripe"] = fake_stripe
        pp.reset_provider_cache()
        p = pp.get_provider(s)
        check("provider: 装包后同配置 → StripeProvider（DB 密钥）",
              p.name == "stripe" and p.key == "sk_test_dbkey123456"
              and p.webhook_gate_secret() == "", (p.name, getattr(p, "key", None)))

        # DB 行再改 key → 不 reset 缓存也应切换（指纹失效）
        row = s.get(Setting, "payment_config")
        row.value = dict(row.value, stripe_key="sk_live_dbkey7890")
        s.commit()
        p2 = pp.get_provider(s)
        check("provider: DB 改 key 后缓存指纹失效自动重建（无需重启/手动 reset）",
              p2.name == "stripe" and p2.key == "sk_live_dbkey7890", getattr(p2, "key", None))

        # 清空 DB 行 → 回落 env（无 key）→ mock
        row = s.get(Setting, "payment_config")
        row.value = {}
        s.commit()
        check("provider: DB 清空回落 env → mock", pp.get_provider(s).name == "mock")

        # ===== GET /payments/config：掩码 + source + webhook_url =====
        row.value = {"stripe_key": "sk_test_dbkey123456", "stripe_webhook_secret": "whsec_dbsec123456",
                     "paypal_client_id": "pid-db-123", "paypal_secret": "pp-secret-db-999",
                     "paypal_base": "https://api-m.paypal.com", "paypal_webhook_id": "WHIDDB123",
                     "stripe_klarna": True}
        s.commit()
        pp.reset_provider_cache()
        r = client.get("/api/admin/trade/payments/config", headers=ops_tok)
        d = r.json()
        check("GET 200（普通管理员可读）", r.status_code == 200, r.text)
        check("GET stripe 掩码 + mode=test + source=db",
              d["stripe"]["key_set"] is True
              and d["stripe"]["key_masked"] == "sk_***3456"
              and d["stripe"]["key_mode"] == "test"
              and d["stripe"]["source"] == "db"
              and d["stripe"]["webhook_secret_masked"] == "whs***3456"
              and d["stripe"]["klarna"] is True, d.get("stripe"))
        check("GET paypal 明文仅 client_id，secret/webhook_id 掩码 + live base",
              d["paypal"]["client_id"] == "pid-db-123"
              and d["paypal"]["secret_masked"] == "pp-***-999"
              and d["paypal"]["webhook_id_masked"] == "WHI***B123"
              and d["paypal"]["base"] == "https://api-m.paypal.com", d.get("paypal"))
        check("GET package/effective（站点未配置时 webhook_url 为空串）",
              d["package"]["stripe"] is True
              and d["effective"]["provider"] == "stripe"
              and "stripe(klarna)" in d["effective"]["available"]
              and d["effective"]["webhook_url"] == "", d.get("effective"))
        check("GET 响应无任何明文密钥", "sk_test_dbkey123456" not in r.text
              and "pp-secret-db-999" not in r.text and "whsec_dbsec123456" not in r.text)

        # 未配置站点时 webhook_url 为空
        check("webhook_url 站点未配置 → 空", d["effective"]["webhook_url"] == ""
              or d["effective"]["webhook_url"].startswith("http"), d["effective"]["webhook_url"])
        s.add(Setting(key="site_url", value="https://shop.glowmag.example"))
        s.commit()
        d2 = client.get("/api/admin/trade/payments/config", headers=root_tok).json()
        check("webhook_url 站点配置后拼接",
              d2["effective"]["webhook_url"] == "https://shop.glowmag.example/api/payments/webhook",
              d2["effective"]["webhook_url"])

        # ===== PUT：保存/校验/权限 =====
        r = client.put("/api/admin/trade/payments/config", headers=ops_tok,
                       json={"stripe_key": "sk_test_x"})
        check("PUT 普通管理员 → 403 superadmin required",
              r.status_code == 403 and r.json()["detail"] == "superadmin required", r.text)

        r = client.put("/api/admin/trade/payments/config", headers=root_tok,
                       json={"stripe_key": "rk_bad_prefix"})
        check("PUT 非法前缀密钥 → 422", r.status_code == 422, r.text)
        r = client.put("/api/admin/trade/payments/config", headers=root_tok,
                       json={"stripe_webhook_secret": "nope"})
        check("PUT 非法 whsec 前缀 → 422", r.status_code == 422, r.text)
        r = client.put("/api/admin/trade/payments/config", headers=root_tok,
                       json={"stripe_klarna": "yes"})
        check("PUT klarna 非布尔 → 422", r.status_code == 422, r.text)

        r = client.put("/api/admin/trade/payments/config", headers=root_tok,
                       json={"paypal_base": "https://api-m.sandbox.paypal.com"})
        check("PUT 合法保存 → 200 + 回显生效配置",
              r.status_code == 200 and r.json()["paypal"]["base"] == "https://api-m.sandbox.paypal.com",
              r.text[:200])

        # 空串清除 = 回落 env（DB 删字段）
        r = client.put("/api/admin/trade/payments/config", headers=root_tok,
                       json={"paypal_secret": ""})
        d = r.json()
        s.expire_all()   # 测试会话身份映射缓存了旧行，失效后重读
        row = s.get(Setting, "payment_config")
        check("PUT 空串清除 → DB 字段删除 + paypal 降级（半凭据）",
              r.status_code == 200 and "paypal_secret" not in row.value
              and "paypal" not in d["effective"]["available"], (row.value, d["effective"]))

        # ===== POST /payments/test =====
        pp.reset_provider_cache()
        r = client.post("/api/admin/trade/payments/test", headers=ops_tok,
                        json={"provider": "stripe"})
        d = r.json()
        check("test stripe 伪包 → ok + test 模式 + 余额",
              d.get("ok") is True and d.get("mode") == "test"
              and d.get("balance_cents") == 12345 and stripe_calls, d)

        stripe_state["balance"] = RuntimeError("invalid_api_key")
        r = client.post("/api/admin/trade/payments/test", headers=root_tok,
                        json={"provider": "stripe"})
        d = r.json()
        check("test stripe 失败 → ok=False + 原因片段",
              d.get("ok") is False and "invalid_api_key" in d.get("reason", ""), d)

        r = client.post("/api/admin/trade/payments/test", headers=root_tok,
                        json={"provider": "paypal"})
        d = r.json()
        check("test paypal 半凭据 → 明确原因",
              d.get("ok") is False and "不完整" in d.get("reason", ""), d)

        # ===== webhook 门禁走 provider 生效配置（非 dev + DB secret） =====
        client.put("/api/admin/trade/payments/config", headers=root_tok,
                   json={"paypal_secret": "", "stripe_webhook_secret": "whsec_dbsec123456"})
        app_settings.env = "prod"
        try:
            pp.reset_provider_cache()
            prov = pp.get_provider(s)
            check("webhook 门禁：stripe + DB whsec → 通过",
                  prov.webhook_gate_secret() == "whsec_dbsec123456")

            row = s.get(Setting, "payment_config")
            row.value = {k: v for k, v in row.value.items() if k != "stripe_webhook_secret"}
            s.commit()
            pp.reset_provider_cache()
            r = client.post("/api/payments/webhook",
                            json={"id": "evt_gate_1", "type": "t", "data": {}})
            check("webhook 门禁：非 dev 无验签密钥 → 400 webhook_secret_not_configured",
                  r.status_code == 400 and r.json()["detail"] == "webhook_secret_not_configured",
                  r.text)
        finally:
            app_settings.env = "dev"

        # ===== 通用 settings 列表脱敏 =====
        client.put("/api/admin/trade/payments/config", headers=root_tok,
                   json={"stripe_key": "sk_test_dbkey123456", "paypal_secret": "pp-secret-db-999"})
        r = client.get("/api/admin/ops/settings", headers=root_tok)
        body = r.text
        pc = next((i["value"] for i in r.json()["items"] if i["key"] == "payment_config"), None)
        check("settings 列表 payment_config 脱敏",
              pc is not None and pc.get("stripe_key") == "sk_***3456"
              and pc.get("paypal_secret") == "pp-***-999"
              and "sk_test_dbkey123456" not in body and "pp-secret-db-999" not in body, pc)

        # ===== methods 端点 klarna 标记来自生效配置（DB） =====
        pp.reset_provider_cache()
        r = client.get("/api/payments/methods")
        d = r.json()
        check("methods: DB klarna=true → stripe 节点 klarna=true",
              any(p["id"] == "stripe" and p["klarna"] for p in d["providers"]), d)

        s.close()
finally:
    sys.modules.pop("stripe", None)
    app_settings.env = "dev"
    pp._provider = None
    pp._provider_sig = None

print(f"\n==== test_paycfg: {PASSED} passed, {len(FAILED)} failed ====")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
