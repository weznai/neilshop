"""域包 —— 按《微服务演进架构设计-v3》八域蓝图组织：

trade    交易域（cart/checkout/orders/payments/returns + 后台履约）
member   会员域（account/points/referrals/subscriptions）
catalog  商品域（目录/搜索 + 后台商品管理）
promo    营销域（折扣码/礼品卡/弹窗 + 后台营销）
content  内容域（FAQ/博客/评价/UGC + 后台审核）
support  客服域（工单 + 后台工作台）
ops      运营域（看板/会员管理/审计日志）
ai       AI 域（推荐/客服 Agent）

分层纪律：router 只做 HTTP 编排（校验/鉴权/响应组装）→ service 业务逻辑与事务
→ repository 仅数据访问。跨域只走 service，禁止跨域摸 repository。
"""
