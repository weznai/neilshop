# GLOWMAG MVP 实现说明（FastAPI + MySQL 版）

> 对应《高可用架构设计-v2》《微服务演进架构设计-v3》《数据库设计文档-完整版》的**可运行落地版**。
> 本文档记录技术栈落地决策、模块与设计文档的映射关系、API 契约总表与运行手册。

---

## 1. 技术栈落地决策（相对原设计的调整与理由）

| 原设计 | 落地版 | 理由 |
|---|---|---|
| Next.js 前端 + Spring Boot 3 主服务 + FastAPI AI 服务 | **FastAPI 单体（Python 3.13）** + 原型静态挂载 | 开发机仅 Java 8（Spring Boot 3 需 17）；遵循 v3 文档"今天不建微服务、按域分包铺路"原则，模块边界=未来微服务边界 |
| MySQL 8 主从 + Redis 哨兵 + Meilisearch + Qdrant | **MySQL 8.0.22 单实例**（glowmag 库） | MVP 阶段够用；连接池 pre_ping + 3600s 回收；全部组件无 Redis 依赖，购物车落 DB（对齐文档 carts 镜像表设计，加 Redis 是优化不是改结构） |
| Stripe/Klaviyo/Shippo 真实对接 | **mock-pay / webhook 模拟 / outbox_events 落库** | 支付状态机、幂等、退款、对账链路全部真实实现，只把"调第三方"换成"调模拟端点"，接真 Stripe 时只改 payments 路由内层 |
| JWT + Redis session | **JWT（PyJWT HS256）+ DB** | 无状态目标一致；游客购物车用 `X-Cart-Token` |
| 金额 DECIMAL(10,2) | **美分 int** | 消除浮点误差；切 DECIMAL 只需改列类型，代码零改动（全部整型运算） |
| DATETIME(3) UTC | **DATETIME(0) + naive UTC 秒级截断** | MySQL DATETIME 四舍五入会把 .6s 进位成"未来时间"翻转生效判断（实测踩坑），统一 floor 到秒保证写读对称 |

**模型覆盖**：11 域 51 表全部落 SQLAlchemy 模型（`server/app/models/`），列名/索引/枚举与《数据库设计文档-完整版》逐列对齐；`MEDIUMTEXT` 以 `Text().with_variant(MEDIUMTEXT(), "mysql")` 表达，SQLite 兼容（测试用）。

---

## 2. 模块 ↔ 微服务蓝图映射

```
app/routers/            ← 未来微服务（v3 文档 §2 八域蓝图）
  account.py            → member-svc（注册/登录/地址簿/愿望单/订阅/GDPR consent）
  catalog.py            → product-svc（商品/分类/集合/搜索/评价读）
  cart.py               → trade-svc 入口（游客 token 车 + 登录合并）
  checkout.py           → trade-svc（定价引擎在此）
  orders.py             → trade-svc（我的订单/取消/物流轨迹）
  payments.py           → trade-svc（支付意图/模拟支付/webhook 幂等）
  returns.py            → trade-svc（RMA 用户侧）
  promo.py              → promo-svc（折扣码校验/礼品卡/弹窗）
  points.py             → member-svc（积分三视图）
  content.py            → content-svc（FAQ/博客/评价提交/UGC）
  support.py            → notify/客服（工单用户侧）
  admin_catalog.py      → product-svc 后台
  admin_trade.py        → trade-svc 后台（发货/退款/RMA 状态机/库存）
  admin_ops.py          → promo/content/member 后台 + dashboard

app/services/
  pricing.py            → 定价引擎（折扣码/捆绑/积分/礼品卡/运费/税，纯函数可测）
  points.py             → 积分账务唯一真相（流水驱动余额）
  promo_rules.py        → 折扣码校验唯一闸门（路由不得复制实现）
```

模块间纪律与 v3 §3 一致：**跨域只走 service 函数，禁止跨模块直查他人表**。

---

## 3. 核心业务规则（与 prototype 原型 13 轮对齐的口径）

- **免邮** ≥ $35（3500 美分），否则 standard $4.99 / express $14.99；免邮码 FREESHIP
- **税率** settings.tax_rate = 0.0735，基数 = subtotal − 折扣码 − 捆绑 − 积分 − 礼品卡 + 运费，四舍五入到分
- **折扣码**：WELCOME20 = 20% 封顶 $10 首单限一次；EARLYBIRD = 25%；BYE2025 = 25% 封顶 $15；百分比取整四舍五入（2998×20% → 600，对齐原型 $6.00）
- **捆绑**（press-on 品类）：任 2 件 85 折 / 任 3 件 8 折，自动生效，独立于折扣码
- **积分**：$1 = 10 分；100 分 = $1 抵扣；下单获得先冻结（frozen=1，退货期 30 天后解冻）；退款作废未解冻积分
- **标准验证订单** `NS260728D4E5F6`：Bare Gems $15.99 + Cherry Bomb $13.99 − WELCOME20 $6.00 + 运费 $4.99 + 税 $2.13 = **$31.10**，311 积分冻结（seed 内置，前后台四页对齐）
- **库存**：place 预扣（乐观锁 version + stock>=qty，失败整单回滚 409）→ 支付成功实扣确认 → 取消释放 → 退货收货回补；全部动作写 `stock_movements` 流水（唯一真相）
- **RMA 状态机**：申请(0)→批准/发标签(2)→在途(3)→收货(4，回补库存)→退款(5，质量问题 reason 2/4/5 加退运费 $4.99)；拒绝(6)/部分退款(7)

---

## 4. API 总表（15 模块 90+ 端点，Swagger：/docs）

| 模块 | 端点（摘要） |
|---|---|
| account | register / login / me(GET,PUT) / addresses CRUD / wishlist / newsletter / consent |
| catalog | products(列表/详情/搜索) / categories / collections / reviews |
| cart | GET / items POST·PUT·DELETE / merge（游客 token 合并） |
| checkout | preview（全分项试算）/ place（建单+预扣+用分+清车） |
| orders | 列表 / 详情 / cancel / track |
| payments | create-intent / mock-pay / webhook（event_id 幂等） |
| returns | RMA 申请 / 列表 / 详情 |
| promo | validate / giftcard / popup |
| points | balance / ledger / expiring |
| content | faqs / articles / reviews(提交+列表) / ugc |
| support | tickets(创建/列表/留言) / templates |
| admin/catalog | 商品/变体/分类/集合 CRUD + 上下架（admin_logs 全记录） |
| admin/trade | 订单列表详情 / ship / mark-delivered / refund / RMA 状态机 / stock adjust·movements·low |
| admin/ops | dashboard / discounts / popups / settings / reviews 审核 / ugc 审核 / tickets 工作台 / members / logs |

鉴权：`Authorization: Bearer <jwt>`；后台 `role ≥ 2`；游客购物车 `X-Cart-Token`。

---

## 5. 运行手册

```powershell
# 1) MySQL（本机服务 MySQL80，glowmag/glowmag123 用户，库 glowmag 已建）
#    首次建库建用户见 server/scripts/seed.py 头注（或手工执行 CREATE DATABASE glowmag CHARACTER SET utf8mb4）

# 2) 依赖
cd server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # 国内加速: -i https://mirrors.aliyun.com/pypi/simple/

# 3) 种子数据（建表 create_all + 灌入原型基线数据）
.venv\Scripts\python.exe scripts\seed.py

# 4) 启动
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
#    API 文档  http://localhost:8000/docs
#    原型前台  http://localhost:8000/   （../prototype 静态挂载）
```

**种子账号**（密码统一 `glowmag123`）：

| 邮箱 | 角色 |
|---|---|
| admin@glowmag.com | 超管(9) |
| ops@glowmag.com | 运营(2) |
| cs@glowmag.com | 客服(1) |
| emma@glowmag.com | 顾客（含 611 积分 + 演示订单） |

**测试**（各自 DROP/CREATE 独立 MySQL 测试库）：

```powershell
.venv\Scripts\python.exe scripts\test_a.py   # 20/20 账户/目录/购物车/后台目录
.venv\Scripts\python.exe scripts\test_b.py   # 56/56 交易全链路（含 $31.10 数值断言）
.venv\Scripts\python.exe scripts\test_c.py   # 78/78 营销/内容/客服/运营后台
```

环境变量：`GM_DB`（默认 mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag?charset=utf8mb4）、`GM_JWT_SECRET`、`GM_ENV`。

---

## 6. MySQL 落地踩坑实录（已修复，写入预防再犯）

1. **VARCHAR 无长度**：`Column(String)` 在 SQLite 静默通过、MySQL 建表报 CompileError → 长文本一律 `Text`（product.description_md 用 `Text().with_variant(MEDIUMTEXT(), "mysql")`）
2. **DATETIME 四舍五入**：utcnow() 微秒 .6 → MySQL 进位成未来 1 秒 → 折扣码 `not_started` 误判 → `utcnow()` 全局 floor 到秒
3. **REPEATABLE READ 快照**：测试会话长事务读不到 TestClient 请求内已提交数据（SQLite 无此现象）→ engine `isolation_level="READ COMMITTED"`（电商读已提交亦是常规选择）
4. **BigInteger 主键**：SQLite BIGINT PRIMARY KEY 不自增（测试垫片 @compiles 仅 sqlite 生效）；MySQL 原生正常
5. **aware/naive 混比**：MySQL DATETIME 读回 naive，与 aware `utcnow()` 比较抛 TypeError → 全系统统一 naive UTC

---

## 7. 已知简化与演进路径

| 简化点 | 演进动作（按设计文档） |
|---|---|
| mock-pay 模拟支付 | 接 Stripe：payments.py 内层换 SDK，webhook 验签 + webhook_events 幂等已就位 |
| 邮件/通知不发送 | outbox_events 已落 `order.paid/order.refunded`，接 Resend/Klaviyo = 加一个 outbox 消费器 |
| 弃购扫描无定时任务 | carts.abandoned_mails_sent/recovery_token 字段已建，加 APScheduler/Celery beat 扫描 |
| 搜索 LIKE | 量级上来切 Meilisearch（catalog.search 单点替换） |
| create_all 建表 | 切 Alembic 前向迁移（只前向纪律，对应文档 §12） |
| 单实例 MySQL | 加从库 + 读写分离；资金相关（库存扣减/支付状态）**强制读主**（文档 §2.3） |
| AI 服务未部署 | P2 再上 FastAPI 独立进程（推荐/客服 Agent），Java 侧接口契约不变 |

**下一步建议**（优先级）：① ~~checkout 与 prototype 前端 JS 真联通~~ ✅ 已完成（见 §8）→ ② Alembic 迁移接管建表 → ③ Stripe 沙箱替换 mock-pay → ④ 弃购定时任务 + 邮件模板。

---

## 8. 前后端真联通（已完成）

**架构**：`prototype/assets/api.js` 双模式桥接层（49 页自动加载）——
- 启动探测 `/api/health`（1.5s）：API 可达 → `mode='api'`（本地优先：G 购物车照常写 localStorage 驱动现有 UI，`save()` 防抖 800ms 全量对账到服务端；JWT 存 `gm_token`，游客车 token 存 `gm_cart_token`）；不可达 → `mode='local'`（file:// 纯静态演示，13 轮原型行为零变化）
- 页面接线挂在 `gm:apiready` 事件 / `GM_API.ready` 轮询守卫内，local 分支代码路径不动

**已联通页面（17）**：checkout（preview 实时计价 + place→intent→mock-pay→success 跳转）、success/track（真实订单/轨迹）、cart（同步徽标）、store/product（API 价格/库存/变体/售罄态刷新 + 变体级加购）、login/register/account/account-orders（JWT + 积分三视图 + 订单列表）、admin-login + 后台 7 页（看板/订单含发货/商品含上下架/库存含手工调整/退货状态机/工单回复关单/会员画像）；admin-marketing/content/settings 三页保留演示数据（已加横幅标注）。

**联通踩坑**（已修）：
1. app.js 顶层 `const G` 不挂 window → api.js 用 `typeof G !== 'undefined'` 探测（`window.G` 永远 undefined 的坑）
2. FastAPI `@router.get("/")` 在静态挂载 `/` 之下，无尾斜杠 `/api/cart` 404 → cart.py 补 `@router.get("")` 双路由（orders/points 同款写法）
3. GM_CATALOG 本地 id 1-12 与 seed.py CATALOG 顺序严格对齐 —— 变体映射懒加载详情缓存 `gm_varmap`

**演示路径**：`cd server && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000` → 打开 http://localhost:8000/（前台）/ http://localhost:8000/admin-login.html（后台，ops@glowmag.com / glowmag123）。

**回归保障**：后端 154/154（MySQL 三库）；前端 verify.ps1 通过 + 智能体 jsdom 双模式联测 125 项（API 81 + local 44）全绿。

---

## 9. 第二批演进（已完成）

### 9.1 Alembic 迁移接管建表
- `migrations/`（env.py 挂 Base.metadata + GM_DB 环境变量优先）；初始版本 `7bab2b9ff482 init 51 tables` 已在空库验证 `upgrade head` 建出全部表；现有 glowmag 库已 `stamp head`
- 命令：`$env:GM_DB=...; python -m alembic revision --autogenerate -m "desc"` / `upgrade head`；**纪律**：只前向，模型改动必须伴随迁移（对应文档 §12）

### 9.2 后台任务 worker（scripts/worker.py）
独立进程（应用保持无状态），MySQL `GET_LOCK('glowmag_worker')` 防多实例；`--once` 单轮 / `--loop --interval 60`：

| 任务 | 触发 | 动作 |
|---|---|---|
| outbox 消费 | published=0 retry<5 | 6 类邮件渲染投递（MVP 日志，接 Resend 只改 emails.deliver）→ published=1 |
| 超时关单 | PENDING>30min（settings.order_timeout_minutes 可配） | 取消+库存 RELEASE 回补+timeline+outbox(order.canceled) |
| 弃购扫描 | 车 1h 未动+有货+有邮箱 | recovery_token+邮件（**EmailPreference 退订合规跳过**） |
| 积分过期 | expires_at<now | 按用户汇总扣减+EXPIRE 流水+置 NULL 防重 |
| 每日对账 | 当日无行 | payments vs orders、points 余额 vs 流水 → reconciliation_daily（不平置 status=1 告警） |

邮件模板 6 个（app/services/emails.py，Jinja2 内联）：order_paid/shipped/refunded、abandoned_cart、welcome_coupon、restock_notify。

### 9.3 AI 服务模块（app/routers/ai.py）
- `GET /api/ai/recommend?product_id=|cart_ids=`：同类相关→标签命中→热销兜底→新上架兜底（四级降级对齐文档"AI挂→热销榜"），reason 标来源
- `GET /api/ai/hot`：热销榜（前端"猜你喜欢"兜底接口）
- `POST /api/ai/chat`：中英意图识别（order/size/wear/shipping/return/care/points/account/code/recommend/human）；FAQ 从 DB 检索；订单查询脱敏（单号只回后 4 位）；未命中→转人工（fallback）
- **GlowBot 联通**（chrome.js 仅动应答函数）：api 模式 → /api/ai/chat，2s 超时/失败 → 回落本地关键词表（降级矩阵落地）；local 模式零变化

### 9.4 后台最后 3 页接线（17+3 页全联通）
- admin-marketing：折扣码 CRUD+启停、弹窗配置 CRUD+转化率
- admin-content：评价审核（通过/驳回）、FAQ CRUD、博客 CRUD（草稿/发布）、UGC 审核（采用发 100 积分）——后端补 articles/faqs CRUD 端点（admin_ops.py，8 端点）
- admin-settings：settings 6 键真实读写（免邮/税率/运费/退货窗/积分），未接键组标"演示"

### 9.5 回归总账
后端 **181/181**（A 20 + B 56 + C 78 + worker 27，全 MySQL）；前端 verify.ps1 通过；实库冒烟：recommend/chat（中英）/hot/worker --once 对账 diff=0。

**下一步**（按文档优先级）：① ~~Stripe 沙箱~~ ✅ Provider 就绪层已完成（见 §10）② ~~弃购三封~~ ✅ ③ ~~Compose 部署~~ ✅ ④ K8s/3 台拓扑（§7.2，流量到时）⑤ AI 语义搜索（Qdrant，P3）。

---

## 10. 第三批演进（已完成）

### 10.1 Stripe 就绪支付层（services/payment_provider.py）
- **Provider 抽象**：MockProvider（默认，行为与原 mock-pay 完全一致）/ StripeProvider（真实 SDK）；`get_provider()` 单例——`GM_STRIPE_KEY` 非空且 stripe 包可导入 → Stripe，否则 Mock + 一次性告警
- StripeProvider：`PaymentIntent.create(amount, metadata.order_no, idempotency_key=order_no)`；webhook 走 `Webhook.construct_event` 验签（失败 400 invalid_signature）+ 本店事件校验
- **开启方式**：`GM_STRIPE_KEY` + `GM_STRIPE_WEBHOOK_SECRET` 环境变量 + `pip install stripe`——代码零改动；stripe 模式下 mock-pay 端点 409（真实支付由 webhook 驱动）
- 端点签名/响应结构不变 → test_b 56/56 回归红线保持；新增 test_payments 25/25（mock 链路/provider 选择与降级/验签分支）

### 10.2 弃购三封阶梯序列（worker.scan_abandoned_carts）
| 阶段 | 触发 | 折扣码 | 主题 |
|---|---|---|---|
| 1 | 1h 未动 | ABANDON10（9 折） | Still thinking about your GLOWMAG cart? |
| 2 | 24h 未动 | ABANDON15（85 折） | 15% off your favorites |
| 3 | 72h 未动 | 无码 + 最小库存紧迫感 | Last call: your cart items are almost gone |

- `abandoned_mails_sent` 兼作阶段号，CAS 原子推进（WHERE 旧值判 rowcount）；每阶段独立 recovery_token（归因）；用户回访自然重置计时（updated_at 锚定）；退订/关闭偏好用户全序列合规跳过；worker 测试 37/37

### 10.3 容器化部署（方案零落地，仓库根）
- `server/Dockerfile`（python:3.13-slim、非 root、层缓存、HEALTHCHECK、uvicorn 2 workers；prototype 进镜像）
- `docker-compose.yml`：mysql:8.0（utf8mb4、3306 不出宿主、mysqladmin healthcheck）+ api（127.0.0.1:8000，密钥强校验 `${VAR:?}`）+ worker（--loop）+ migrate（profile=deploy 一次性 alembic）；512m 资源限幅
- `.env.example` / `scripts/backup.ps1`（mysqldump+gzip+14 天保留+异地提醒，-WhatIf）/ `deploy.md`（首次部署 8 步、Cloudflare 接入、备份与季度恢复演练、→3 台迁 K8s 路径、故障手册）
- 本机无 Docker：YAML/LF/语法级验证通过，首次上线按 deploy.md §2 八步执行

### 10.4 回归总账
后端 **216/216**（A 20 + B 56 + C 78 + worker 37 + payments 25，全 MySQL 除 payments 为 sqlite 单元）；前端 verify.ps1 通过；requirements.txt 补 pymysql/cryptography/alembic。

---

## 11. 第四批演进（已完成）

### 11.1 账户侧缺口端点（10 个）
| 端点 | 说明 |
|---|---|
| GET /api/referrals/me · POST /simulate-invite | 推荐码确定性派生（GLOW-sha256[:8]）；邀请列表脱敏 + stats；on_order_paid 钩子（payments 已挂）自动发双份 1000 分、防自邀 |
| GET/POST /api/subscriptions/* | 订阅盒 MVP 全状态机（active/pause/resume 续期/skip/cancel），计划口径对齐 subscribe.html（4/6/8 周 = $12.99/13.99/14.99） |
| POST /api/account/unsubscribe | HMAC token 校验（宽限模式 + warning）；EmailPreference 全退 |
| POST /api/account/password-reset/request·confirm | 防账号枚举（恒 200）；JWT purpose=pwreset 15min；emails 追加 reset 模板 |
| POST /api/promo/giftcard/purchase | $25/$50/$100 三档；GC-XXXX 生成 + 激活 ledger |

### 11.2 可观测性 + 应用级限流（core/observability.py）
- **X-Request-Id**（透传/生成 12hex + 回写）+ glowmag.access 单行结构化日志（rid/method/path/status/ms）
- **GET /metrics**（Prometheus 文本）：requests_total{method,path,status}（动态段折叠 {id}、static/openapi 归组）+ duration summary（p50/p95，环形 10000 样本）
- **限流**（内存滑动窗，超限 429 + Retry-After）：login 60/min、register 30、password-reset 20、mock-pay 120、tickets 30——应用层兜底，线上仍以 Nginx/Cloudflare 为第一道（§2.2）
- main.py 预挂（ImportError 守卫），零侵入路由

### 11.3 前台再接线 11 页（累计 31 页联通）
- 账户侧 6：wishlist（真列表+两段式移除+加购反查）、rewards（余额三数+流水❄冻结）、refer（推荐码/复制分享/邀请表/Simulate invite）、gift-cards（余额查询+三档购买生成码）、unsubscribe（token 校验+成功态+Resubscribe）、login（forgot-password 两步 modal）
- 内容侧 5：faq（DB 分组+计数徽标）、blog/blog-post（文章列表/详情+手写 md 渲染器 XSS 转义+TOC 生成）、contact（建工单+My tickets 消息流）、search（实时联想走 API+本地最近搜索并存）
- admin 侧本轮无变化（上轮 11 页已全通）

### 11.4 回归总账
后端 **271/271**（A 20 + B 56 + C 78 + worker 37 + refsub 38 + obs 17 + payments 25）；前端 verify.ps1 通过 + 双模式 jsdom 136 项（74+62）；实库冒烟 7 端点全通。

**下一步**（低优先）：K8s 3 台拓扑（§7.2，流量到时）· Qdrant 语义搜索（P3）· 真实 Stripe 密钥 · Cloudflare 生产接入。

---

## 12. 第五批演进 · 收官（已完成）

### 12.1 前台接线补完（累计 34 页联通）
- **account-address**：地址簿 CRUD（默认址切换/编辑弹窗/.arm 两段式删除）
- **subscribe**：双态（无订阅→计划卡下单；有订阅→状态卡 Pause/Resume/Cancel + next_billing；价格以 API 为准）
- **index**：New Arrivals 4 卡实时化（价格/划线价/库存徽标/Quick Add）

### 12.2 看板真实趋势（admin）
- dashboard 新增 `daily`（14 天连续 GMV/订单序列）、`reconcile`（最近对账行）、`low_stock_top`（前 5）
- admin.html 趋势柱状图接真实序列（全零降级为演示+角标）；底部对账行（支付差/积分差/状态徽标）

### 12.3 E2E 全旅程回归套件（scripts/test_e2e.py，61 断言）
逛→注册→地址/愿望单→游客车→merge→折扣试算($31.10)→下单→支付→积分冻结→推荐有礼双份奖励→工单→后台发货/送达→RMA（批准/收货回补/退款）→礼品卡→worker 消费+对账→退订→/metrics。发版必跑，幂等（每次 DROP 重建库）。

### 12.4 E2E 抓出的真实 bug（本轮已修）
1. **RMA 退款不含税/折扣分摊**：旧口径 `qty×单价+499`，含税订单永远到不了 REFUNDED、积分不作废 → 改为**按订单实付比例折算**（`item.share × grand_total/subtotal`，质量原因加退运费 499，封顶 grand_total）——单件全退恰为全额，订单可达 REFUNDED（admin_trade.refund_rma）
2. **worker 对账退款日误报**：payments_gross 只统计 status=1，退款单被剔除而 orders_paid 仍含 → 放宽为 status IN (1,3,4)（当日实收口径，worker.reconcile）
3. JWT dev secret 长度 <32 字节触发 PyJWT 警告 → 默认值加长
4. 测试口径同步：test_b RMA 2098→2158（含税分摊）、补退 1012→952；test_e2e 移除 tax_rate=0 临时绕道（退款=2038 全额）

### 12.5 回归总账（最终）
**8 套 332 断言全绿**：E2E 61×2 + A 20 + B 56 + C 78 + worker 37 + refsub 38 + payments 25 + obs 17；前端 verify.ps1 通过；根 README.md 导航就位。

---

## 13. 第六批演进 · 硬化（已完成）

### 13.1 并发正确性修复（checkout._RESERVE_SQL）
- **Bug**（并发压测发现）：乐观锁 `WHERE version=:v` 无重试 → 30 并发秒杀仅 2-3 单成交，27 人收到**假性缺货 409**（库存从未归零）——超卖防护一直成立（stock 绝不为负），但严重 undersell
- **修复**：预扣改为单语句原子扣减（`stock=stock-qty WHERE stock>=qty AND is_active=1`，version 仅自增不再参与守卫）——无假冲突、无超卖；测试：**30 并发恰好售罄 10 单 / 409=20 / 库存归零**
- scripts/test_concurrency.py（6 用例）：超卖竞态 / 同用户幂等 / 10 单并发支付积分无重 / 限流 21 连发 / 只读 50 并发 P95=545ms（SLO 800ms 内）/ 61s 窗口恢复 —— **6/6**

### 13.2 备份恢复首次演练（deploy.md §7 演练记录）
- backup.ps1 实跑（52 表，13.5KB gz）→ 临时库恢复 → 行数/CHECKSUM/抽查单（$31.10）/users 全字段比对全一致 → **应用级验证**（drill 库起 uvicorn：health+bare-gems $15.99 均 200）
- 固化 scripts/restore-drill.ps1（一键：建库→解压→导入→核验→应用验证→清理，-KeepDb 留现场；二次干跑 10.4s 通过）；下次演练建议 2026-11-16 前

### 13.3 演示库充实（seed --reset）
16 用户（2 风控/3 沉睡/银金卡）· 26 订单（**dashboard 14 天窗 9 个非零日**）· 49 评价（分布 59/24/10/4/2%，6 带图，3 待审 1 拒绝，商品 rating 重算对齐）· 5 RMA（全状态，退款按实付比例口径）· 7 工单（全状态含满意度）· 4 UGC · 7 文章（6 发布+1 草稿）· 7 核销 · 17 库存流水 · popup 转化 26% —— API 模式后台/内容页全部有真实运营态可看。

### 13.4 回归总账（最终·硬化后）
**9 套 338 断言全绿**（+并发 6）：E2E 61 + A 20 + B 56 + C 78 + worker 37 + refsub 38 + payments 25 + obs 17 + concurrency 6；演示库 seed --reset 可重复。

---

## 14. 业务差距审计（§14 由审计智能体产出，见上/附录）
121 条目：✅58 / 🟡28 / ❌32；完备度 61%（P0 加权 50%）。P0 清单与口径偏差表详见 §14 原文。

## 15. 第七批演进 · P0 资损修复（已完成）

### 15.1 安全审计（A）+ 修复
- **工单 IDOR 已修**：GET /api/support/tickets 任意邮箱枚举工单对话 → 登录仅自查（他人 403）/ 游客必须 ticket_no+email 双因子
- login 401 文案统一（防账户存在性枚举）；57 个 admin 端点全 require_admin 验证通过；JWT role 从 DB 读（payload 篡改无效）；test_sec **29/29**（攻击者视角：跨用户地址/RMA/订阅 404、双因子、JWT 伪造/过期）

### 15.2 索引与性能（B）
- 对照数据库文档 §13 逐项核验：补 referrals `uk_code_email`(unique) + discount_redemptions `idx_code_email`（迁移 11e1cc89ae3a，实库已应用）；20k 商品/50k 订单规模 EXPLAIN 复验全部命中（referrals 50000 行扫描 → const 1 行）
- N+1 修复：catalog 列表 101 SQL→8 SQL（-92%）、admin_trade 回补批查、dashboard 聚合化；test_perf **29/29**

### 15.3 P0 资损/资产修复（集成者，源自审计发现）
| 缺陷 | 修复 |
|---|---|
| **礼品卡免费铸造**（未支付即得 active 卡，实测铸 $100 全额抵扣） | purchase 改为创建 status=0 待激活卡 + 待付订单（$25/50/100 走 item variant_id=0 非库存行）；mark_order_paid 支付成功激活 + ledger；前端购买流自动 intent→mock-pay→展示激活码 |
| **积分只冻不解**（全系统无解冻路径，会员资产失效） | worker 新任务 unfreeze_points：paid_at+return_days 期满且订单非取消/退款、无未完结 RMA 的冻结行置 frozen=0（每轮上限 500） |
| **退订 token 宽限** | 收紧：HMAC token 或登录本人二选一（匿名裸 email → 400 token_required） |

### 15.4 回归总账（最终）
**11 套 397 断言全绿**：E2E 61 + A 20 + B 56 + C 78 + worker 37 + refsub 39 + payments 25 + obs 17 + sec 29 + perf 29 + concurrency 6。

**剩余 P0**（见 §14 清单）：PayPal/Apple Pay/Klarna 支付矩阵、州级税表、GDPR 导出/删除、变体级图片、真实 Stripe 密钥切换。

---

## 16. 第八批演进 · 分层模块化重构（已完成）

### 16.1 结构（8 域包 × 四层，对齐微服务蓝图）
`app/domains/{trade,member,catalog,promo,content,support,ops,ai}`——61 文件 5311 行；每域 `router*（薄 HTTP）/ service*（业务事务）/ repository（纯数据访问）/ schemas（DTO）`。

| 旧路由模块 | 新域归属 |
|---|---|
| cart/checkout/orders/payments/returns/admin_trade | trade（核心事务 mark_order_paid/apply_refund/_RESERVE_SQL 迁 service/repository） |
| account/points/referrals/subscriptions | member（services/referrals.py 转 shim） |
| catalog/admin_catalog | catalog（批量查询性能红线原样迁移） |
| promo + admin_ops 的 discounts/popups/settings | promo |
| content + admin_ops 的 articles/faqs/reviews/ugc | content |
| support + admin_ops 的 tickets | support |
| admin_ops 的 dashboard/members/logs | ops |
| ai | ai |

`app/routers/*` 全部降级为 1 行 re-export shim（admin_ops 为四域组装）——main.py 零改动、旧导入路径全兼容。

### 16.2 重构纪律（验收口径）
- **行为零变化**：端点面 135 条逐一比对 identical；**全部 11 套 397 断言零测试修改通过**
- 分层自查：router 无 `db.query/db.execute/text(`；repository 无 HTTPException；跨域只走 service
- 性能红线保持：catalog 批查（8 SQL/页）与 dashboard 聚合（≤25 查询）test_perf 复验通过

### 16.3 此后新代码规约
新端点进 `domains/<域>/`，四层各司其职；`routers/` 只留 shim；跨域复用进 `app/services/`。

---

## 17. 第九批演进 · P0 功能补齐（已完成）

### 17.1 州级税表（services/tax_rates.py）
- 50 州 + DC 税率（CA 0.0735 精确对齐基线 / NY 0.08875 / TX 0.0625 / OR·MT·NH·DE 0.0 免税）；`rate_for(state, fallback)` 未命中回退 settings
- price_cart 新增 `state` 参数 + 响应 `tax_state` 键；preview（body.state）与 place（地址州）已接通——**NY 257 / CA 213 基线不变 / OR 0** 实测
### 17.2 GDPR 导出/删除（member 域 + worker）
- GET /api/account/export（全量 JSON + DataRequest type=1 落库）；POST /delete-request（202 + 7 天宽限，重复 409，可撤销）；worker 新任务 process_data_requests（到期匿化：用户 anonymized/status=-1/登录失效，订单保留但脱敏，财务记录完整）
### 17.3 变体级图片（catalog 域）
- 变体创建/编辑支持 images（≤6，整表替换）；商品详情 variants[].images（批量单查询）；seed 7 张变体图
### 17.4 UGC 公开上墙（content 域 + 前台）
- GET /api/content/ugc（status=1，id 倒序，product 懒加载）；gallery.html 瀑布流 + "Get featured" 投稿表单（匿名可投，100 积分话术）；product.html 变体切换联动主图画廊（STYLE 徽标 + 回落商品图集）
### 17.5 回归总账（最终）
**13 套 445 断言全绿**（+p0 32 +p0b 16）：E2E 61 + A 20 + B 56 + C 78 + worker 37 + refsub 39 + payments 25 + obs 17 + sec 29 + perf 29 + concurrency 6 + p0 32 + p0b 16；零测试修改；演示库 seed --reset 含变体图与 6 条 UGC。

**剩余 P0**（全部外部依赖）：PayPal/Apple Pay/Klarna、真实 Stripe 密钥、Cloudflare 生产接入。

---

## 18. 第十批演进 · 履约域补齐（已完成）

### 18.1 换货全流程（exchanges 影子表激活）
- 用户侧 3 端点（创建/列表/详情：窗口与可换量校验、price_diff 三态）+ 后台 6 端点（队列/approve 分流[diff>0→待差价→mark-paid]/reject/ship[新变体原子扣减+shipment]/complete[旧变体回补+exchanged_qty]）
- 前台 account-orders 换货三步向导接线（选可换 item→商品+变体下拉→差价确认→EX 单号；每单换货历史 chips）；test_exchanges **47/47**
### 18.2 到货通知 + 定时上架
- stock-notify 三端点（售罄才可订阅/幂等/取消）+ worker `restock_notify`（回补→outbox→restock_notify 邮件模板）
- 定时上架：前台查询过滤 `published_at<=now`（六处 repository 函数统一 `_visible()`，admin 不过滤+scheduled 徽标；PUT 支持 published_at）+ worker `publish_scheduled`（水位线去重 + product.published 事件）；seed 演示商品 velvet-nights（now+7d，前台隐身/admin 可见）；product.html 售罄态 Notify me 接线；test_stocknotify **29/29**
### 18.3 邮件偏好中心（细粒度退订）
- GET/PUT /api/account/email-preferences（登录或 email+token 双通道）：三开关部分更新、任一开=复订清 unsubscribed_at、全关=等价全退；前台 unsubscribe.html Preference Center 卡（toggle + 直访 token 流）；与 worker 弃购合规联动；test_emailpref **13/13**
### 18.4 回归总账（最终）
**16 套 534 断言全绿**（+exchanges 47 +stocknotify 29 +emailpref 13）；端点 135→**155**；演示库 seed --reset（14 商品含 1 定时上架）；verify.ps1 通过。

影子表现状：exchanges ✅ / stock_notifications ✅ / data_requests ✅ / variant_images ✅ / product_translations（多语言，P2 遗留）。

---

## 19. 第十一批演进 · 支付矩阵与运营就绪（已完成）

### 19.1 支付矩阵代码侧就绪（payment_provider 扩展）
- **PayPalProvider**（Orders v2 结构桩：oauth + checkout/orders + PayPal-Request-Id 幂等；凭据缺失自动降级，monkeypatch 测试零外呼）
- **Klarna** 经 Stripe `payment_method_types`（GM_STRIPE_KLARNA=1）
- **选择矩阵**：stripe > paypal > mock（半缺凭据跳过+一次性告警）；`GET /api/payments/methods` 公开支付方式（前端可渲染）；create-intent 可选 provider 参数
- 环境变量：GM_PAYPAL_CLIENT_ID/SECRET/BASE（沙箱默认）、GM_STRIPE_KLARNA；test_payments 25→**43**
### 19.2 后台换货队列 + 定时上架 UI（端点早已就绪的补缺）
- admin-returns 双 tab（RMA | Exchanges）：状态机操作（批准/拒绝 .arm/标记收款/发货弹窗/完成）、差价±着色、子状态 tab；admin-products ⏰ 定时徽标 + 改定时/清空弹窗 + 新建透传 published_at；jsdom **37/37** + 真服务 **8/8**
### 19.3 运营日报（worker daily_digest）
- 昨日 GMV/订单/退款/新客/6 项待办/Top3 商品/库存预警 → daily_digest 模板 → digest_recipients 循环投递（水位去重 digest_last_date；零活动仅推水位）
### 19.4 商品多语言（product_translations 影子表激活——最后一块）
- GET 详情/列表 ?locale=zh-CN（有译替换文案+locale 键，回退 en-US；价格结构不变）；admin translations upsert/删除/列表（AdminLog）；seed 3 款中文翻译（对齐 GM_CATALOG.titleZh 口径）
### 19.5 回归总账（最终）
**17 套 547 断言全绿**（payments 25→43 + digest 25）；verify.ps1 通过；演示库含换货样本 + translations=3。

**影子表全部激活**（51 表无影子）。剩余均为外部凭据依赖（真实 Stripe/PayPal 密钥、Cloudflare 生产接入）。

---

## 20'. 第十二批演进 · 工程收尾（已完成）

- **前台支付方式 UI + 中文 locale 联动**：checkout 拉 /api/payments/methods（多 provider 渲染 radio 卡 + 回落 toast；单 mock 保持静态视觉+实时徽标）；store/product zh 模式请求带 locale=zh-CN（有译中文卡片/详情，回退英文）；jsdom 26/26
- **一键回归 runner**：`run_all.ps1`（17 套 + 前端 verify，汇总表/总耗时/-Fast/-Suite 过滤）——完整跑 **17 PASS / 154.4s**
- **安全响应头 + 静态缓存**：nosniff/DENY/Referrer/Permissions/CSP 五头全响应注入（不覆盖已有）；静态资产 7 天缓存、HTML no-cache；test_hardening 17/17
- **API.md**（gen_api_docs.py 生成，149 端点 · 20 分组 · 鉴权 admin 66/user 30/public 53，--check 陈旧校验）+ **CHANGELOG.md**（11 版本 + 断言演进线 154→547）+ 本文档 §20 索引

回归总账（最终）：**17 套 564 断言全绿**（+hardening 17）+ 前端 verify，一键可复跑。

---

## 21. 第十三批演进 · 体验缝合（已完成）

- **前台遗留债清零**（第 11 轮审计 Blocked 项）：cart/account-address 两段式确认切全局 `.arm` 类（清行内 style.color）；login/register `.pw-wrap/.pw-eye` 上收 style.css（两页 -10 行）；`.pay-pill` 参数统一收敛；jsdom 30/30
- **chrome.js 三项 API 化**：页脚 18 处硬编码 i18n 化（93→111 键 en/zh 对称：Do Not Sell/退订/Cookie 设置/全部 aria）；购物车抽屉"猜你喜欢"接 /api/ai/recommend（空车 hot，SLUGS 过滤+车内去重+竞态守卫，失败回落本地）；搜索弹窗联想接 /api/catalog/search（防抖 350ms+分类 chip+非商品 slug 处理）；jsdom 59/59 + 真服 11/11
- **index 新品区 locale 联动** + **邮件模板运营预览**（GET /api/admin/ops/email-templates 示例数据渲染 8 模板；admin-marketing 📧 tab iframe srcdoc 预览）；test_tplpreview 12/12
- 工程整理：test_tplpreview 归位 server/scripts（位置无关路径）；API.md 重生成（**150 端点**）；run_all 清单 17→**18 套**
- 回归总账：**18 套 576 断言全绿**（run_all.ps1 201.4s）。

---

## 14. 业务功能差距审计（智能体 C · 2026-08-16）

> 对照《业务功能完善度分析 v1.2》《前端完整设计文档 v1.0》逐条盘点实现状态。审计方法：读码 + 起 :8021 uvicorn 实测（折扣叠加 $31.10 口径复算、礼品卡铸造-抵扣链路复现、积分冻结余额、退订 token、影子端点 404 探测），服务已停。
> 状态：✅ 已实现（附位置）/ 🟡 部分实现（缺什么）/ ❌ 未实现 / ➖ 文档级设计（代码无需实现）。P = 优先级（P0 上线必须 / P1 上线后一月 / P2 演进）；量 = S(<半天)/M(1-2天)/L(3天+)。

### 14.1 差距矩阵总表（121 条）

**A. 交易/支付（15 条）**

| # | 条目 | 状态 | 位置 / 缺口 | P | 量 |
|---|---|---|---|---|---|
| A1 | 信用卡支付（Stripe Provider 就绪） | 🟡 | payments.py:127 + payment_provider.py；默认 Mock，`GM_STRIPE_KEY` 即切真 | P0 | S |
| A2 | PayPal | ❌ | checkout.html 仅 tab 演示，无后端渠道 | P0 | M |
| A3 | Apple Pay / Google Pay | ❌ | 同上（Stripe 域名验证+PRB 按钮即可） | P0 | S |
| A4 | Klarna/Afterpay 先买后付 | ❌ | 同上（Stripe klarna 一行 payment_method_types） | P0 | S |
| A5 | 结账分项拆行（小计/码/捆绑/积分/礼品卡/运/税） | ✅ | checkout.preview + pricing.py | | |
| A6 | 州级销售税 / Stripe Tax | ❌ | settings.tax_rate 统一 7.35%（实测） | P0 | M |
| A7 | 地址校验自动补全（Smarty/Google） | ❌ | checkout.html 无 autocomplete | P1 | M |
| A8 | 订单备注前台入口 | ✅ | checkout.html note → PlaceRequest.note → orders.note | | |
| A9 | 礼品留言 + 礼品单标记 | ✅ | gift_flag/gift_message 全链路（隐藏发票价 ➖） | | |
| A10 | 折扣码规则引擎（门槛/限次/首单/封顶/时段） | ✅ | promo_rules.py 唯一闸门 | | |
| A11 | 折扣码 × 捆绑叠加 | ✅ | pricing.py:120；实测 3198 = 码 640 + 捆绑 479 | | |
| A12 | 券门槛差额提示（"再买 $X 可用"） | 🟡 | /promo/validate 只回 reason 不带差额；前端本地演示有 | P1 | S |
| A13 | 拆分支付明细（payment_methods 多路） | 🟡 | 礼品卡+卡隐式组合可付；无 payment_methods 表分路记账 | P1 | M |
| A14 | 多币种展示/结算 | ❌ | 全站 USD 单币种 | P2 | M |
| A15 | VAT 发票 | ❌ | 邮件收据即美国收据口径 | P2 | M |

**B. 履约/物流（16 条）**

| # | 条目 | 状态 | 位置 / 缺口 | P | 量 |
|---|---|---|---|---|---|
| B1 | 库存预扣/实扣/释放/回补全流水 | ✅ | checkout/payments/orders/worker + stock_movements 唯一真相 | | |
| B2 | 超时关单+库存释放（30min 可配） | ✅ | worker.cancel_timeout_orders | | |
| B3 | 并发防超卖 | ✅ | 原子单语句扣减 + test_concurrency 6/6 | | |
| B4 | 整单发货回填运单号 | ✅ | admin_trade.ship | | |
| B5 | 拆单发货（一单多包/部分发货） | ❌ | Shipment.item_json 结构就绪，但 ship 一次发全量、无多包裹 UI | P1 | M |
| B6 | 游客物流跟踪页（免登录） | ✅ | orders./track + track.html | | |
| B7 | 异常件自动检测（滞留/失败标红+转工单） | ❌ | track 页仅人工演示切换；无 Shippo webhook 拉轨迹 | P1 | S |
| B8 | 时效承诺展示（预计 X-Y 天送达） | 🟡 | shipping-policy.html 静态 3-5 天；详情/结算页无 ETA 计算 | P1 | S |
| B9 | 运费规则表（重量/目的国/金额选承运） | ❌ | settings 3 键静态（免邮线/4.99/14.99） | P1 | M |
| B10 | RMA 用户侧自助申请 | ✅ | returns.py（30 天窗口/数量校验/时间线） | | |
| B11 | RMA 后台状态机 + 按实付比例退款 | ✅ | admin_trade rmas/*（§12.4 口径） | | |
| B12 | 质量问题退运费 | ✅ | refund_rma reason 2/4/5 + 499 | | |
| B13 | 预付退货标签（真 Shippo） | 🟡 | approve 写 label_url mock 路径 | P1 | M |
| B14 | **换货全流程** | ❌ | **Exchange 表就绪、零端点零接线**；account-order-detail 向导为纯演示 | P1 | S-M |
| B15 | 退货原因结构化统计 | 🟡 | reason 落库+admin-returns 原因图为演示数据，无聚合端点 | P1 | S |
| B16 | 海关/报关（CN22） | ❌ | 国际件未涉及 | P2 | L |

**C. 营销/转化（22 条）**

| # | 条目 | 状态 | 位置 / 缺口 | P | 量 |
|---|---|---|---|---|---|
| C1 | 欢迎订阅弹窗（DB 配置+频控） | ✅ | /api/promo/popup + app.js | | |
| C2 | EXIT intent 挽留弹窗 | ✅ | app.js（scene 可配） | | |
| C3 | 领码限时倒计时紧迫 | 🟡 | 前端 15min 倒计时有；折扣码无时效绑定（过期即失效而非倒计时） | P2 | S |
| C4 | 弹窗后台 CRUD + 转化率 | ✅ | admin_ops popups + admin-marketing.html | | |
| C5 | 折扣码后台 CRUD + 启停 | ✅ | admin_ops discounts + admin-marketing.html | | |
| C6 | 闪购/每日特惠（到点自动上下架） | 🟡 | sale.html 专题+tags；无定时任务 | P1 | M |
| C7 | 满赠规则（满 $45 送锉条） | 🟡 | 前端进度条完整；pricing 引擎无 gift 类型规则 | P1 | M |
| C8 | 捆绑自动折扣（2 件 85/3 件 8 折） | ✅ | pricing.py:114 | | |
| C9 | 弃购三封阶梯召回 | ✅ | worker.scan_abandoned_carts（ABANDON10/15/无码） | | |
| C10 | 弃购退订合规跳过 | ✅ | EmailPreference 双条件检查 | | |
| C11 | **到货通知全链路** | ❌ | stock_notifications 表+restock 模板+outbox 事件映射就绪；**无订阅端点、无触发任务**（链路死路） | P1 | S |
| C12 | 最近浏览 | ✅ | app.js localStorage | | |
| C13 | AI 推荐/猜你喜欢（四级降级） | ✅ | ai.py recommend/hot | | |
| C14 | UGC 投稿激励闭环（采用奖 100 分） | ✅ | content.ugc + admin 审核 | | |
| C15 | 邮件退订中心 | ✅ | unsubscribe.html + /api/account/unsubscribe（HMAC token） | | |
| C16 | 退订 token 强制 | 🟡 | 宽限模式：无 token 也 200（实测），日志告警；上线须关闭 | P0 | S |
| C17 | 邮件偏好中心细粒度（三开关） | 🟡 | EmailPreference 三列有；**无 GET/PUT 偏好端点**，account-settings.html 未接线 | P1 | S |
| C18 | 邮件真实投递（Resend/Klaviyo） | 🟡 | outbox+6 模板全就绪，deliver=日志；Klaviyo 无任何集成 | P1 | S |
| C19 | 生日营销流 | ❌ | users.birthday 字段+登录返回有；注册无入口、无发券任务 | P1 | M |
| C20 | 沉睡唤醒流（60/90 天 EDM） | 🟡 | admin-members 演示行；无 worker 任务 | P1 | M |
| C21 | 推荐有礼（双向 1000 分/防自邀/脱敏） | ✅ | referrals.py + on_order_paid 钩子 | | |
| C22 | 推荐防刷（同卡/同 IP） | ❌ | 仅防自邀 | P2 | M |

**D. 会员/资产（16 条）**

| # | 条目 | 状态 | 位置 / 缺口 | P | 量 |
|---|---|---|---|---|---|
| D1 | 积分三视图（余额/冻结/可用） | ✅ | points.py 3 端点 + rewards.html | | |
| D2 | 支付后冻结发放 | ✅ | payments.mark_order_paid → grant_for_order(frozen=1) | | |
| D3 | 积分抵扣（100 分=$1） | ✅ | pricing + points_svc.spend | | |
| D4 | 积分抵扣 50% 上限 | ❌ | 前端设计文档 §4.3 口径；后端 min(points, subtotal−discount) 无上限 | P1 | S |
| D5 | **冻结积分解冻（退货期后）** | ❌ | **全系统无解冻路径**：worker 无任务、mark-delivered 不解冻（seed 手工造 UNFREEZE 行掩盖）；实测 emma 311 分永久冻结 | P0 | S |
| D6 | 积分过期 | 🟡 | worker.expire_points 就绪，但运行时发放不设 expires_at（只对 seed 数据生效） | P1 | S |
| D7 | 会员等级权益（Silver/Gold） | 🟡 | User.tier 字段+rewards 页演示；无等级计算与分级权益 | P1 | M |
| D8 | **礼品卡购买（付费）** | ❌ | **资损洞（实测复现）**：POST /api/promo/giftcard/purchase 未鉴权未支付即铸造 $25/50/100 卡，结算可全额抵扣 | P0 | S-M |
| D9 | 礼品卡余额查询 | ✅ | promo./giftcard | | |
| D10 | 礼品卡结算抵扣 + ledger | ✅ | checkout.place + gift_card_ledger | | |
| D11 | 礼品卡过期/冻结细则 | 🟡 | 兑换校验 expires_at/status=2 有；购买从不设过期、冻结状态无代码路径 | P1 | S |
| D12 | 订阅盒状态机（暂停/恢复/跳过/取消） | ✅ | subscriptions.py + subscribe.html | | |
| D13 | 订阅自动续期扣款 | ❌ | SUBMOCK 占位创建；无 billing 周期任务（业务文档 P2 战略级） | P1 | L |
| D14 | 储值钱包（充值送） | ❌ | gift_cards 结构可复用未做 | P2 | L |
| D15 | 愿望单 | ✅ | account.py + account-wishlist.html | | |
| D16 | 地址簿 CRUD | ✅ | account.py + account-address.html | | |

**E. 商品/内容（15 条）**

| # | 条目 | 状态 | 位置 / 缺口 | P | 量 |
|---|---|---|---|---|---|
| E1 | 尺码指南（独立页+详情弹窗+五指选码） | ✅ | size-guide.html + product.html 弹窗 | | |
| E2 | 变体级图片（切换联动 Gallery） | ❌ | VariantImage 表就绪；_variant_out 不出图、后台无编辑、前端不联动（业务文档 P0） | P0 | M |
| E3 | 商品视频位 | ✅ | video_url 字段→详情返回（seed 需补素材） | | |
| E4 | 预售 | ❌ | 未做（与到货通知互补） | P2 | M |
| E5 | 定时上架 | 🟡 | published_at + publish/unpublish 手动端点；无定时任务 | P2 | S |
| E6 | 套装商品独立形态 | 🟡 | 捆绑满折口径有；"套装 SKU"作为商品形态无 | P1 | M |
| E7 | 多语言商品（product_translations） | ❌ | 表就绪；catalog API 无 locale 参数（前台 EN/中 仅 UI 文案切换） | P2 | L |
| E8 | 搜索（联想/容错/零结果兜底） | ✅ | catalog.search LIKE + search.html（Meilisearch 为已声明演进 ➖） | | |
| E9 | 评价（已购校验/一单一评/后台审核） | ✅ | content.reviews | | |
| E10 | 评价图片上传 | 🟡 | images 仅 URL 数组；无上传端点与对象存储 | P1 | M |
| E11 | 评分聚合/直方图 | ✅ | rating_avg×100 + 前端直方图 | | |
| E12 | 博客 + 后台 CRUD（草稿/发布） | ✅ | content.articles + admin_ops | | |
| E13 | FAQ 中心 + 后台 CRUD | ✅ | content.faqs + admin_ops | | |
| E14 | UGC 画廊页接 API | 🟡 | 提交/审核链路通；gallery.html 瀑布流仍为演示数据 | P1 | S |
| E15 | 政策页 ×4（隐私/条款/退换/物流） | ✅ | 静态页齐备 | | |

**F. 客服（7 条）**

| # | 条目 | 状态 | 位置 / 缺口 | P | 量 |
|---|---|---|---|---|---|
| F1 | 工单（提交/列表/留言/关联订单） | ✅ | support.py + contact.html | | |
| F2 | 客服工作台（回复/关单/指派/画像） | ✅ | admin_ops tickets + admin-tickets.html | | |
| F3 | 快捷回复模板 | ✅ | support./templates + 前端 chips | | |
| F4 | 订单内部时间线（全事件流） | ✅ | OrderTimeline（状态/退款/RMA/工单） | | |
| F5 | AI 客服 GlowBot（中英/脱敏/转人工/降级） | ✅ | ai.chat + chrome.js 双模式 | | |
| F6 | 工单 SLA 统计 | 🟡 | 页面演示列；无应答时长计算 | P2 | S |
| F7 | 工单满意度回评 | 🟡 | 字段+seed 演示；无端点 | P2 | S |

**G. 合规（7 条）**

| # | 条目 | 状态 | 位置 / 缺口 | P | 量 |
|---|---|---|---|---|---|
| G1 | Cookie 分区同意横幅 + 落库 | ✅ | app.js + /api/account/consent（CookieConsent） | | |
| G2 | GDPR 数据导出（自助） | ❌ | DataRequest 表+account-settings 按钮（toast 演示）；无端点 | P0 | M |
| G3 | GDPR 账户删除（30 天宽限） | ❌ | 同上 | P0 | M |
| G4 | CAN-SPAM（物理地址+一键退订链接） | ✅ | emails._FOOTER | | |
| G5 | 退订即时生效 | ✅ | unsubscribe 同步写库 | | |
| G6 | CCPA Do-Not-Sell 声明 | 🟡 | 页脚/隐私页静态声明；请求未落库 | P1 | S |
| G7 | WCAG 无障碍基础 | 🟡 | alt/键盘/两段式确认有；未系统过检（EAA 2025） | P1 | M |

**H. 数据运营（9 条）**

| # | 条目 | 状态 | 位置 / 缺口 | P | 量 |
|---|---|---|---|---|---|
| H1 | 大盘看板 + 14 天趋势 + 对账行 | ✅ | admin_ops.dashboard daily/reconcile/low_stock_top | | |
| H2 | 每日对账（支付 vs 订单 / 积分 vs 流水） | ✅ | worker.reconcile_daily | | |
| H3 | 商品表现视图（加购率/转化率/退货率） | ❌ | 无 per-product 运营视图 | P1 | M |
| H4 | 库存周转/滞销预警 | 🟡 | /stock/low 有；周转天数/滞销为演示数 | P1 | S |
| H5 | 用户资产（LTV 分层/复购周期） | ❌ | members 有 total_spent/risk；无分层视图 | P1 | M |
| H6 | 营销 ROI（各码核销与带来 GMV） | 🟡 | DiscountRedemption 落库；无 ROI 聚合视图 | P1 | S |
| H7 | 履约监控（发货时长/时效达成率） | ❌ | 数据在 timeline 里，无视图 | P2 | M |
| H8 | 成本毛利 | 🟡 | variant.cost 列已建；后台无编辑、无毛利视图 | P1 | M |
| H9 | 操作审计日志 | ✅ | admin_logs + /admin/ops/logs | | |

**I. 供应链/后台效率（6 条）**

| # | 条目 | 状态 | 位置 / 缺口 | P | 量 |
|---|---|---|---|---|---|
| I1 | 采购单/在途/质检 | ❌ | admin-inventory 生成采购单按钮为 toast；无表无端点 | P1 | L |
| I2 | 批量发货/批量打单 | 🟡 | 批量按钮为 toast 演示；单笔 ship 真实 | P1 | M |
| I3 | 订单 CSV 导出 | ✅ | admin-orders.html 前端真实导出（可见行优先） | | |
| I4 | 打单发货流水线（待打单→拣货→扫码校验） | ❌ | 未做 | P1 | M |
| I5 | 库存盘点（差异调整） | ❌ | toast 演示 | P2 | M |
| I6 | 多仓库存（美西/美东/中国） | ❌ | 单仓 stock 字段；三仓为演示页 | P2 | L |

**J. 系统（8 条）**

| # | 条目 | 状态 | 位置 / 缺口 | P | 量 |
|---|---|---|---|---|---|
| J1 | JWT + RBAC（role≥2 后台） | ✅ | core/security + deps | | |
| J2 | 可观测（X-Request-Id/metrics/应用限流） | ✅ | core/observability.py | | |
| J3 | Alembic 前向迁移 | ✅ | migrations/（只前向纪律） | | |
| J4 | Compose 部署 + 备份 + 恢复演练 | ✅ | deploy.md/Dockerfile/backup.ps1/restore-drill.ps1 | | |
| J5 | 回归体系（9 套 338 断言） | ✅ | scripts/test_*.py | | |
| J6 | MySQL 主从 + 读写分离 | ➖ | 文档级演进（§7.2 资金强制读主） | | |
| J7 | K8s 3 台拓扑 | ➖ | 文档级演进 | | |
| J8 | Redis/Meilisearch/Qdrant | ➖ | 演进路径（购物车落 DB/LIKE 搜索为已声明简化） | | |

### 14.2 统计

| 口径 | 数值 |
|---|---|
| 总条目 | **121**（有效 118 + 文档级 ➖3） |
| ✅ 已实现 | **58**（47.9%） |
| 🟡 部分实现 | **28**（23.1%） |
| ❌ 未实现 | **32**（26.4%） |
| ➖ 文档级 | **3** |
| **完备度（不加权）** | (58 + 28×0.5) / 118 = **61.0%** |
| **完备度（P0 加权口径）** | 上线必须集 20 项：✅10 / 🟡1 / ❌9 → **50%**（半分计 52.5%） |

结论：**"能下单、能履约、能对账"的主干（交易状态机/库存/RMA/工单/看板）完成度很高（≈90%）**；缺口集中在①支付矩阵与税务（北美 DTC 上线硬门槛）、②GDPR 自助（合规红线）、③"表先行端点缺"的影子功能（换货/到货通知/数据请求/变体图/翻译），以及本审计新发现的 2 个资损洞。

### 14.3 P0 清单（上线阻塞项 · 最小实现方案）

| # | 阻塞项 | 最小实现方案（一句话） |
|---|---|---|
| 1 | **D8 礼品卡免费铸造（资损洞）** | purchase 端点改为建 status=0 待激活卡并生成订单走既有 create-intent→支付→webhook 链，付讫回调置 status=1 + ledger type=1（复用现有支付事务，≈半天） |
| 2 | **D5 积分永不解冻（资产失效）** | worker 加 unfreeze_points 任务：paid_at+return_days 且无未完结 RMA 的 frozen 行 → frozen=0 + UNFREEZE 流水（照抄 expire_points 骨架 ≈40 行） |
| 3 | C16 退订 token 宽限 | 删除 account.py 无 token 也放行的宽容分支，邮件链接统一携带 HMAC token |
| 4 | A2 PayPal | payments 旁新增 PayPalProvider（Orders v2 create/capture 两端点），前端 PayPal tab 走授权跳转 |
| 5 | A3 Apple/Google Pay | Stripe Payment Request Button + 域名验证，payment_method_types 已兼容，后端近零改动 |
| 6 | A4 Klarna BNPL | Stripe intent 的 payment_method_types 加 'klarna'，line items 传商品名 |
| 7 | A6 州级税率 | 先内置 50 州静态税率 JSON，pricing 按 shipping_address.state 查表（后续切 Stripe Tax） |
| 8 | G2/G3 GDPR 导出/删除 | account.py 加 GET /export（聚合用户全量数据 JSON 下载）+ POST /delete（DataRequest 落库，worker 30 天宽限后匿名化） |
| 9 | E2 变体级图片 | _variant_out join variant_images 输出 images[]，admin 变体编辑支持图片，product.html Gallery 联动切换 |
| 10 | A1 真实卡支付收尾 | 生产注入 GM_STRIPE_KEY/GM_STRIPE_WEBHOOK_SECRET + pip install stripe，按 §10.1 零代码切换 |

### 14.4 P1/P2 路线图（按 ROI 排序前 10）

| # | 条目 | 为什么值 | 量 |
|---|---|---|---|
| 1 | B14 换货全流程 | 表/向导 UI 全就绪，补 returns.py 三个端点+admin 状态机即通；美妆 DTC"不喜欢免费换"直接降差评 | S-M |
| 2 | C11 到货通知 | 表+邮件模板+outbox 事件映射三件就绪，只缺订阅端点与 worker 补货触发；断货流量白流失 | S |
| 3 | C18+C17 邮件投递+偏好中心 | deliver 换 Resend 一处改动；偏好 GET/PUT 端点补上后全部营销流才真正可达用户 | S |
| 4 | C19/C20/C12 生日+沉睡+券差额 | 三个复购引擎共用 worker 扫描骨架（弃购已验证），LTV 直接收益 | M |
| 5 | D4+D11+D6 积分/礼品卡口径对齐 | 50% 上限一行、购买设 expires_at 一行、发放设过期一行——资产规则与文档对齐 | S |
| 6 | B9+B8 运费规则表+ETA | shipping_rates 迁移+pricing 查表，国际扩张与时效承诺前置 | M |
| 7 | B5 拆单发货 | ship 端点加 items 参数 + 多包裹回填 UI，Shipment 模型现成 | M |
| 8 | H3+H6 商品表现/营销 ROI 看板 | 纯 SQL 聚合视图，数据已齐（timeline/redemptions/sold_count），指导推流与停投 | M |
| 9 | D13 订阅真实扣款 | 先做 worker 周期任务（发提醒邮件+mock 扣款），再切 Stripe Billing | L |
| 10 | A7 Smarty 地址校验 | 前端 SDK+后端 verify 代理，省运费纠纷 | M |

P2 择要：多语言商品（E7）、储值钱包（D14）、预售（E4）、海关报关（B16）、采购单（I1）、多仓（I6）、WCAG 系统化（G7）、履约监控（H7）。

### 14.5 文档 vs 实现的口径偏差表

| # | 业务文档口径 | 实现口径 | 影响 |
|---|---|---|---|
| 1 | 积分"退货期 30 天后解冻"（§3） | 冻结后**无任何解冻路径**；seed 手工写 UNFREEZE 行掩盖 | 用户赚取积分永久不可用（P0） |
| 2 | 积分抵扣"上限 50%"（前端设计 §4.3） | min(points, subtotal−折扣)，无上限 | 大额抵扣侵蚀毛利，前后端口径不一 |
| 3 | 快递运费 $12.99（前端设计 §4.3） | settings.shipping_express = $14.99 | 文档间不一致，以实现/原型为准 |
| 4 | 礼品卡两段式（change_type 2 冻结/3 确认/4 解冻） | place 时一步 type=3 直接扣+置尽 | 未支付订单的礼品卡额度无保护（低风险，超时关单不清礼品卡预占） |
| 5 | 礼品卡"过期/冻结细则" | 兑换校验 expires_at 存在，但购买**从不设置过期**；status=2 冻结无代码路径 | 校验成死代码 |
| 6 | 税"各州销售税/Stripe Tax" | settings.tax_rate 全局 7.35% | 非 CA 州错税（P0） |
| 7 | 支付矩阵 4 渠道（卡/PayPal/Klarna/礼品卡） | mock/Stripe 单路 intent；前端 4 tab 为 UI 演示 | 结算页承诺与实际通道不符 |
| 8 | 退订"一键退订链接（带 token）" | 宽限模式：无 token 也生效 | 可被恶意批量退订他人（P0 关宽限） |
| 9 | 评价"图集+灯箱+上传" | images 为 URL 数组，无上传服务 | 用户无法自助传图 |
| 10 | Klaviyo back-in-stock/生日流 | outbox 自研替代，Klaviyo 零集成 | 营销自动化能力=worker 任务清单 |
| 11 | Shippo webhook 更新物流状态 | shipments 状态仅后台手工推进（mark-delivered） | 无真实轨迹回传 |
| 12 | 定时上架（published_at+定时任务） | publish/unpublish 手动端点 | 爆款 0 点上架需人肉 |
| 13 | 积分过期规则（rewards 页明示） | expire_points 只扫有 expires_at 的行，运行时发放不设 | 规则只对 seed 生效 |
| 14 | Meilisearch/Redis/AI 独立服务 | LIKE 搜索/DB 购物车/AI 内置路由 | 已在 §7 声明的简化，非偏差，记录备查 |

### 14.6 审计过程备注

- 实测复现（:8021，GM_DB→glowmag，审计后已停）：①叠加口径 3198 → 码 640+捆绑 479=1119（✓ §3）；②礼品卡免支付铸造 $100 并在 preview 全额抵扣 1599（资损洞证据）；③emma 余额 611/冻结 311/可用 300；④unsubscribe 错 token=400、无 token=200；⑤影子端点 /api/exchanges、/api/account/preferences、/api/account/data-export、/api/admin/trade/shipments 全部 404。
- 前端接线核对：34/51 页接 GM_API（含 admin-login 共 11 后台页），未接线 16 页中 4 页（account-order-detail/account-returns/account-settings/account-points）属"应有后端但无端点"的影子页，其余为静态内容页（政策/教程/404/sale 等）——_index.html ⑱ 的联通声明与实际一致，**无需修正**。
- "影子表"现象：51 表中 exchanges、stock_notifications、data_requests、product_translations、variant_images 五张表仅有模型无端点——数据库先行策略让结构就绪，是下阶段最快的补齐骨架。

---

## 20. 文档索引（智能体 C · 2026-08-17）

> 全仓文档/脚本一句话导航：先读哪份、去哪找什么。

| 文档 / 脚本 | 一句话导航 |
|---|---|
| `README.md` | 项目总入口：目录导航 / 快速开始 / 17 套回归清单 / 种子账号 |
| `API.md` | **API 端点手册**（`scripts/gen_api_docs.py` 自动生成，勿手编；`--check` 供 CI 校验陈旧） |
| `CHANGELOG.md` | 版本史（Keep a Changelog）：0.1.0→0.11.0 十一批演进 + 回归断言数演进线 |
| `MVP实现说明-MySQL版.md` | 本文档：落地总账（技术决策/模块映射/各批演进/审计/踩坑） |
| `deploy.md` | 生产部署：首次 8 步 / Cloudflare 接入 / 备份与季度恢复演练 / →K8s 路径 / 故障手册 |
| `scripts/gen_api_docs.py` | API.md 生成器（展平 FastAPI 路由→分组→鉴权推断→写手册） |
| `scripts/backup.ps1` | MySQL 备份：mysqldump+gzip+14 天保留+异地提醒（-WhatIf 干跑） |
| `scripts/restore-drill.ps1` | 一键恢复演练：建库→导入→核验→应用级验证→清理（-KeepDb 留现场） |
| `数据库设计文档-完整版.md` | 51 表结构/索引/枚举权威口径（模型逐列对齐基准） |
| `高可用架构设计-v2.md` | 单机高可用纪律、主从读写分离与资金读主演进 |
| `微服务演进架构设计-v3.md` | 八域蓝图与拆分路径（domains/ 分包的理论依据） |
| `业务功能完善度分析.md` | 121 条业务差距矩阵与 P0/P1/P2 路线图 |
| `业务流程与数据模型全景.md` | 全业务流程与数据模型对照全景 |
| `前端完整设计文档.md` | 51 页原型设计口径（交互/计价/展示规则基准） |
| `指甲电商独立站系统设计.md` | 初始系统设计（总体架构与非功能目标） |
| `指甲电商独立站详细设计.md` | 初始详细设计（模块/接口/状态机细化） |
| `建站执行文档-参考glamnetic.md` | 对标站建站执行清单（品类/素材/节奏参考） |
| `微信公众号内容架构规划-v3.md` | 内容营销侧：公众号栏目与选题规划 |
| `server/README.md` | server 侧说明：环境/启动/测试补充 |

---

## 22. 一键演示（智能体 C · 2026-08-18）

> 把"能跑起来"变成"能讲故事"：根目录三脚本拉起/讲述/收尾，销售演示旅程对运行中的 :8000 全真实 API 讲完一个顾客的完整故事，`$31.10` 计价口径四处对齐（preview / place / 后台看板 / demo 输出）。

### 22.1 脚本清单

| 脚本 | 职责 |
|---|---|
| `start.ps1`（仓库根） | 一键启动：seed 数据检测（缺则自动灌种子）→ uvicorn :8000 → worker 定时任务 → 自动打开浏览器 |
| `scripts\demo.ps1` | 销售演示旅程（本节主角）：前置探 `/api/health`（不通提示先跑 start.ps1），十步走完，任一步失败即停并打印响应体；参数 `-Port`（默认 8000）/ `-SkipReturn`（跳过第 8 步退货） |
| `stop.ps1`（仓库根） | 收尾：停 uvicorn 与 worker |

### 22.2 旅程步骤表（demo.ps1 全真实 API，全新随机邮箱顾客）

| # | 步骤 | 关键 API | 演示看点 |
|---|---|---|---|
| 1 | 逛 | `GET /api/catalog/products` · `GET /api/catalog/search?q=bare` | 前 3 款（名/价格/库存）+ 搜索命中 Bare Gems |
| 2 | 注册 | `POST /api/account/register` · `POST /api/account/addresses` | 随机邮箱新客（触发欢迎券）+ San Francisco 地址簿 |
| 3 | 车 | `GET /api/cart`（游客 X-Cart-Token）· `POST /api/cart/items` ×2 · `POST /api/cart/merge` | Bare Gems 变体现查（详情 API）+ Magic Glue → 合并后登录车 2 件 $29.98 |
| 4 | 算 | `POST /api/checkout/preview`（code=WELCOME20, state=CA） | 分项打印：$29.98 − $6.00 码 + $4.99 运 + $2.13 税 = **grand $31.10** |
| 5 | 买 | `POST /api/checkout/place` → `POST /api/payments/create-intent` → `POST /api/payments/mock-pay` → `GET /api/points` | 订单号 + 状态 PAID + 积分入账 311（$1=10 分，冻结） |
| 6 | AI 客服 | `POST /api/ai/chat`（"where is my order …"） | intent=order，回复首行打印且单号脱敏为 `NS26****XXXX` |
| 7 | 后台 | `POST /api/account/login`（ops@）· `GET /api/admin/ops/dashboard` · `POST …/orders/{no}/ship`（usps+随机单号）· `GET /api/orders/track` | 今日 GMV 含本单 +1 → 发货 → 免登录轨迹 SHIPPED |
| 8 | 退货 | `POST /api/returns`（reason=2 质量）→ admin `approve → receive → refund` | 退款按实付比例口径：$16.59 货款 + $4.99 退运费 = 实退 $21.58（库存回补留痕） |
| 9 | 对账 | `GET /metrics` | `glowmag_http_requests_total` 中 demo 相关路径计数汇总（worker 批处理不在 HTTP API，另跑 `worker.py --loop`） |
| 10 | 收尾 | — | 本旅程数据统计（订单/用户/邮件在服务端日志）+ 清理方式：`seed.py --reset` 后重新灌种子 |

### 22.3 用法与注意

```powershell
.\start.ps1                    # 先拉起（或服务已在跑则跳过）
.\scripts\demo.ps1             # 完整十步；-SkipReturn 跳退货；-Port 8010 换端口
.\stop.ps1                     # 收尾
```

- demo.ps1 为 UTF-8 BOM、纯 PowerShell（ConvertFrom-Json，不依赖 jq）；步骤间 0.3s 间隔便于讲解跟读。
- 演示数据不污染种子基线的关键：随机邮箱 + 独立订单/RMA 单号；彻底重置走 `cd server; .venv\Scripts\python.exe scripts\seed.py --reset`（drop_all 重建）再 `scripts\seed.py` 灌种子。
