# -*- coding: utf-8 -*-
"""GLOWMAG API 端点手册自动导出器（智能体 C）

原理：from app.main import app → 递归展平路由（FastAPI 0.141+ 的 _IncludedRouter
→ original_router，沿途累计 include 前缀/tags/dependencies）→ 按 path 前缀分组
（/api/account、/api/admin/*、/api/ai 等）→ 写 docs/API.md。

鉴权推断：路由依赖里出现 require_admin → 🔒 admin；出现 get_current_user → 👤 user；
否则（含 get_current_user_optional 可选登录）→ 🌐 public。

用法：
    python scripts/gen_api_docs.py            # 生成/覆盖 docs/API.md
    python scripts/gen_api_docs.py --check    # 生成后与现有 API.md 比对（忽略时间戳行），
                                              # 不一致 exit 1（供 CI 校验陈旧）
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
sys.path.insert(0, str(SERVER))

OUT = ROOT / "docs" / "API.md"

ADMIN_MARK = "🔒 admin"
USER_MARK = "👤 user"
PUBLIC_MARK = "🌐 public"

METHOD_ORDER = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 4}
METHOD_ZH = {"GET": "查询", "POST": "提交", "PUT": "更新", "PATCH": "部分更新", "DELETE": "删除"}

# ---------------------------------------------------------------- 分组标签
GROUP_TITLES = {
    "/api/account": "会员账户",
    "/api/admin/catalog": "后台 · 商品目录",
    "/api/admin/ops": "后台 · 运营",
    "/api/admin/trade": "后台 · 交易/履约",
    "/api/ai": "AI 服务",
    "/api/cart": "购物车",
    "/api/catalog": "商品目录",
    "/api/checkout": "结账",
    "/api/content": "内容（博客/FAQ/评价/UGC）",
    "/api/exchanges": "换货",
    "/api/health": "健康检查",
    "/api/orders": "订单",
    "/api/payments": "支付",
    "/api/points": "积分",
    "/api/promo": "营销（折扣码/礼品卡/弹窗）",
    "/api/referrals": "推荐返利",
    "/api/returns": "退货 RMA",
    "/api/subscriptions": "订阅盒",
    "/api/support": "客服工单",
    "/metrics": "可观测性",
}

# ---------------------------------------------------------------- 简述生成
# (方法, 路径) 全路径精确覆写——语义复合、一句话讲清行为的端点
OVERRIDES = {
    ("POST", "/api/checkout/place"): "下单（定价引擎·预扣库存·积分冻结·清空购物车）",
    ("POST", "/api/checkout/preview"): "结账试算（小计/码/捆绑/积分/礼品卡/运费/税全分项）",
    ("POST", "/api/payments/create-intent"): "创建支付意图（provider 可选 stripe/paypal/mock）",
    ("POST", "/api/payments/mock-pay"): "模拟支付成功（驱动订单状态机）",
    ("POST", "/api/payments/webhook"): "支付 webhook 回调（验签 + event_id 幂等）",
    ("GET", "/api/payments/methods"): "可用支付方式矩阵（公开）",
    ("GET", "/api/ai/recommend"): "个性化推荐（同类→标签→热销→新上架四级降级）",
    ("GET", "/api/ai/hot"): "热销榜（猜你喜欢兜底）",
    ("POST", "/api/ai/chat"): "AI 客服对话（中英意图识别/订单脱敏/未命中转人工）",
    ("GET", "/api/promo/popup"): "订阅弹窗配置（DB 驱动 + 频控）",
    ("POST", "/api/promo/validate"): "折扣码试算校验（唯一闸门 promo_rules）",
    ("POST", "/api/promo/giftcard"): "礼品卡余额查询（兑换码）",
    ("POST", "/api/promo/giftcard/purchase"): "礼品卡购买（$25/50/100，支付成功后激活）",
    ("GET", "/api/orders/track"): "订单物流轨迹（免登录）",
    ("GET", "/api/account/me"): "个人信息（登录态）",
    ("PUT", "/api/account/me"): "更新个人信息",
    ("POST", "/api/account/register"): "注册（欢迎券触发）",
    ("POST", "/api/account/login"): "登录（JWT）",
    ("POST", "/api/account/consent"): "Cookie 分区同意落库",
    ("POST", "/api/account/newsletter"): "邮件订阅",
    ("POST", "/api/account/unsubscribe"): "一键退订（HMAC token 或登录本人）",
    ("POST", "/api/account/password-reset/request"): "发起密码重置（防账号枚举，恒 200）",
    ("POST", "/api/account/password-reset/confirm"): "确认密码重置（purpose=pwreset JWT 15min）",
    ("GET", "/api/account/email-preferences"): "邮件偏好读取（三开关，登录或 email+token 双通道）",
    ("PUT", "/api/account/email-preferences"): "邮件偏好部分更新（任一开=复订）",
    ("GET", "/api/account/export"): "GDPR 个人数据导出（全量 JSON + DataRequest 落库）",
    ("POST", "/api/account/delete-request"): "GDPR 账户删除申请（202 + 7 天宽限）",
    ("GET", "/api/points"): "积分三视图（余额/冻结/可用）",
    ("GET", "/api/points/ledger"): "积分流水（账务唯一真相）",
    ("GET", "/api/points/expiring"): "即将过期积分汇总",
    ("GET", "/api/referrals/me"): "我的推荐（码/邀请脱敏列表/stats）",
    ("POST", "/api/referrals/simulate-invite"): "模拟受邀下单（演示归因发奖）",
    ("GET", "/api/admin/ops/dashboard"): "运营看板（14 天趋势/最近对账/低库存 Top）",
    ("POST", "/api/cart/merge"): "游客购物车合并至登录账户",
    ("GET", "/api/catalog/search"): "商品搜索（LIKE，演进 Meilisearch 单点替换）",
    ("GET", "/api/catalog/stock-notify"): "到货通知订阅状态查询",
    ("POST", "/api/catalog/stock-notify"): "订阅到货通知（售罄商品，幂等）",
    ("DELETE", "/api/catalog/stock-notify"): "取消到货通知订阅",
    ("POST", "/api/support/tickets/{ticket_no}/messages"): "工单追加留言",
    ("GET", "/api/health"): "健康检查（服务名/版本）",
    ("GET", "/metrics"): "Prometheus 指标（requests_total / duration p50·p95）",
    ("POST", "/api/admin/trade/stock/adjust"): "手工调整库存（写 stock_movements 流水）",
    ("GET", "/api/admin/trade/stock/low"): "低库存预警列表",
    ("GET", "/api/admin/trade/stock/movements"): "库存流水查询（唯一真相）",
    ("GET", "/api/cart"): "购物车视图（token/登录解析，响应头回写 X-Cart-Token）",
    ("POST", "/api/cart/items"): "加购变体（游客可用的 X-Cart-Token）",
    ("PUT", "/api/cart/items/{variant_id}"): "修改购物车数量",
    ("DELETE", "/api/cart/items/{variant_id}"): "移出购物车商品",
    ("POST", "/api/account/wishlist/{product_id}"): "加入愿望单",
    ("DELETE", "/api/account/wishlist/{product_id}"): "移出愿望单",
    ("DELETE", "/api/account/delete-request"): "撤销账户删除申请",
    ("GET", "/api/orders/{order_no}"): "订单详情（登录本人，或订单号+邮箱双因子）",
    ("POST", "/api/returns"): "提交 RMA 退货申请（30 天窗口/数量校验）",
    ("GET", "/api/returns"): "我的退货申请列表",
    ("GET", "/api/returns/{rma_no}"): "退货单详情 + 时间线",
    ("POST", "/api/exchanges"): "创建换货（窗口/可换量校验，差价三态）",
    ("GET", "/api/exchanges"): "我的换货单列表",
    ("GET", "/api/exchanges/{exchange_no}"): "换货单详情（差价/状态）",
    ("GET", "/api/subscriptions/me"): "我的订阅",
    ("POST", "/api/subscriptions"): "创建订阅（4/6/8 周计划）",
    ("GET", "/api/support/tickets"): "工单列表（登录仅自查；游客 ticket_no+email 双因子）",
    ("POST", "/api/support/tickets"): "创建工单（游客可投，可关联订单）",
    ("POST", "/api/content/reviews"): "提交商品评价（已购校验/一单一评）",
    ("GET", "/api/content/ugc"): "UGC 公开上墙（status=1，id 倒序）",
    ("POST", "/api/content/ugc"): "投稿 UGC（匿名可投，采用奖 100 积分）",
    ("PUT", "/api/admin/catalog/collections/{collection_id}/products"): "设置合集商品清单（整表替换）",
    ("GET", "/api/admin/catalog/products/{product_id}/translations"): "商品翻译列表",
    ("PUT", "/api/admin/catalog/products/{product_id}/translations"): "翻译 upsert（locale 维度）",
    ("DELETE", "/api/admin/catalog/products/{product_id}/translations/{locale}"): "删除翻译（按 locale）",
    ("POST", "/api/admin/catalog/products/{product_id}/variants"): "创建变体（支持变体图片 ≤6 张）",
    ("POST", "/api/cart/items-batch"): "批量加购（逐项校验，部分成功）",
    ("PUT", "/api/account/password"): "登录态修改密码（旧密校验）",
    ("GET", "/api/catalog/variants/{variant_id}/siblings"): "同商品变体兄弟列表",
    ("POST", "/api/returns/{rma_no}/cancel"): "撤销退货申请",
    ("PUT", "/api/admin/catalog/collections/{collection_id}"): "集合更新（部分字段，含 banner）",
    ("DELETE", "/api/admin/catalog/collections/{collection_id}"): "集合删除（级联清商品关联）",
    ("GET", "/api/admin/catalog/collections/{collection_id}/products"): "集合商品清单",
    ("GET", "/api/account/wishlist/has"): "愿望单是否已含商品（?product_id=）",
}

# 动作词 → 短语模板（{res} 为资源名词，取自前一段或默认）
ACTIONS = {
    "ship": "{res}发货（回填运单号）",
    "mark-delivered": "标记{res}送达",
    "mark-paid": "标记换货差价已收",
    "refund": "{res}退款",
    "approve": "批准{res}",
    "reject": "拒绝{res}",
    "receive": "RMA 收货（回补库存）",
    "complete": "完成换货（旧变体回补 + exchanged_qty）",
    "cancel": "取消{res}",
    "pause": "暂停订阅",
    "resume": "恢复订阅（续期）",
    "skip": "跳过一期订阅",
    "toggle": "启停{res}",
    "publish": "上架{res}",
    "unpublish": "下架{res}",
    "assign": "指派工单",
    "close": "关闭工单",
    "reply": "回复工单",
    "place": "提交{res}",
    "validate": "校验{res}",
    "adjust": "调整{res}",
    "risk": "标记会员风控",
    "track": "物流轨迹查询",
    "request": "发起请求",
    "confirm": "确认",
}

# 资源名词（末段或参数前段 → 中文）
RESOURCES = {
    "products": "商品",
    "product": "商品",
    "categories": "分类",
    "collections": "合集",
    "variants": "变体",
    "translations": "多语言翻译",
    "orders": "订单",
    "order": "订单",
    "rmas": "RMA",
    "exchanges": "换货单",
    "stock": "库存",
    "movements": "库存流水",
    "members": "会员",
    "discounts": "折扣码",
    "popups": "弹窗",
    "settings": "运营配置",
    "reviews": "评价",
    "ugc": "UGC",
    "articles": "博客文章",
    "faqs": "FAQ",
    "tickets": "工单",
    "addresses": "收货地址",
    "wishlist": "愿望单",
    "items": "购物车商品",
    "cart": "购物车",
    "ledger": "流水",
    "messages": "留言",
    "giftcard": "礼品卡",
    "subscriptions": "订阅",
    "hot": "热销榜",
    "recommend": "推荐",
    "chat": "AI 对话",
    "methods": "支付方式",
    "search": "搜索",
    "dashboard": "看板",
    "logs": "操作日志",
    "templates": "快捷回复模板",
}


def _describe(route, method: str, path: str) -> str:
    """简述：docstring 首行 → summary → 精确覆写 → 路径语义生成 → 兜底。"""
    doc = (getattr(route.endpoint, "__doc__", "") or "").strip()
    if doc:
        return doc.splitlines()[0].strip()
    if route.summary:
        return route.summary
    if (method, path) in OVERRIDES:
        return OVERRIDES[(method, path)]

    segs = [s for s in path.strip("/").split("/") if s]
    has_param = any(s.startswith("{") for s in segs)
    solid = [s for s in segs if not s.startswith("{")]
    last = solid[-1] if solid else path

    if last in ACTIONS:
        res = ""
        for prev in reversed(solid[:-1]):
            if prev in RESOURCES:
                res = RESOURCES[prev]
                break
        return ACTIONS[last].format(res=res)

    res = RESOURCES.get(last, last)
    if method == "GET":
        if last in ("hot", "recommend", "chat", "search", "track", "dashboard", "methods"):
            return OVERRIDES.get((method, path), res)
        return f"{res}详情" if has_param else f"{res}列表"
    if method == "POST":
        return f"创建{res}"
    if method in ("PUT", "PATCH"):
        return f"更新{res}"
    if method == "DELETE":
        return f"删除{res}"
    return f"{METHOD_ZH.get(method, method)} {res}"


# ---------------------------------------------------------------- 路由展平
def _dep_names(route, inherited) -> set:
    """依赖名全集：递归展开子依赖树 —— require_perm(...) 返回闭包 _guard，
    后台守卫依赖 get_admin_user 藏在其子依赖里，只看一层会漏（误判 public）。"""
    names = set(inherited)
    stack = [route.dependant]
    while stack:
        dep = stack.pop()
        for d in dep.dependencies:
            names.add(getattr(d.call, "__name__", ""))
            if getattr(d, "dependencies", None):
                stack.append(d)
    for d in getattr(route, "dependencies", None) or []:
        names.add(getattr(getattr(d, "dependency", None), "__name__", ""))
    return names


_ADMIN_DEPS = {
    "require_admin",       # 历史守卫名（兼容）
    "require_superadmin",  # 超管守卫
    "_guard",              # require_perm(...) 工厂产物（闭包名）
    "get_admin_user",      # 后台身份解析（require_perm/_guard 的子依赖，树内命中）
    "get_admin_session_user",  # 后台会话探测（/api/admin/session/me）
}


def _auth_mark(names: set) -> str:
    if names & _ADMIN_DEPS:
        return ADMIN_MARK
    if "get_current_user" in names:
        return USER_MARK
    return PUBLIC_MARK


def _group_key(path: str) -> str:
    parts = path.strip("/").split("/")
    if parts and parts[0] == "api":
        depth = 3 if len(parts) >= 2 and parts[1] == "admin" else 2
        return "/" + "/".join(parts[:depth])
    return "/" + parts[0]


def flatten(routes, prefix="", tags=(), deps=()):
    """递归展平：_IncludedRouter → original_router（累计 include 前缀/tags/依赖）。"""
    out = []
    for r in routes:
        type_name = type(r).__name__
        if type_name == "_IncludedRouter":
            ic = r.include_context
            out.extend(
                flatten(
                    r.original_router.routes,
                    prefix + (ic.prefix or ""),
                    tuple(tags) + tuple(ic.tags or ()),
                    tuple(deps) + tuple(ic.dependencies or ()),
                )
            )
        elif type_name == "APIRoute":
            out.append((r, prefix, tuple(tags), tuple(deps)))
    return out


def collect_endpoints():
    from app.main import app  # noqa: 延迟导入，保证 --help 不依赖环境

    flat = flatten(app.routes)
    raw = sum(
        len(r.methods - {"HEAD", "OPTIONS"})
        for r, *_ in flat
        if getattr(r, "include_in_schema", True) is not False
    )
    endpoints = {}
    for route, prefix, inherited_tags, inherited_deps in flat:
        # include_in_schema=False 的路由（robots.txt/sitemap/legacy 重定向等）不进 API 手册
        if getattr(route, "include_in_schema", True) is False:
            continue
        path = prefix + route.path
        if path != "/" and path.endswith("/"):  # 尾斜杠双路由合并（同处理器）
            norm = path.rstrip("/")
        else:
            norm = path
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            key = (method, norm)
            if key in endpoints:
                endpoints[key]["dual"] = True
                continue
            names = _dep_names(route, [getattr(d, "__name__", "") for d in inherited_deps])
            tag_list = list(route.tags or []) + [t for t in inherited_tags if t not in (route.tags or [])]
            endpoints[key] = {
                "method": method,
                "path": norm,
                "auth": _auth_mark(names),
                "tags": tag_list,
                "desc": _describe(route, method, norm),
                "dual": False,
            }
    return list(endpoints.values()), raw


# ---------------------------------------------------------------- 渲染
FOOTER = """## 常见响应约定（静态说明）

- **金额单位**：全部金额字段为**美分 int**（如 `3110` = $31.10），前端除以 100 展示；整型运算消除浮点误差。
- **游客购物车**：无需登录，携带请求头 `X-Cart-Token: <hex>`（首访由服务端签发并在响应头回写）；登录后调用 `POST /api/cart/merge` 合并。
- **鉴权头**：`Authorization: Bearer <jwt>`；后台端点要求 `role >= 2`（运营/仓库/超管），否则 403 `Admin only`。
- **错误风格**：失败返回 4xx/5xx + `{"detail": "<原因短语>"}`（如 401 `Not authenticated`、409 库存不足、429 限流附 `Retry-After`）。
- **列表分页**：统一 `{items, total, page, size}` 结构（page 从 1 起）。
- **时间**：DATETIME 秒级 UTC（naive），前端自行转本地时区。
"""


def render(endpoints, raw_count) -> str:
    from datetime import datetime

    dual_count = raw_count - len(endpoints)
    groups = {}
    for ep in endpoints:
        groups.setdefault(_group_key(ep["path"]), []).append(ep)
    for eps in groups.values():
        eps.sort(key=lambda e: (e["path"], METHOD_ORDER.get(e["method"], 9)))

    auth_count = {ADMIN_MARK: 0, USER_MARK: 0, PUBLIC_MARK: 0}
    for ep in endpoints:
        auth_count[ep["auth"]] += 1

    lines = []
    lines.append("# GLOWMAG API 端点手册")
    lines.append("")
    lines.append("> 本文件由 `scripts/gen_api_docs.py` 自动生成（`from app.main import app` 展平路由），请勿手编；")
    lines.append("> CI 可用 `python scripts/gen_api_docs.py --check` 校验是否陈旧（不一致 exit 1）。")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(
        f"- 端点总数：**{len(endpoints)}**（展平后路由 {raw_count} 条，"
        f"含 {dual_count} 个尾斜杠双路由已合并；方法×路径去重口径）"
    )
    lines.append(f"- 分组数：**{len(groups)}**")
    lines.append(
        "- 鉴权分布：🔒 admin {} · 👤 user {} · 🌐 public {}".format(
            auth_count[ADMIN_MARK], auth_count[USER_MARK], auth_count[PUBLIC_MARK]
        )
    )
    lines.append("")
    lines.append("## 运行与交互文档")
    lines.append("")
    lines.append("```powershell")
    lines.append("cd server")
    lines.append(".venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000 --reload")
    lines.append("```")
    lines.append("")
    lines.append("- Swagger 交互文档：<http://localhost:8000/docs>（可逐端点 Try it out）")
    lines.append("- ReDoc：<http://localhost:8000/redoc> · OpenAPI JSON：<http://localhost:8000/openapi.json>")
    lines.append("- 原型前台：<http://localhost:8000/> · 种子账号见 README（密码 `glowmag123`）")
    lines.append("")

    for gkey in sorted(groups):
        eps = groups[gkey]
        title = GROUP_TITLES.get(gkey, "")
        head = f"## {gkey}" + (f" · {title}" if title else "")
        lines.append("")
        lines.append(f"{head}（{len(eps)} 个端点）")
        lines.append("")
        lines.append("| 方法 | 路径 | 鉴权 | tags | 说明 |")
        lines.append("|---|---|---|---|---|")
        for ep in eps:
            path_cell = f"`{ep['path']}`"
            if ep["dual"]:
                path_cell += f"（`{ep['path']}/` 双路由）"
            tags = ", ".join(ep["tags"]) if ep["tags"] else "-"
            lines.append(
                f"| `{ep['method']}` | {path_cell} | {ep['auth']} | {tags} | {ep['desc']} |"
            )

    lines.append("")
    lines.append(FOOTER)
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    check = "--check" in sys.argv
    endpoints, raw = collect_endpoints()
    content = render(endpoints, raw)

    if check:
        if not OUT.exists():
            print("API.md 不存在（先运行 gen_api_docs.py 生成）")
            return 1
        current = OUT.read_text(encoding="utf-8")
        # 忽略时间戳行（每分钟都会变），其余必须逐行一致
        import re

        strip = lambda s: re.sub(r"^- 生成时间：.*$", "- 生成时间：<masked>", s, flags=re.M)
        if strip(current) == strip(content):
            print("API.md 与路由一致（--check 通过）")
            return 0
        print("API.md 与当前路由不一致（陈旧）——请重新运行 gen_api_docs.py")
        return 1

    OUT.write_text(content, encoding="utf-8", newline="\n")
    auth_count = {ADMIN_MARK: 0, USER_MARK: 0, PUBLIC_MARK: 0}
    for ep in endpoints:
        auth_count[ep["auth"]] += 1
    n_groups = len({_group_key(ep["path"]) for ep in endpoints})
    print(
        "已生成 {}：端点 {}（路由 {} 条，双路由合并 {}）· 分组 {} · 鉴权 admin {}/user {}/public {}".format(
            OUT, len(endpoints), raw, raw - len(endpoints), n_groups,
            auth_count[ADMIN_MARK], auth_count[USER_MARK], auth_count[PUBLIC_MARK],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
