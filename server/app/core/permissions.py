"""权限契约 —— 角色 → 权限点集中映射（RBAC 单一事实源）。

设计要点：
- 权限点格式 `domain:action`，端点挂 require_perm("xxx")，路由层不再出现角色数字；
- 角色矩阵硬编码于此（小团队固定五种角色，不建 Role/Permission 表避免过度设计），
  调整角色能力只改本文件，前后端通过 /api/admin/session/me 下发的 permissions 对齐；
- 超管恒为全量权限；顾客(0)为空集（守卫统一 403）；
- 美甲师(4)仅 chat:manage（行级 mine=1 归属校验在 chat 域 service 层）。
"""

from __future__ import annotations

from app.core.enums import UserRole


class Perm:
    """权限点常量（字符串值即接口守卫与前端 hasPerm 的契约 key）"""

    DASHBOARD_READ = "dashboard:read"    # 数据看板
    TRADE_READ = "trade:read"            # 订单/运费模板查看
    TRADE_MANAGE = "trade:manage"        # 订单业务操作（地址/取消/备注/完成/运费模板写）
    TRADE_SHIP = "trade:ship"            # 履约发货（ship/prepare/mark-delivered/换货发货）
    TRADE_REFUND = "trade:refund"        # 退款/资金类（订单退款/RMA退款/换货打款）
    RMA_READ = "rma:read"                # 退换货/换货单查看
    RMA_MANAGE = "rma:manage"            # 退货/换货审核（approve/reject/complete）
    RMA_RECEIVE = "rma:receive"          # 退货收货入库
    TICKET_MANAGE = "ticket:manage"      # 工单工作台 + 快捷回复模板
    CHAT_MANAGE = "chat:manage"          # 在线客服会话/接管/快捷问题
    CATALOG_READ = "catalog:read"        # 商品/分类/合集/翻译只读
    CATALOG_MANAGE = "catalog:manage"    # 商品写（建/改/上下架/变体/分类/合集/翻译）
    STOCK_READ = "stock:read"            # 库存流水/预警/到货通知
    STOCK_MANAGE = "stock:manage"        # 库存调整
    PROMO_MANAGE = "promo:manage"        # 营销（折扣码/礼品卡/弹窗）
    CONTENT_MANAGE = "content:manage"    # 内容（文章/FAQ/评价/UGC 审核）
    MEDIA_MANAGE = "media:manage"        # 媒体库上传/删除
    MEMBER_READ = "member:read"          # 会员/订阅查看
    MEMBER_MANAGE = "member:manage"      # 会员风险标记/积分调整/订阅代操作
    OPS_QUEUE = "ops:queue"              # 运营队列（弃购/对账/GDPR/Newsletter）
    LOG_READ = "log:read"                # 审计日志
    SETTINGS_MANAGE = "settings:manage"  # 系统设置（白名单外 key service 层再限超管）
    AI_MANAGE = "ai:manage"              # AI 客服配置（LLM Key/Prompt/RAG）
    ADMIN_READ = "admin:read"            # 管理账号列表（工单指派选择器）
    ADMIN_MANAGE = "admin:manage"        # 管理员账号建/改（仅超管）


ALL_PERMISSIONS = frozenset({
    getattr(Perm, name) for name in dir(Perm) if name.isupper()
})

_CS = {
    Perm.TICKET_MANAGE, Perm.CHAT_MANAGE,
    Perm.TRADE_READ, Perm.RMA_READ, Perm.MEMBER_READ, Perm.ADMIN_READ,
}
_OPS = _CS | {
    Perm.DASHBOARD_READ,
    Perm.TRADE_MANAGE, Perm.TRADE_SHIP, Perm.TRADE_REFUND,
    Perm.RMA_MANAGE, Perm.RMA_RECEIVE,
    Perm.CATALOG_READ, Perm.CATALOG_MANAGE,
    Perm.STOCK_READ, Perm.STOCK_MANAGE,
    Perm.PROMO_MANAGE, Perm.CONTENT_MANAGE, Perm.MEDIA_MANAGE,
    Perm.MEMBER_MANAGE, Perm.OPS_QUEUE,
    Perm.LOG_READ, Perm.SETTINGS_MANAGE, Perm.AI_MANAGE,
}
_WAREHOUSE = {
    Perm.DASHBOARD_READ,
    Perm.TRADE_READ, Perm.TRADE_SHIP,
    Perm.RMA_READ, Perm.RMA_RECEIVE,
    Perm.CATALOG_READ,
    Perm.STOCK_READ, Perm.STOCK_MANAGE,
}
_ARTIST = {Perm.CHAT_MANAGE}

ROLE_PERMISSIONS: dict[int, frozenset[str]] = {
    int(UserRole.CUSTOMER): frozenset(),
    int(UserRole.CS): frozenset(_CS),
    int(UserRole.OPS): frozenset(_OPS),
    int(UserRole.WAREHOUSE): frozenset(_WAREHOUSE),
    int(UserRole.ARTIST): frozenset(_ARTIST),
    int(UserRole.SUPER): ALL_PERMISSIONS,
}

# 可登录后台的角色（登录闸门用；顾客 0 拒绝）
BACKEND_ROLES = frozenset(ROLE_PERMISSIONS) - {int(UserRole.CUSTOMER)}

# 超管可建/可管的后台账号角色（美甲师走 seed，不进账号管理面）
ADMIN_ACCOUNT_ROLES = frozenset(
    {int(UserRole.CS), int(UserRole.OPS), int(UserRole.WAREHOUSE), int(UserRole.SUPER)}
)


def permissions_of(role: int) -> frozenset[str]:
    """角色 → 权限集（未知角色按顾客处理=空集，守卫统一 403）"""
    return ROLE_PERMISSIONS.get(int(role), frozenset())


def role_has_perms(role: int, perms) -> bool:
    allowed = permissions_of(role)
    return bool(allowed) and all(p in allowed for p in perms)
