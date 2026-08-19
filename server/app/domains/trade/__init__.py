"""trade 交易域 —— 购物车/结算/订单/支付/退货(RMA) 用户全链路 + 后台交易履约。

导出路由（挂载于 app.main，前缀即未来微服务边界）：
- cart_router       /api/cart          购物车（游客 token / 登录合并）
- checkout_router   /api/checkout      试算 preview / 下单 place
- orders_router     /api/orders        订单列表/详情/取消/物流查询
- payments_router   /api/payments      intent / mock-pay / webhook
- returns_router    /api/returns       RMA 申请/列表/详情
- admin_router      /api/admin/trade   后台订单履约/退款/RMA 队列/库存调整与流水

分层纪律：router 只做 HTTP 编排（校验/鉴权/响应头）→ service 业务逻辑与事务
→ repository 纯数据访问（SQL 只在此）。跨域协作仅走 app.services.*。
"""

from app.domains.trade.router_admin import router as admin_router  # noqa: F401
from app.domains.trade.router_cart import router as cart_router  # noqa: F401
from app.domains.trade.router_checkout import router as checkout_router  # noqa: F401
from app.domains.trade.router_orders import router as orders_router  # noqa: F401
from app.domains.trade.router_payments import router as payments_router  # noqa: F401
from app.domains.trade.router_returns import router as returns_router  # noqa: F401
