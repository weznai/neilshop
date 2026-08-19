# GLOWMAG 后端服务（FastAPI 单体 + MySQL 8）

按《微服务演进架构设计-v3》"按域分包铺路"原则组织：**8 个域包对齐未来微服务拆分蓝图**，域内四层分离。

## 目录结构

```
app/
  main.py              # 仅组装：中间件 + 路由注册（零业务）
  core/                # 横切关注点：config/db/security/deps/enums/observability
  models/              # ORM 模型（51 表，按 11 个数据域分文件，数据层底座）
  services/            # 跨域公共服务：pricing/points/promo_rules/emails/payment_provider
  domains/             # ★ 业务域（对齐微服务蓝图八域，拆分=把域包变进程）
    trade/             # 交易：cart/checkout/orders/payments/returns + 后台履约
    member/            # 会员：account/points/referrals/subscriptions
    catalog/           # 商品：目录/搜索 + 后台商品管理
    promo/             # 营销：折扣码/礼品卡/弹窗 + 后台营销
    content/           # 内容：FAQ/博客/评价/UGC + 后台审核
    support/           # 客服：工单 + 后台工作台
    ops/               # 运营：看板/会员管理/审计日志
    ai/                # AI：推荐/客服 Agent
  （routers/ shim 层已于 v0.2 裁撤，main.py 直连 domains）
```

**域内四层**（每个域包一致）：
- `router*.py` 薄 HTTP 层——校验/鉴权(Depends)/调 service/组装响应，**禁止 ORM**
- `service*.py` 业务层——逻辑与事务（HTTPException 兼容保留）
- `repository.py` 数据访问——纯查询/SQL，**禁止业务分支与 HTTP 概念**
- `schemas.py` DTO——Pydantic 模型

**纪律**：跨域只走 service（或 app.services），禁止摸他人 repository；models 集中共享。

## 运行

```powershell
cd server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe scripts\seed.py     # 建表 + 种子（首次）
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
```

- API 文档: http://localhost:8000/docs
- 原型前台: http://localhost:8000/ （静态站 ../web/client）
- 环境变量: `GM_DB`（默认 mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag?charset=utf8mb4）、`GM_JWT_SECRET`
- 种子账号: admin/ops/cs/emma @glowmag.com，密码 `glowmag123`；演示订单 NS260728D4E5F6（$31.10）

## 测试

```powershell
.venv\Scripts\python.exe scripts\test_a.py   # 20 用例
.venv\Scripts\python.exe scripts\test_b.py   # 56 用例（交易全链路）
.venv\Scripts\python.exe scripts\test_c.py   # 78 用例
.venv\Scripts\python.exe scripts\test_worker.py  # 27 用例（worker/邮件/对账）
```
（各脚本自建 glowmag_test_a/b/c/w 库，需本机 MySQL 及 glowmag 用户）

**数据库迁移（Alembic，只前向）**

```powershell
$env:GM_DB='mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag?charset=utf8mb4'
.venv\Scripts\python.exe -m alembic upgrade head                          # 应用迁移
.venv\Scripts\python.exe -m alembic revision --autogenerate -m "desc"     # 模型变更→新迁移
```

**后台任务 worker（独立进程，GET_LOCK 单实例）**

```powershell
.venv\Scripts\python.exe scripts\worker.py --once            # outbox消费/超时关单/弃购/积分过期/每日对账
.venv\Scripts\python.exe scripts\worker.py --loop --interval 60
```

**AI 服务**：`GET /api/ai/recommend|hot`、`POST /api/ai/chat`（GlowBot 前端已接，超时自动回落本地应答）

## 约定

- 金额一律**美分 int**；rating 库内 ×100（487=4.87）
- 时间一律 **naive UTC 秒级**（core/db.utcnow —— MySQL DATETIME 四舍五入会造出"未来时间"，禁止 aware 混比）
- 枚举一律 SmallInteger，取值见 `app/core/enums.py`（与数据库文档注释一一对应）
- 鉴权: `Authorization: Bearer <jwt>`；游客购物车: `X-Cart-Token`（首次响应头返回）
- 后台接口统一 `/api/admin/*`，需 role >= 2；role: 0顾客 1客服 2运营 3仓库 9超管
- 折扣码校验只许走 `services/promo_rules.validate_code`；积分账务只许走 `services/points`；定价只许走 `services/pricing.price_cart`
- **分层**：router 禁 ORM；repository 禁业务/HTTP；跨域只走 service；新端点进对应 domains/*（routers/ 仅 shim）
- 演进: 域包即未来微服务 → 拆分=把 app/domains/<域> 变进程，接口不变
