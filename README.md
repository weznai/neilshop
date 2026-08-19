# GLOWMAG · 指甲电商独立站（Press-on Nails + Magnetic Lashes DTC）

从设计文档 → 高保真原型 → FastAPI+MySQL 前后端真联通的完整落地。

## 架构（v0.3 · Vue 3 SPA 前后台）

```
web/
  client/   前台门店 SPA（Vite + Vue 3 + Router + Pinia，38 视图，挂载于 /）
  admin/    管理控制台 SPA（同栈，13 视图，挂载于 /admin，会话独立）
server/     FastAPI 单体（按域分包 domains/*，18 域路由 160+ 端点，51 表 MySQL + Alembic）
```

- **前端工程**：Vue 3.5 SFC + vue-router 4（history 模式，旧 `*.html` URL 自动重定向）+ Pinia 3 stores（ui/auth/cart）；npm workspace 统一管理（一条 `npm run build` 双 SPA 统一输出 `web/dist`：client 在根、admin 在 `/admin` 子目录，FastAPI 单目录挂载）
- **鉴权**：HttpOnly Cookie（前台 `gm_token` / 后台 `gm_admin_token` 独立会话，后台 SameSite=Strict + 短时效；响应体仍返回 token 供 API 客户端/测试 Bearer 使用）
- **购物车**：Pinia cart store 服务端权威（add/setQty/remove 全部服务端先行）
- **拆分缝**：`window.GM_API_BASE` / `window.GM_ADMIN_API_BASE` 可配 API 基址 + 服务端 `GM_ALLOWED_ORIGINS` CORS 白名单 → 任一端整体搬独立域名只需改配置
- **开发**：`npm run dev:client`（:5173）/ `npm run dev:admin`（:5174），/api 代理 → :8000；**生产**：`npm run build` → `web/dist` 由 FastAPI 单目录 SPA 挂载（未命中按前缀回落 client/admin 各自 index.html）

## 目录导航

| 路径 | 内容 |
|---|---|
| `web/client/` | 前台 SPA（src/views 38 视图 + layouts + components + stores） |
| `web/admin/` | 后台 SPA（src/views 13 视图 + AdminLayout 侧栏） |
| `server/` | FastAPI 单体（domains 8 域 × router/service/repository，51 表 MySQL + Alembic） |
| `server/scripts/` | seed 种子 / worker 定时任务 |
| `server/tests/` | 20 套回归测试（test_a/b/c/e2e/sec/concurrency...，run_all.ps1 一键全量） |
| `docs/deploy.md` + `docker-compose.yml` + `.env.example` | 部署交付（方案零：单机 Compose + 穷人高可用纪律；Dockerfile 多阶段 node 构建 + python 运行） |
| `scripts/backup.ps1` | MySQL 备份（gzip + 14 天保留 + 异地提醒） |
| `docs/MVP实现说明-MySQL版.md` | **落地总账**：技术决策/模块映射/API 总表/踩坑实录/各批演进（§1-§12） |
| `docs/` 其余 `*.md` | 设计文档（系统设计/详细设计/数据库/高可用/微服务演进/建站执行/业务全景等 9 份） |

## 快速开始

一键演示（推荐）——根目录 PowerShell 三连：

```powershell
.\start.ps1          # 一键启动：seed 检测 → uvicorn :8000 → worker → 自动开浏览器
.\scripts\demo.ps1   # 销售演示旅程：逛/注册/游客车合并/WELCOME20 试算($31.10)/下单支付/积分/
                     #   AI 客服/后台发货/退货退款/指标对账（-SkipReturn 跳退货；-Port 换端口）
.\stop.ps1           # 收尾：停 uvicorn 与 worker
```

手动方式：

```powershell
cd server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt    # 国内: -i https://mirrors.aliyun.com/pypi/simple/
.venv\Scripts\python.exe scripts\seed.py         # 建表+种子（MySQL: glowmag/glowmag123@127.0.0.1）
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload

# 前端（npm workspace：一条命令安装 + 双 SPA 统一构建到 web/dist）
npm install
npm run build

# 前端开发模式（热更新，另开两个终端）
npm run dev:client                        # :5173，/api 代理到 :8000
npm run dev:admin                         # :5174
```

- 前台 http://localhost:8000/ · API 文档 /docs · 后台 http://localhost:8000/admin/
- 种子账号（密码 `glowmag123`）：admin@ / ops@ / cs@ / emma@glowmag.com（后台登录仅放行 role≥2）
- 演示订单 NS260728D4E5F6（$31.10，四页对齐口径）
- 定时任务：`.venv\Scripts\python.exe scripts\worker.py --loop --interval 60`

## 回归

```powershell
# 一键全量（推荐）：19 套后端 + 前端 verify，汇总表 + 总耗时，任一失败 exit 1
powershell -File run_all.ps1            # -Fast 跳过慢速并发套件 / -Suite test_a,test_b 过滤

# 单套细跑
cd server
.venv\Scripts\python.exe tests\test_e2e.py       # 61 · 全旅程 E2E（发版必跑）
.venv\Scripts\python.exe tests\test_a.py         # 24 · 账户/目录/购物车/商品富字段编辑/批量导入
.venv\Scripts\python.exe tests\test_b.py         # 64 · 交易/支付/退货/库存/运费模板
.venv\Scripts\python.exe tests\test_c.py         # 78 · 营销/内容/客服/运营
.venv\Scripts\python.exe tests\test_worker.py    # 37 · 定时任务/对账
.venv\Scripts\python.exe tests\test_refsub.py    # 38 · 推荐/订阅/礼品卡/改密
.venv\Scripts\python.exe tests\test_payments.py  # 43 · 支付 Provider 抽象（Stripe/PayPal/Klarna）
.venv\Scripts\python.exe tests\test_obs.py       # 17 · 可观测性/限流
.venv\Scripts\python.exe tests\test_concurrency.py  # 6 · 并发竞态/超卖/压测（较慢，含 61s 等待）
.venv\Scripts\python.exe tests\test_sec.py       # 29 · 越权/IDOR/JWT 攻击者视角
.venv\Scripts\python.exe tests\test_perf.py      # 29 · 索引命中/N+1/EXPLAIN
.venv\Scripts\python.exe tests\test_p0.py        # 32 · 州级税表 + GDPR 导出/删除/匿化
.venv\Scripts\python.exe tests\test_p0b.py       # 16 · 变体图片 + UGC 公开接口
.venv\Scripts\python.exe tests\test_exchanges.py # 47 · 换货全流程状态机
.venv\Scripts\python.exe tests\test_stocknotify.py  # 29 · 到货通知 + 定时上架
.venv\Scripts\python.exe tests\test_emailpref.py # 13 · 邮件偏好中心
.venv\Scripts\python.exe tests\test_digest.py    # 25 · 运营日报 + 商品多语言
.venv\Scripts\python.exe tests\test_hardening.py # 17 · 安全响应头 + 静态缓存
.venv\Scripts\python.exe tests\test_cache.py     # 20 · 热路径缓存（需 GM_CACHE=1，脚本内自设）
.venv\Scripts\python.exe tests\test_tplpreview.py # 12 · 邮件模板预览
```

可选：`GM_CACHE=1` 开启目录/AI 热路径缓存（TTL 默认 30s，写操作自动失效；默认关闭不影响测试基线）。

另：`scripts/gen_api_docs.py [--check]` 生成/校验 docs/API.md（149 端点鉴权标注）。

备份演练：`scripts\backup.ps1` 备份 → `scripts\restore-drill.ps1 -BackupFile <gz>` 一键恢复核验（见 docs/deploy.md §7）。

生产部署见 `docs/deploy.md`（Cloudflare 前置 + Compose，迁移 Alembic 只前向）。
