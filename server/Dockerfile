# GLOWMAG API/worker/migrate 共用镜像 —— 对齐《高可用架构设计-v2》§7.0 方案零
# 多阶段：stage1 node 构建前后台 Vue SPA → stage2 python 运行（含 dist 静态挂载）
# 注意：构建上下文 = 仓库根（web/ 与 server/ 需进镜像），本文件位于 server/Dockerfile

# ---------- stage 1: web build（npm workspace：client + admin 一次安装、一条命令、统一输出 web/dist） ----------
FROM node:22-alpine AS webbuild
WORKDIR /web
COPY package.json package-lock.json ./
COPY web/client/package.json web/client/
COPY web/admin/package.json web/admin/
RUN npm ci --no-fund --no-audit
COPY web/client web/client
COPY web/admin web/admin
RUN npm run build

# ---------- stage 2: runtime ----------
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC \
    PIP_NO_CACHE_DIR=1

# 非 root 运行（§7.0 最小权限纪律）
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /usr/sbin/nologin appuser

WORKDIR /app/server

# 依赖层先行（层缓存：requirements.txt 未变则命中缓存跳过 pip install）
# 注：requirements.txt 为既有文件不可改 —— pymysql[rsa](MySQL 驱动+caching_sha2 认证)
#     / alembic(容器内迁移) / tzdata(TZ 时区) 由镜像层补齐
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt "pymysql[rsa]" alembic tzdata

# 应用代码（-chown 免去额外 chown 层；变更频繁的 app/ 放依赖之后）
COPY --chown=appuser:appuser server/alembic.ini ./alembic.ini
COPY --chown=appuser:appuser server/migrations ./migrations
COPY --chown=appuser:appuser server/app ./app
# scripts/ 只取 seed.py/worker.py（worker 服务复用本镜像）；tests/ 不进镜像
COPY --chown=appuser:appuser server/scripts/seed.py server/scripts/worker.py ./scripts/
# 前后台统一构建产物（main.py 挂 parents[2]/web/dist：client 在根 · admin 在 /admin 子目录）
COPY --from=webbuild --chown=appuser:appuser /web/dist /app/web/dist

USER appuser
EXPOSE 8000

# 容器自愈探针：urllib 请求 /api/health（slim 无 curl/wget，零额外依赖）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
