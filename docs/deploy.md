# GLOWMAG 部署文档（方案零 · 单机 Docker Compose 起步）

> 对齐《高可用架构设计-v2》§7.0「单机起步 + 穷人高可用纪律」。本机（Windows 开发机）无 Docker，全部配置经语法级验证；首次上线时按本文档在 Linux 服务器逐条执行即完成交付。

## 0. 交付物清单

```
nailshop/（仓库根）
├── docker-compose.yml       # §7.0 编排：mysql / api / worker / migrate(profile deploy)
├── .env.example             # 环境变量样例（cp 为 .env 填写，密钥永不入库）
├── docs/
│   └── deploy.md            # 本文档
├── scripts/
│   └── backup.ps1           # Windows 管理机 MySQL 备份（异地纪律 §5.3）
└── server/
    ├── Dockerfile           # api/worker/migrate 共用镜像（python:3.13-slim 单阶段，非 root）
    └── .dockerignore        # 构建上下文裁剪（首次部署 cp 到仓库根生效，见 §2）
```

§7.0 纪律对照：

| 架构文档纪律 | 本交付落地 |
|---|---|
| 单机 Compose 起步，不加机器拼集群 | 4 服务 1 卷 1 网，全部 `glowmag-*` 命名 |
| 入口最小化 | api 仅绑 `127.0.0.1:8000`；mysql 3306 不映射宿主，仅内网 `glowmag-net` |
| 资源上限防互杀 | mysql / api 各 `memory: 512m`（大促调优见 §5） |
| 每日备份必须异地 | §4：服务器 cron + 管理机 backup.ps1 + R2/S3 上传 |
| 季度恢复演练 | §4.3：临时容器演练步骤 |
| 密钥外置、代码零硬编码 | compose `${VAR:?}` 强校验，缺失密钥拒绝启动 |

## 1. 前置条件

1. **服务器**：4C8G 及以上，系统盘 40G+，Debian 11/12 或 Ubuntu 22.04+，时间同步（`timedatectl` 确认 NTP）。
2. **Docker**：Docker Engine ≥ 24 与 Compose v2 插件（`docker compose version` 可用即 v2）。
3. **域名接入 Cloudflare**（§7.0「入口交给 Cloudflare」）：域名 NS 托管至 CF，源站只回环可达，公网入口由 CF 提供 TLS/WAF/CC 防护。
4. **安全组/防火墙**：仅开放 22（SSH）、80/443（反代或 cloudflared 方案）；**8000 与 3306 绝不对公网开放**。

## 2. 首次部署

以下命令均在服务器仓库根执行（示例 `/opt/nailshop`）。

```bash
# 0) 克隆代码
git clone <仓库地址> /opt/nailshop && cd /opt/nailshop

# 1) 生成 .env（密钥生成见 .env.example 内注释）
cp .env.example .env
openssl rand -hex 32          # 填入 GM_JWT_SECRET
openssl rand -hex 16          # 填入 GM_MYSQL_ROOT_PASSWORD / GM_MYSQL_PASSWORD

# 2) .dockerignore 就位（Docker 只认构建上下文根的 .dockerignore）
cp server/.dockerignore .dockerignore

# 3) 构建镜像（api/worker/migrate 共用）
docker compose build

# 4) 先起 MySQL 并等待 healthy（约 20~30s）
docker compose up -d mysql
docker compose ps             # STATUS 显示 (healthy) 后继续

# 5) 建表迁移（migrate 为 profile "deploy" 一次性服务，不常驻）
docker compose --profile deploy run --rm migrate

# 6) 首次可选：灌入种子数据（商品/折扣码/演示账号，对齐 prototype 基线口径）
docker compose run --rm api python scripts/seed.py

# 7) 起全部常驻服务
docker compose up -d

# 8) 冒烟验证
curl -s http://127.0.0.1:8000/api/health   # 期望 {"ok":true,"service":"glowmag-api",...}
curl -sI http://127.0.0.1:8000/            # 期望 200（prototype 静态首页，随镜像分发）
```

### 2.1 Cloudflare 接入（二选一）

- **方案 A（推荐）cloudflared Tunnel**：零开放端口。CF Zero Trust → Networks → Tunnels 创建 Tunnel 取得 Token，在仓库根 docker-compose.yml 末尾追加：

  ```yaml
    tunnel:
      image: cloudflare/cloudflared:latest
      container_name: glowmag-tunnel
      restart: unless-stopped
      command: tunnel --no-autoupdate run --token ${CF_TUNNEL_TOKEN:-}
      networks: [glowmag-net]
  ```

  `.env` 追加 `CF_TUNNEL_TOKEN=`；CF 控制台 Public Hostname 指向 `http://api:8000`（容器内网直连，不经过宿主端口）。随后 `docker compose up -d`。

- **方案 B 源站反代**：宿主安装 Caddy（自动 HTTPS），`Caddyfile` 一行 `your.domain.com { reverse_proxy 127.0.0.1:8000 }`，CF DNS 开代理（橙云），SSL 模式 Full (strict)（源站证书可用 CF Origin CA）。

## 3. 日常运维

**发布（滚动更新）**：

```bash
cd /opt/nailshop && git pull
docker compose build
docker compose --profile deploy run --rm migrate   # 有迁移时必须先行，再起新代码
docker compose up -d                               # 只重建镜像变化的服务，秒级滚动
```

**常用命令**：

```bash
docker compose ps                          # 状态总览（healthy 与否）
docker compose logs -f --tail=100 api      # 跟踪 API 日志
docker compose logs -f worker              # 后台任务日志（outbox/关单/对账）
docker compose exec mysql sh -c \
  'exec mysql -uglowmag -p"$MYSQL_PASSWORD" glowmag'   # 进业务库（密码不出容器环境）
docker compose restart api                 # 单服务重启
docker compose down                        # 停全部（数据卷 glowmag-mysql 保留）
```

## 4. 备份与恢复（穷人高可用纪律，§5.3 / §7.0）

**核心纪律：本地备份 ≠ 备份。每日备份完成后必须上传异地（R2/S3），未确认上传成功不算完成当日运维。**

### 4.1 服务器侧每日备份（Linux cron）

```bash
mkdir -p /var/backups/glowmag
crontab -e   # 追加（每日 03:00 导出 → gzip → rclone 上传 R2 → 校验后清理 14 天前本地文件）
0 3 * * * cd /opt/nailshop && docker compose exec -T mysql sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --quick --hex-blob --routines --triggers --events glowmag' | gzip > /var/backups/glowmag/glowmag_$(date +\%Y\%m\%d).sql.gz && rclone copy /var/backups/glowmag/glowmag_$(date +\%Y\%m\%d).sql.gz r2:glowmag-backups/$(date +\%Y)/ && find /var/backups/glowmag -name 'glowmag_*.sql.gz' -mtime +14 -delete
```

### 4.2 Windows 管理机备份（scripts/backup.ps1）

参数化（host/user/password/db/输出目录/保留天数），自动探测 mysqldump，gzip 压缩，`-WhatIf` 演练支持：

```powershell
# 手动执行（密码走环境变量避免明文）
$env:GM_MYSQL_PASSWORD = '...'
.\scripts\backup.ps1 -HostName 127.0.0.1 -BackupDir D:\backups\glowmag -RetainDays 14

# 每日 03:00 计划任务（SYSTEM 账户；GM_MYSQL_PASSWORD 需设为机器级环境变量）
schtasks /Create /TN "GLOWMAG-Backup" /SC DAILY /ST 03:00 /RU SYSTEM /TR "powershell -NoProfile -ExecutionPolicy Bypass -File D:\ops\nailshop\scripts\backup.ps1 -HostName <db主机> -BackupDir D:\backups\glowmag"
```

### 4.3 季度恢复演练（§5.3 纪律，实操留档）

**不碰生产卷**，在临时容器中验证备份可用性：

```bash
# 1) 从 R2 取最近一次备份并解压
rclone copy r2:glowmag-backups/2026/ /tmp/drill/ && gunzip /tmp/drill/glowmag_*.sql.gz

# 2) 起一次性 MySQL（仅回环 3307）
docker run -d --name glowmag-drill -e MYSQL_ROOT_PASSWORD=drill -p 127.0.0.1:3307:3306 mysql:8.0
sleep 30

# 3) 建库并恢复
docker exec -i glowmag-drill mysql -uroot -proot \
  -e "CREATE DATABASE glowmag CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
docker exec -i glowmag-drill mysql -uroot -proot glowmag < /tmp/drill/glowmag_*.sql

# 4) 抽查关键表（行数 > 0、最近订单/商品可查）
docker exec -i glowmag-drill mysql -uroot -proot glowmag \
  -e "SELECT COUNT(*) products FROM products; SELECT COUNT(*) orders FROM orders;"

# 5) 清理并留档：docker stop glowmag-drill；记录演练日期/耗时/问题至运维日志
```

## 5. 升级与扩容路径

| 场景 | 动作 |
|---|---|
| 大促流量 | api `deploy.resources.limits.memory` 512m→1g；mysql 512m→1g；api 容器 command 覆盖 `--workers 4`；CF 侧开缓存规则（静态站全量缓存） |
| MySQL 8.0 → 8.4 | **禁止原地升级卷**：起 8.4 新容器按 §4.3 流程 dump → restore → 切换 compose 镜像标签，灰度观察 3 天 |
| 单机扛不住 | **不加机器拼 Compose**（多机 Swam/compose 不在本方案纪律内）：迁移 K8s（Helm 化 api/worker + 云 RDS + 托管 Ingress），拆分路径见《高可用架构设计-v2》§7.2 |
| 磁盘增长 | `docker system prune -f` 清构建缓存；备份按保留策略滚动；数据卷迁移用 `docker run --rm -v` 双卷 cp，停机窗口内完成 |

## 6. 故障手册

| 症状 | 排查 | 处置 |
|---|---|---|
| api 重启循环 | `docker compose logs api` | 多为 `.env` 密钥缺失/错误（compose 启动即 `${VAR:?}` 拦截）或迁移未跑（表不存在）→ 修 `.env` / 补跑 §2 步骤 5 → `docker compose up -d` |
| CF 502/504 | `curl -s http://127.0.0.1:8000/api/health` | 本地通 → 查 tunnel/反代；本地不通 → 看 api 日志按上一行处置 |
| worker 不消费 | `docker compose logs worker` | 看 MySQL 连通性；日志出现 `lock ... held by another worker` 属 GET_LOCK 单实例保护，确认无重复 worker 容器即可 |
| mysql OOM/被杀 | `docker stats`、`dmesg | grep -i oom` | 上调 memory limit（§5），必要时 my.cnf 调低 `innodb_buffer_pool_size`；重启后 `docker compose restart api worker` |
| 磁盘满 | `df -h`、`docker system df` | 按 §5 磁盘行清理；勿删 `glowmag-mysql` 卷 |
| 迁移失败 | `docker compose --profile deploy run --rm migrate` 看 traceback | 修模型/revision 后重跑；`docker compose exec mysql ... alembic_version` 对齐 `alembic current` |
| 忘记 MySQL 密码 | `.env` 即当时密码来源 | 若 root 丢失：停 mysql → 临时加 `--skip-grant-tables` 命令行启动重置 → 恢复编排（留操作记录） |
| 怀疑密钥泄露 | — | 立即轮换 `.env` 中对应值并 `docker compose up -d`（GM_JWT_SECRET 轮换=全员重新登录，属预期） |

## 7. 备份恢复演练记录（§4.3 纪律实操留档）

> 纪律原话：**没有验证过的备份等于没有备份。** 本节由 `scripts/restore-drill.ps1` 产出的核验结论自动对照填写，每次演练追加一段。

### 7.1 首次实战演练（2026-08-16，本机 Windows + MySQL 8.0.22）

- **备份产物**：`C:\Users\lihui\AppData\Local\Temp\opencode\drill\glowmag_20260816_131128.sql.gz`（13,549 B / 解压 81,183 B；`backup.ps1 -HostName 127.0.0.1 -User glowmag -Database glowmag` 产出）
- **恢复目标**：临时库 `glowmag_drill`（root 建库 + 授权 glowmag@127.0.0.1/localhost；python gzip 流式解压 → `mysql < dump.sql` 导入 3.4s；演练结束已 DROP）
- **核验结果**：

| 核验项 | 生产库 glowmag | 恢复库 glowmag_drill | 结论 |
|---|---|---|---|
| 表数量 | 52 | 52 | PASS |
| 行数 products | 13 | 13 | PASS |
| 行数 users | 4 | 4 | PASS |
| 行数 orders | 3 | 3 | PASS |
| 行数 reviews | 0 | 0 | PASS |
| 抽查订单 NS260728D4E5F6 | grand_total=3110 | grand_total=3110 | PASS |
| CHECKSUM TABLE users | 716888312 | 716888312 | PASS |
| users 全字段比对（4 行×9 列） | — | 完全一致 | PASS |
| 应用级验证（GM_DB 指向恢复库起 uvicorn :8020） | /api/health 200 + /api/catalog/products/bare-gems 200（price_min=1599） | 同左 | PASS |

- **耗时**：手工首跑约 2 分钟（备份 0.6s + 导入 3.4s + 核验/应用验证/清理）；`restore-drill.ps1` 复跑全程 **10.4s**
- **结论**：备份**可恢复且可用**（不止"数据在"，应用能对恢复库正常提供服务）；脚本二次干跑用同一备份重演通过，验证演练可重复
- **已知噪声**：mysqldump 对 `glowmag` 用户报 `PROCESS privilege ... dump tablespaces` 警告（单库逻辑恢复不需要 tablespace 信息，数据完整无损）；如需消警可在服务器侧备份账号加 PROCESS 权限

### 7.2 一键演练脚本 scripts/restore-drill.ps1

把 §4.3 手工步骤固化为流水线：建临时库 → gunzip 解压 → mysql 导入 → 数据核验（表数/关键表行数/抽查订单/CHECKSUM/全字段比对）→ 应用级验证（临时 uvicorn 打 /api/health 与商品接口）→ 自动清理（DROP 临时库 + 杀临时端口），末尾输出核验结论表，任一项 FAIL 退出码 1。

```powershell
# 常规演练（用最近一次备份；root 密码走 GM_MYSQL_ROOT_PASSWORD 或 -RootPassword）
.\scripts\restore-drill.ps1 -BackupFile C:\Users\lihui\AppData\Local\Temp\opencode\drill\glowmag_20260816_131128.sql.gz

# 保留临时库现场排障（事后务必手动 DROP DATABASE glowmag_drill）
.\scripts\restore-drill.ps1 -BackupFile <备份.sql.gz> -KeepDb

# 常用参数：-SourceDb glowmag -TempDb glowmag_drill -HostName 127.0.0.1 -AppPort 8020
#           -SpotOrderNo/-SpotGrandTotal/-SpotSlug/-SpotPrice（抽查样本随数据演进更新）
```

### 7.3 下次演练建议

- **节奏**：季度一次（下次 **2026-11-16 前**），大版本升级/迁移工具变更/备份策略调整后**加练一次**
- **用最近的异地备份**演练（从 R2 `rclone copy` 拉回）而非只测本地文件——异地副本才是灾备真正依赖的那份
- 随业务数据演进同步更新 `-SpotOrderNo` 等抽查样本（选最近一日的真实订单），并把结果表追加到本节留档
