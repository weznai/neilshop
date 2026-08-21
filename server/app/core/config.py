import os

JWT_SECRET_DEFAULT = "dev-secret-change-me-0123456789abcdef0123456789"


class Settings:
    """全局配置（环境变量外置，代码零硬编码 —— 对应微服务铺路第 6 条）"""

    db_url: str = os.getenv(
        "GM_DB",
        "mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag?charset=utf8mb4",
    )
    jwt_secret: str = os.getenv("GM_JWT_SECRET", JWT_SECRET_DEFAULT)
    # 运行环境：dev（默认，开放 mock 支付/未验签 webhook）/ test / staging / prod
    env: str = os.getenv("GM_ENV", "dev").strip().lower() or "dev"
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

    _cache_flag: str = os.getenv("GM_CACHE", "").strip().lower()
    cache_enable: bool = _cache_flag not in ("", "0", "false", "off", "no")
    cache_ttl_seconds: int = int(os.getenv("GM_CACHE_TTL", "30" if cache_enable else "0"))


settings = Settings()

# 非 dev 环境安全闸门：jwt_secret 仍为默认值时拒绝启动（防止生产裸奔默认密钥）
if settings.env != "dev" and settings.jwt_secret == JWT_SECRET_DEFAULT:
    raise RuntimeError(
        "GM_JWT_SECRET is still the default value; set a real secret "
        "when GM_ENV != 'dev'"
    )
