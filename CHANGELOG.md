# Changelog

本变更日志基于《MVP实现说明-MySQL版.md》§1-21 与 README 整理，格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
各批次未单独记录发布日期，按批次倒序排列（最新在前）；"回归断言"为该批次收官时全测试套件合计断言数（全 MySQL 实库）。

## [0.3.1] · 前端 workspace 统一打包发布

### Changed
- **npm workspaces**：根 package.json 统管 web/client + web/admin —— 一次 `npm install`（依赖提升根 node_modules，双端 vue/pinia 版本强制一致）、一条 `npm run build`。
- **统一发布目录 web/dist**：client 产物在根、admin 在 `/admin` 子目录（构建顺序 client→admin，client emptyOutDir 清空重建）；FastAPI 由双挂载简化为单目录 `SPAStaticFiles`（未命中按路径前缀回落 client/admin 各自 index.html；/api 不回落保持 JSON 404）。
- Dockerfile webbuild 阶段：根 npm ci + npm run build，产物单次 COPY /web/dist；run_all.ps1 verify 改根级单命令构建。
## [0.3.0] · 前端 Vue 3 SPA 全量重构

### Changed
- **web/client 前台 SPA**：Vite 6 + Vue 3.5 + vue-router 4 + Pinia —— 38 视图（首页/目录/商品/购物车/结算/成功/登录注册/账户中心 7 页/搜索/物流/博客/画廊/推荐/积分/订阅/礼品卡/组合/促销/联名/关于/联系/FAQ/教程/尺码/政策页×4/退订/404）；StoreLayout 布局（公告栏/Mega Menu/页脚/购物车抽屉/搜索弹窗/AI 客服/Cookie 同意/欢迎与 EXIT 弹窗/移动端 Tabbar）。
- **web/admin 后台 SPA**：同栈 13 视图（登录/看板/订单/详情/退货换货/工单/商品/编辑/库存/营销/内容/会员/设置）+ AdminLayout 折叠侧栏；纯 Cookie 会话（gm_admin_token）。
- **状态管理**：Pinia stores（ui toast/弹窗/抽屉、auth Cookie 会话、cart 服务端权威）替代全局 G 对象；i18n 改响应式（切换不再整页刷新）。
- **服务端挂载**：SPAStaticFiles（404 回落 index.html 支持前端 history 路由）；/admin-login.html 服务端 307 → /admin/；旧 *.html URL 由前端路由 LEGACY 映射表重定向。
- **Dockerfile 多阶段**：node:22-alpine 构建双 SPA → python:3.13-slim 运行。
- **run_all.ps1**：frontend-verify 步骤改为双 SPA vite build（编译即校验）。

### Removed
- 旧静态站 51 页 HTML + assets（app.js/chrome.js/i18n.js/api.js/admin.js 等 ~150KB JS）；file:// 双模式演示通道（SPA 需起服务，local 演示模式退役）。

### 回归
- 后端 20 套不受影响（纯 API 契约未动）；双 SPA vite build 通过（client gzip 58KB / admin gzip 40KB）；SPA 回落/静态资源/旧链重定向冒烟通过。
## [0.2.0] · 前后台正式分离（结构重构）

### Changed
- **前端物理拆分**：`prototype/` → `web/client/`（前台门店，挂载 `/`）+ `web/admin/`（管理控制台，挂载 `/admin`），两个自含静态站（各自 assets），后台可整体搬独立域名托管（`window.GM_ADMIN_API_BASE` 配 API 基址 + 服务端 `GM_ALLOWED_ORIGINS` CORS 白名单 + `GM_COOKIE_SECURE`）。
- **鉴权改造**：登录/注册响应写 HttpOnly Cookie——前台 `gm_token`（SameSite=Lax）/ 后台 `gm_admin_token`（SameSite=Strict + 短时效 `GM_ADMIN_TOKEN_HOURS`，默认 12h）；前端不再持有 token（localStorage 仅存非敏感用户概要）；Bearer 头保留（API 客户端/测试）。
- **后台专用登录端点**：`POST /api/account/admin/login`（仅 role≥2 放行，403 拒绝非管理员）+ `/api/account/admin/logout`；前台新增 `POST /api/account/logout`。
- **购物车服务端权威**：API 模式下 G.add/setQty/remove 全部服务端先行，本地 localStorage 降级为渲染缓存与 `file://` 演示兜底；`gm:cartupdated` 事件驱动 cart/checkout 页重渲染。
- **删除 SLUGS 硬编码**：新增 `GET /api/catalog/products-by-id/{id}`；cart 视图补 `product_id`/`variant_label`；product/gallery/wishlist/chrome 全部动态解析，换 seed 不断链。
- **CORS 收紧**：默认同源不加 CORS 中间件（原 `allow_origins=["*"]` 移除）；拆域时白名单启用 `allow_credentials`。
- **裁撤 `app/routers/` 单行重导出层**（18 文件）：main.py 直连 domains 装配；`@app.on_event` → lifespan。

### Added
- `web/admin/index.html` 入口重定向；admin 站点独立 api.js（API 基址可配）。
- `GM_COOKIE_AUTH` 开关（默认开；测试套件置 0 走纯 Bearer，20 套脚本已注入）。
- 根 `.gitignore`；清理 server/ 下 41 个测试残留文件（test_*.sqlite* / smoke_*.log）。

### Fixed
- admin 三处跨站死链（unsubscribe/account-order-detail 改绝对路径）。

- **测试独立目录**：20 套 test_*.py 从 `server/scripts/`（保留 seed/worker 运维脚本）迁至 `server/tests/`；run_all.ps1/README/.gitignore/.dockerignore 同步。
### 回归
- 20 套后端全过（test_a 24 / test_b 64 / test_c 78 / e2e 61 / sec 29 / concurrency 6 ...）；前端 verify（node --check x 6 资产 + 全部内联脚本 + 死链扫描）通过；浏览器旅程冒烟（游客车→Cookie 登录→合并→试算→下单→支付→后台 Cookie 管理→登出）通过。API.md 161 路径 167 操作（admin 73/user 30/public 58）。
## [0.16.0] · 第十八批演进 · 运费模板表驱动与批量导入

### Added
- **ShippingRate 影子表激活**：pricing 运费改为查表（国家精确→通配 `*` + 方式匹配最低价；free_over 覆盖全局免邮门槛；未命中回退 settings，seed 值与原默认一致零回归）——运营改表结算即时生效。
- 运费模板管理：`GET/POST /api/admin/trade/shipping-rates` + `PUT .../{id}`（价格/免邮门槛/时效/启停，审计日志，eta 倒挂 422）；公开 `GET /api/checkout/shipping-methods`（按方式聚合最低价+时效，checkout 可用）。
- settings 页运费 tab API 化：模板表（目的国/承运商/方式/运费/免邮/时效/启停开关）+ 新建/编辑弹窗；演示面板自动隐藏。
- **商品批量导入**：`POST /api/admin/catalog/products/bulk`（≤100 行，部分成功不回滚，逐行返回 ok/error）；商品页"📦 批量导入"弹窗——CSV 粘贴（slug,title,price,stock,category_id）→ 客户端解析 → 结果面板（成功/失败明细）。
- **捆绑折扣 settings 化**：bundle_2_off / bundle_3_off（默认 15/20 不变，0=关闭该档）；营销页捆绑 tab API 化（两档折扣实时编辑，改完结算立即生效）。

### Changed
- API.md 152→157 端点；test_a 23→24（bulk）、test_b 56→64（运费模板 8 断言：改价→preview 即时变化→还原、CA 新建、聚合、401/422/404 守卫）。

## [0.15.0] · 第十七批演进 · 后台编辑独立页与侧栏折叠

### Added
- **商品编辑独立页** `admin-product-edit.html`（?id=N 编辑 / 无参新建）：两栏全页布局——左：基本信息（8 行 Markdown 描述）/定价（含定时上架与清空定时）/变体管理（新增+行内编辑）；右：媒体（120px 主图即时预览）/组织标签/统计元信息；顶栏：状态徽标、前台预览（product.html?slug=）、上下架、保存。
- **订单详情独立页** `admin-order-detail.html`（?no=NSxxx）：两栏布局——左：商品明细（含已退/已换标记）+ 金额分项合计 + 完整时间线；右：订单信息卡/收件地址/履约操作区（发货/标记妥投/退款，两段式确认）。列表页"详情"与行点击均跳转。
- **后台侧栏折叠**：侧栏底部 ⏸ 按钮，点击收成 64px 图标栏（title 提示），localStorage 记忆（gm_side_min），全部 12 个后台页生效。
- 后端 `GET /api/admin/catalog/products/{product_id}` 单商品管理端点（test_a 新增 admin_product_get，23 用例）；API.md 151→152 端点。
- 前台 `product.html` 支持 `?slug=` 直达（原 `?id=1-12` 零回归；slug 命中本地 12 款时评价区联动，否则用响应 id）。

### Changed
- admin-products 列表页弹窗回归精简（编辑/新建跳独立页，local 模式保留演示弹窗）；admin-orders 删除已迁移的 ordModal 及死代码（文件 449→325 行）。

## [0.14.0] · 第十六批演进 · 后台商品编辑器全字段化

### Added
- **商品编辑器重做**（admin-products）：弹窗扩为 680px 分区编辑器——基本信息（标题/副标题/分类下拉/Markdown 描述）、定价（区间+划线价）、媒体（主图即时预览/图集≤8张/视频URL）、组织（标签/NEW/热销徽标）、变体管理；**新建同享全字段**，创建后自动打开编辑器引导补变体。
- 后端 schema 扩展：ProductCreateIn/ProductUpdateIn 支持 description_md/compare_at_price/images/video_url/is_new/is_best_seller/category_id（更新校验分类存在，images ≤8 张 422）；_admin_product_out 回吐全部新字段（test_a 新增 admin_product_rich_fields，20→22）。
- 商品列表强化：主图缩略图 + NEW/HOT 徽标 + 划线价展示；搜索（防抖 300ms 打服务端 q）与状态筛选（在售/草稿/已下架）真实接 API + 分页。
- 订单详情操作补全（admin-orders）：📦 标记妥投（status=3 时）+ 💸 退款（金额默认全额/可部分 + 原因入审计，两段式 .arm 确认，与退货页同款）。
- 会员画像风控（admin-members）：画像弹窗内风控状态下拉（正常/关注/黑名单）→ POST members/{id}/risk，保存后列表即时刷新。

### Changed
- 无端点增减（仍 151）；商品 PUT 语义为全字段覆盖式（未变化字段值相同不产生 diff 日志）。

## [0.13.0] · 第十四批+第十五批演进 · 一键演示与后台补全

### Added
- 一键起停 `start.ps1`/`stop.ps1`（环境检查/seed 探测/PID 管理/就绪探测/-Reset/-Restart）；`demo.ps1` 十步销售演示旅程（$31.10 标准口径实跑）；`上线检查清单.md`、`backup.ps1`/`restore-drill.ps1`（恢复演练已实操）。
- 热路径缓存（GM_CACHE=1 开启，默认关；catalog 列表/详情/分类/集合/搜索 + ai hot/recommend，11 个 admin 写失效钩子；test_cache 20 断言）。
- `GET /api/admin/catalog/variants` 变体列表端点（product_id 过滤 / q 搜 SKU+标题 / 分页；API.md 150→151 端点）。
- 后台商品编辑 API 化：编辑弹窗（标题/副标题/价格区间/划线价，PUT products/{id}）+ **变体管理**（列表/新增 POST variants/改价改安全库存停启用 PUT variants/{id}）。
- 后台库存中心 SKU 概览 API 化（水位条/规格/价格/现货/安全库存/停启用；"调整"预填变体直达手工调整弹窗；服务端搜索防抖 300ms + 分页）。

### Changed
- 后台右侧内容区字号梯度收紧（正文 14→13.5px、表格 14→13px、表头 12→11px、行距 padding 14→10px，10 页共享 admin.css 一次生效）。

### Fixed
- 登录全角字符拦截：全角字母/＠/．统一归一半角 + 小写化（ａｄｍｉｎ/ＯＰＳ 可登录）；邮箱框 type=email→text；邮箱/密码错误分开提示（回显实际输入与演示密码提醒）。
- 服务 pid 文件被失败启动覆盖为死 pid 的问题（以端口实际占用者为准修正）。

## [0.12.0] · 第十二批+第十三批演进 · 工程收尾与体验缝合

### Added
- 一键回归 `run_all.ps1`（18 套 + 前端 verify，汇总表/-Fast/-Suite 过滤）；`API.md` 自动生成（150 端点鉴权标注，`--check` 陈旧校验）；`CHANGELOG.md`。
- 安全响应头（nosniff/DENY/Referrer/Permissions/CSP）+ 静态资源缓存（资产 7 天/HTML no-cache）。
- 前台支付方式选择（/api/payments/methods 实时渲染 + 回落 toast）；商品中文 locale 联动（store/product/index，?locale=zh-CN 有译回退英文）。
- 购物车抽屉"猜你喜欢"接 /api/ai/recommend（空车热销兜底）；搜索联想接 /api/catalog/search；邮件模板运营预览（8 模板示例渲染 iframe）。
- `test_hardening` / `test_tplpreview` 套件。

### Changed
- 页脚/aria 18 处硬编码 i18n 化（93→111 键 en/zh 对称）；两段式确认统一切 `.arm` 类；login/register `.pw-wrap`、`.pay-pill` 上收 style.css（前台遗留债清零）。
- run_all 清单 17→18 套；test_tplpreview 归位 server/scripts（位置无关路径）。

### Fixed
- 无。

## [0.11.0] · 第十一批演进 · 支付矩阵与运营就绪

### Added
- **PayPalProvider**（Orders v2 结构桩：oauth + checkout/orders + PayPal-Request-Id 幂等；凭据缺失自动降级，monkeypatch 测试零外呼）；**Klarna** 经 Stripe `payment_method_types` 开关（`GM_STRIPE_KLARNA=1`）。
- Provider 选择矩阵（stripe > paypal > mock，半缺凭据跳过 + 一次性告警）；`GET /api/payments/methods` 公开支付方式；create-intent 支持可选 provider 参数。
- 后台换货队列 UI：admin-returns 双 tab（RMA | Exchanges）状态机操作、差价±着色、子状态 tab；admin-products ⏰ 定时上架徽标 + 改定时/清空弹窗。
- 运营日报 worker `daily_digest`：昨日 GMV/订单/退款/新客/6 项待办/Top3 商品/库存预警 → digest_recipients 循环投递（水位去重）。
- 商品多语言（最后一块影子表激活）：详情/列表 `?locale=zh-CN`（有译替换 + 回退 en-US）+ admin translations upsert/删除/列表。

### Changed
- test_payments 25→43（PayPal 结构桩/Klarna 开关/选择矩阵降级）。

**回归**：17 套 **547 断言**全绿（+digest 25）；51 表影子表全部激活；剩余均为外部凭据依赖（真实 Stripe/PayPal 密钥、Cloudflare 生产接入）。

## [0.10.0] · 第十批演进 · 履约域补齐

### Added
- **换货全流程**（exchanges 影子表激活）：用户侧 3 端点（创建/列表/详情，窗口与可换量校验、price_diff 三态）+ 后台 6 端点（approve 分流：diff>0→待差价→mark-paid / reject / ship 新变体原子扣减 / complete 旧变体回补）；前台 account-orders 三步换货向导。
- **到货通知**：stock-notify 三端点（售罄才可订阅/幂等/取消）+ worker `restock_notify`（回补→outbox→邮件）。
- **定时上架**：前台六处 repository 统一 `_visible()` 过滤 `published_at<=now`（admin 不过滤 + scheduled 徽标）+ worker `publish_scheduled`（水位线去重）。
- **邮件偏好中心**：GET/PUT `/api/account/email-preferences`（登录或 email+token 双通道），三开关部分更新、任一开=复订、与 worker 弃购合规联动。

**回归**：16 套 **534 断言**全绿（+exchanges 47 +stocknotify 29 +emailpref 13）；端点 135→**155**。

## [0.9.0] · 第九批演进 · P0 功能补齐

### Added
- **州级税表**（services/tax_rates.py）：50 州 + DC（CA 0.0735 对齐基线 / NY 0.08875 / OR·MT·NH·DE 免税），未命中回退 settings；preview（body.state）与 place（地址州）接通。
- **GDPR 导出/删除**：GET `/api/account/export`（全量 JSON + DataRequest 落库）；POST `/delete-request`（202 + 7 天宽限、重复 409、可撤销）；worker `process_data_requests` 到期匿化（订单脱敏、财务记录完整）。
- **变体级图片**：变体创建/编辑支持 images（≤6，整表替换）；商品详情批量出图；seed 7 张变体图。
- **UGC 公开上墙**：GET `/api/content/ugc`（status=1）+ gallery 瀑布流 + 匿名投稿表单（采用奖 100 积分）；product.html 变体切换联动主图画廊。

**回归**：13 套 **445 断言**全绿（+p0 32 +p0b 16）；零测试修改。

## [0.8.0] · 第八批演进 · 分层模块化重构

### Changed
- **八域四层重构**：`app/domains/{trade,member,catalog,promo,content,support,ops,ai}` × `router*（薄 HTTP）/ service*（业务事务）/ repository（纯数据访问）/ schemas（DTO）`，61 文件 5311 行，对齐微服务蓝图。
- `app/routers/*` 全部降级为 1 行 re-export shim（admin_ops 为四域组装）——main.py 零改动、旧导入路径全兼容。
- 重构纪律验收：**行为零变化**（端点面 135 条逐一比对 identical；分层自查 router 无直查 SQL、repository 无 HTTPException、跨域只走 service）。

**回归**：11 套 **397 断言零测试修改通过**；catalog 批查（8 SQL/页）与 dashboard 聚合（≤25 查询）性能红线复验保持。

## [0.7.0] · 第七批演进 · 安全审计修复 + 索引性能 + P0 资损修复

### Fixed
- **工单 IDOR**：任意邮箱枚举工单对话 → 登录仅自查（他人 403）/ 游客 ticket_no+email 双因子；login 401 文案统一防账户存在性枚举；JWT role 从 DB 读（payload 篡改无效）。
- **P0 资损——礼品卡免费铸造**：purchase 改为创建 status=0 待激活卡 + 待付订单，支付成功回调激活 + ledger；前端购买流自动 intent→mock-pay→展示激活码。
- **P0 资产——积分只冻不解**：worker 新任务 `unfreeze_points`（退货期满且无未完结 RMA 的冻结行置 frozen=0，每轮上限 500）。
- **退订 token 宽限收紧**：HMAC token 或登录本人二选一（匿名裸 email → 400 token_required）。

### Added
- 索引补齐：referrals `uk_code_email`(unique) + discount_redemptions `idx_code_email`（迁移 11e1cc89ae3a）；20k 商品/50k 订单规模 EXPLAIN 复验全部命中。
- N+1 修复：catalog 列表 101 SQL→8 SQL（-92%）、admin_trade 回补批查、dashboard 聚合化。

**回归**：11 套 **397 断言**全绿（+sec 29 攻击者视角 +perf 29）。

## [0.6.0] · 第六批演进 · 硬化

### Fixed
- **并发假性缺货**（30 并发秒杀仅 2-3 单成交、27 人收到假 409）：乐观锁 `WHERE version=:v` 无重试 → 预扣改单语句原子扣减（`stock=stock-qty WHERE stock>=qty`）；30 并发恰好售罄 10 单/409=20/库存归零。

### Added
- 备份恢复**首次演练**：backup.ps1 实跑（52 表）→ 临时库恢复 → 行数/CHECKSUM/抽查单/users 全字段比对 → 应用级验证（drill 库起 uvicorn 均 200）；固化 `scripts/restore-drill.ps1` 一键化。
- seed 演示库充实（--reset 可重复）：16 用户 / 26 订单（14 天窗 9 个非零日）/ 49 评价 / 5 RMA 全状态 / 7 工单 / popup 转化 26%。
- scripts/test_concurrency.py 6 用例：超卖竞态/同用户幂等/并发支付积分无重/限流/P95 只读压测/窗口恢复。

**回归**：9 套 **338 断言**全绿（+并发 6）。

## [0.5.0] · 第五批演进 · 收官

### Added
- **E2E 全旅程套件**（test_e2e.py 61 断言，发版必跑）：逛→注册→地址/愿望单→游客车→merge→折扣试算($31.10)→下单→支付→积分冻结→推荐有礼双份奖励→工单→后台发货/送达→RMA→礼品卡→worker 对账→退订→/metrics。
- 看板真实趋势：dashboard `daily`（14 天 GMV/订单序列）+ `reconcile`（最近对账行）+ `low_stock_top`；前端全零降级演示 + 角标。
- 前台接线收官（累计 34 页）：account-address 地址簿 CRUD、subscribe 双态、index New Arrivals 实时化。

### Fixed
- **RMA 退款不含税/折扣分摊**（E2E 抓出）：旧口径永远到不了 REFUNDED → 改为按订单实付比例折算（质量原因加退运费 499，封顶 grand_total）。
- worker 对账退款日误报（payments_gross 放宽为 status IN 1,3,4 当日实收口径）；JWT dev secret 长度 <32 警告。

**回归**：8 套 **332 断言**全绿。

## [0.4.0] · 第四批演进 · 账户缺口 + 可观测性

### Added
- **账户侧缺口端点 10 个**：推荐返利（确定性派生码 GLOW-sha256[:8]、邀请脱敏、on_order_paid 钩子双份 1000 分、防自邀）；订阅盒 MVP 全状态机（active/pause/resume/skip/cancel）；HMAC 退订；防枚举密码重置（恒 200 + purpose=pwreset JWT）；礼品卡购买三档。
- **可观测性**（core/observability.py，main.py 预挂零侵入）：X-Request-Id 透传/生成/回写 + glowmag.access 单行结构化日志；GET /metrics（Prometheus 文本，动态段折叠 {id}）；应用级滑动窗限流（login 60/min、register 30、password-reset 20、mock-pay 120、tickets 30，超限 429 + Retry-After）。
- 前台再接线 11 页（账户 6 + 内容 5，累计 31 页）：wishlist/rewards/refer/gift-cards/unsubscribe/login-forgot + faq/blog·blog-post/contact/search。

**回归**：271 断言全绿（+refsub 38 +obs 17）。

## [0.3.0] · 第三批演进 · Stripe 就绪 + 弃购三封 + Compose

### Added
- **Provider 支付抽象**（services/payment_provider.py）：Mock（默认）/Stripe（真实 SDK）；`GM_STRIPE_KEY` + `GM_STRIPE_WEBHOOK_SECRET` 零代码切换；webhook `Webhook.construct_event` 验签（失败 400 invalid_signature）+ 本店事件校验；stripe 模式下 mock-pay 409。
- **弃购三封阶梯**（worker.scan_abandoned_carts）：1h ABANDON10（9 折）→ 24h ABANDON15（85 折）→ 72h 无码+最小库存紧迫感；`abandoned_mails_sent` 兼作阶段号 CAS 原子推进；退订/关闭偏好全序列合规跳过。
- **容器化部署**：server/Dockerfile（python:3.13-slim、非 root、HEALTHCHECK）+ docker-compose.yml（mysql8 + api + worker + migrate profile，密钥强校验、512m 限幅）+ .env.example + scripts/backup.ps1（mysqldump+gzip+14 天保留）+ deploy.md（首次部署 8 步/Cloudflare/恢复演练/故障手册）。

### Changed
- requirements.txt 补 pymysql/cryptography/alembic。

**回归**：**216 断言**全绿（+worker 37 +payments 25）。

## [0.2.0] · 第二批演进 · Alembic + worker + AI + 后台全接

### Added
- **Alembic 接管建表**：migrations/（env.py 挂 Base.metadata + GM_DB 优先）；初始版本 `7bab2b9ff482 init 51 tables` 空库验证；只前向纪律（模型改动必须伴随迁移）。
- **后台任务 worker**（scripts/worker.py 独立进程，MySQL GET_LOCK 防多实例，--once/--loop）：outbox 消费（6 类邮件渲染投递）、超时关单（PENDING>30min + 库存 RELEASE 回补）、弃购扫描、积分过期、每日对账（不平置 status=1 告警）。
- **AI 服务模块**（app/routers/ai.py）：recommend（同类→标签→热销→新上架四级降级）/ hot 热销榜 / chat（中英意图识别、订单脱敏单号只回后 4 位、未命中转人工）；GlowBot 双模式联通（2s 超时回落本地关键词表）。
- 后台最后 3 页接线（17+3 页全联通）：admin-marketing 折扣码/弹窗 CRUD、admin-content 审核+FAQ/博客 CRUD（补 8 端点）、admin-settings 6 键真实读写。

**回归**：**181 断言**全绿（+worker 27）。

## [0.1.0] · 首发 · FastAPI 单体全链路

### Added
- **FastAPI 单体**（Python 3.13，按域分包=未来微服务边界）：18 路由模块、11 域 51 表 SQLAlchemy 模型逐列对齐《数据库设计文档-完整版》；定价引擎（折扣码/捆绑/积分/礼品卡/运费/税纯函数）、积分账务流水驱动、折扣码校验唯一闸门。
- **$31.10 标准验证订单全链路**：Bare Gems + Cherry Bomb − WELCOME20 $6.00 + 运费 $4.99 + 税 $2.13 = $31.10、311 积分冻结（seed 内置，前后台四页对齐）。
- **库存四态流水**（place 预扣→支付实扣→取消释放→退货回补，stock_movements 唯一真相）+ **RMA 状态机**（申请→批准→在途→收货回补→退款，质量问题退运费）。
- **mock-pay 模拟支付**：支付状态机/幂等/退款/对账链路全部真实，只把"调第三方"换成模拟端点；outbox_events 落库。
- **前后端真联通**：prototype/assets/api.js 双模式桥接（api/local，1.5s 探测 /api/health），17 页联通（checkout 全链路/账户/后台 7 页）。
- 落地决策：美分 int 金额、DATETIME 秒级 naive UTC（防 MySQL 四舍五入）、READ COMMITTED、JWT + X-Cart-Token 游客车；MySQL 踩坑实录 5 条写入文档。

**回归**：**154 断言**全绿（A 20 + B 56 + C 78）+ 前端 verify.ps1 + jsdom 双模式 125 项。

---

## 附：回归断言数演进（各批收官口径）

| 批次 | 版本 | 断言数 | 增量来源 |
|---|---|---|---|
| 首发 | 0.1.0 | 154 | A 20 + B 56 + C 78 |
| 第二批 | 0.2.0 | 181 | +worker 27 |
| 第三批 | 0.3.0 | 216 | +worker 37（弃购细化）+payments 25 |
| 第四批 | 0.4.0 | 271 | +refsub 38 +obs 17 |
| 第五批 | 0.5.0 | 332 | +E2E 61×2 |
| 第六批 | 0.6.0 | 338 | +concurrency 6 |
| 第七批 | 0.7.0 | 397 | +sec 29 +perf 29，refsub 38→39 |
| 第八批 | 0.8.0 | 397 | 重构零行为变化（零测试修改通过） |
| 第九批 | 0.9.0 | 445 | +p0 32 +p0b 16 |
| 第十批 | 0.10.0 | 534 | +exchanges 47 +stocknotify 29 +emailpref 13 |
| 第十一批 | 0.11.0 | 547 | payments 25→43、新增 digest 25（收官口径见 MVP 文档 §19.5） |

演进线：**154 → 181 → 216 → 271 → 332 → 338 → 397 → 397 → 445 → 534 → 547**
