import os
from urllib.parse import urlsplit

JWT_SECRET_DEFAULT = "dev-secret-change-me-0123456789abcdef0123456789"


def _detect_env(db_url: str) -> str:
    """GM_ENV 未显式设置时按 GM_DB 探测运行环境（fail-closed）：
    sqlite / 本机回环库 → dev（本地开发与测试现行为不变）；
    其它远程主机 → 一律按 prod 触发安全闸门，杜绝忘配 GM_ENV 的生产部署
    （如远程 MySQL）以 dev 裸奔：默认 secret / mock_pay 放行 / webhook 免验签"""
    try:
        parts = urlsplit(db_url)
    except ValueError:
        return "prod"
    if (parts.scheme or "").lower().startswith("sqlite"):
        return "dev"
    host = (parts.hostname or "").lower()
    # 仅显式本机回环按 dev；空主机/解析失败等异常形态一律 prod（fail-closed）
    return "dev" if host in ("localhost", "127.0.0.1", "::1") else "prod"


class Settings:
    """全局配置（环境变量外置，代码零硬编码 —— 对应微服务铺路第 6 条）"""

    db_url: str = os.getenv(
        "GM_DB",
        "mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag?charset=utf8mb4",
    )
    jwt_secret: str = os.getenv("GM_JWT_SECRET", JWT_SECRET_DEFAULT)
    # 运行环境：dev（开放 mock 支付/未验签 webhook）/ test / staging / prod；
    # 显式 GM_ENV 优先，未设置按 GM_DB 探测（见 _detect_env，远程库 fail-closed 按 prod）
    env: str = os.getenv("GM_ENV", "").strip().lower() or _detect_env(db_url)
    # mock 支付开关：默认随 env（仅 dev 开放）；GM_MOCK_PAY=1 任何环境放行，=0 强制关闭
    _mock_pay: str = os.getenv("GM_MOCK_PAY", "").strip().lower()

    @property
    def mock_pay_enabled(self) -> bool:
        if self._mock_pay:
            return self._mock_pay not in ("0", "false", "off", "no")
        return self.env == "dev"
    token_days: int = int(os.getenv("GM_TOKEN_DAYS", "7"))
    # 后台会话更短（小时）· 前后台拆域后各自 Cookie 互不串台
    admin_token_hours: int = int(os.getenv("GM_ADMIN_TOKEN_HOURS", "12"))
    # CORS 白名单（逗号分隔完整 origin，如 https://admin.example.com）；为空 = 同源部署不加 CORS 中间件
    allowed_origins: str = os.getenv("GM_ALLOWED_ORIGINS", "")
    # Cookie 会话通道（默认开；纯 API 网关/测试套件可 GM_COOKIE_AUTH=0 关闭，仅 Bearer）
    cookie_auth: bool = os.getenv("GM_COOKIE_AUTH", "1") not in ("0", "false", "off", "no")
    # Cookie Secure 标记：默认随 env（prod=HTTPS 开 / dev 关），可用 GM_COOKIE_SECURE=0/1 覆盖
    _cookie_secure: str = os.getenv("GM_COOKIE_SECURE", "")

    @property
    def cookie_secure(self) -> bool:
        if self._cookie_secure:
            return self._cookie_secure not in ("0", "false", "off", "no")
        return self.env == "prod"
    stripe_key: str = os.getenv("GM_STRIPE_KEY", "")
    stripe_webhook_secret: str = os.getenv("GM_STRIPE_WEBHOOK_SECRET", "")
    stripe_klarna: int = int(os.getenv("GM_STRIPE_KLARNA", "0"))
    paypal_client_id: str = os.getenv("GM_PAYPAL_CLIENT_ID", "")
    paypal_secret: str = os.getenv("GM_PAYPAL_SECRET", "")
    paypal_base: str = os.getenv("GM_PAYPAL_BASE", "https://api-m.sandbox.paypal.com")
    # PayPal Webhook ID（可选；非 dev 环境作为 webhook 门禁/验签匹配依据，空则拒绝处理）
    paypal_webhook_id: str = os.getenv("GM_PAYPAL_WEBHOOK_ID", "")
    # /metrics 访问令牌：非 dev 环境必配（?token= 或 Bearer 匹配；未配 → 403 fail-closed）
    metrics_token: str = os.getenv("GM_METRICS_TOKEN", "").strip()

    _cache_flag: str = os.getenv("GM_CACHE", "").strip().lower()
    cache_enable: bool = _cache_flag not in ("", "0", "false", "off", "no")
    cache_ttl_seconds: int = int(os.getenv("GM_CACHE_TTL", "30" if cache_enable else "0"))
    # 进程内缓存条目上限：超限按最旧淘汰，防长尾键（分页/参数组合）无界涨内存
    cache_maxsize: int = int(os.getenv("GM_CACHE_MAXSIZE", "10000"))

    # 站点对外根地址（邮件模板内链/退订链接前缀；默认沿用模板原硬编码域名保持兼容）
    site_url: str = os.getenv("GM_SITE_URL", "https://glowmag.example").strip().rstrip("/")

    # ===== AI 客服大模型（OpenAI 兼容 chat/completions；key 为空 = 未启用，走规则引擎兜底） =====
    llm_api_key: str = os.getenv("GM_LLM_API_KEY", "").strip()
    # 兼容端点基址：OpenAI / DeepSeek / 通义 / Moonshot 等任意 OpenAI 风格网关
    llm_base_url: str = os.getenv("GM_LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    llm_model: str = os.getenv("GM_LLM_MODEL", "gpt-4o-mini").strip()
    llm_timeout: int = int(os.getenv("GM_LLM_TIMEOUT", "20"))          # 单次调用超时（秒）
    llm_max_tokens: int = int(os.getenv("GM_LLM_MAX_TOKENS", "500"))   # 回复长度上限
    # 进程级 LLM/embedding 并发槽位：拿不到槽位立即回落本地规则引擎，防线程池被慢网关耗尽
    llm_max_concurrency: int = int(os.getenv("GM_LLM_MAX_CONCURRENCY", "8"))


settings = Settings()

# 非 dev 环境安全闸门：jwt_secret 仍为默认值时拒绝启动（防止生产裸奔默认密钥）
if settings.env != "dev" and settings.jwt_secret == JWT_SECRET_DEFAULT:
    raise RuntimeError(
        "GM_ENV resolved to '%s' (non-local GM_DB) but GM_JWT_SECRET is still the "
        "default; set a real GM_JWT_SECRET (and GM_ENV=prod explicitly) before "
        "starting. For local development set GM_ENV=dev." % settings.env
    )
