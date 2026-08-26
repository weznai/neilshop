# GLOWMAG API 端点手册

> 本文件由 `scripts/gen_api_docs.py` 自动生成（`from app.main import app` 展平路由），请勿手编；
> CI 可用 `python scripts/gen_api_docs.py --check` 校验是否陈旧（不一致 exit 1）。

- 生成时间：2026-08-23 13:17:48
- 端点总数：**217**（展平后路由 224 条，含 7 个尾斜杠双路由已合并；方法×路径去重口径）
- 分组数：**23**
- 鉴权分布：🔒 admin 114 · 👤 user 37 · 🌐 public 66

## 运行与交互文档

```powershell
cd server
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
```

- Swagger 交互文档：<http://localhost:8000/docs>（可逐端点 Try it out）
- ReDoc：<http://localhost:8000/redoc> · OpenAPI JSON：<http://localhost:8000/openapi.json>
- 原型前台：<http://localhost:8000/> · 种子账号见 README（密码 `glowmag123`）


## /api/account · 会员账户（27 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/account/addresses` | 👤 user | account | 收货地址列表 |
| `POST` | `/api/account/addresses` | 👤 user | account | 创建收货地址 |
| `PUT` | `/api/account/addresses/{address_id}` | 👤 user | account | 更新收货地址 |
| `DELETE` | `/api/account/addresses/{address_id}` | 👤 user | account | 删除收货地址 |
| `POST` | `/api/account/admin/login` | 🌐 public | account | 后台专用登录：role>=2 才放行，签发短时效 gm_admin_token（SameSite=Strict）。 |
| `POST` | `/api/account/admin/logout` | 🌐 public | account | 创建logout |
| `GET` | `/api/account/admin/me` | 🌐 public | account | 后台会话探测：严格只认 gm_admin_token（与前台 gm_token 隔离，双 Cookie 并存不串台）。 |
| `POST` | `/api/account/consent` | 🌐 public | account | Cookie 分区同意落库 |
| `POST` | `/api/account/delete-request` | 👤 user | account | GDPR 账户删除申请（202 + 7 天宽限） |
| `DELETE` | `/api/account/delete-request` | 👤 user | account | 撤销账户删除申请 |
| `GET` | `/api/account/email-preferences` | 🌐 public | account | 偏好中心读取：登录 → 自身邮箱；或 ?email=&token=（us_ HMAC）。 |
| `PUT` | `/api/account/email-preferences` | 🌐 public | account | 偏好中心部分更新：任一开关为 1 → 复订（清 unsubscribed_at）；全 0 → 等价全退。 |
| `GET` | `/api/account/export` | 👤 user | account | GDPR 个人数据导出（全量 JSON + DataRequest 落库） |
| `POST` | `/api/account/login` | 🌐 public | account | 登录（JWT） |
| `POST` | `/api/account/logout` | 🌐 public | account | 登出：清前台会话 Cookie（幂等，未登录也 200）。 |
| `GET` | `/api/account/me` | 👤 user | account | 个人信息（登录态） |
| `PUT` | `/api/account/me` | 👤 user | account | 更新个人信息 |
| `POST` | `/api/account/newsletter` | 🌐 public | account | 邮件订阅 |
| `PUT` | `/api/account/password` | 👤 user | account | 登录态修改密码（旧密校验） |
| `POST` | `/api/account/password-reset/confirm` | 🌐 public | account | 确认密码重置（purpose=pwreset JWT 15min） |
| `POST` | `/api/account/password-reset/request` | 🌐 public | account | 发起密码重置（防账号枚举，恒 200） |
| `POST` | `/api/account/register` | 🌐 public | account | 注册（欢迎券触发） |
| `POST` | `/api/account/unsubscribe` | 🌐 public | account | 一键退订（HMAC token 或登录本人） |
| `GET` | `/api/account/wishlist` | 👤 user | account | 愿望单列表 |
| `GET` | `/api/account/wishlist/has` | 👤 user | account | 心愿单是否已含某商品（详情页心形状态轻查询，登录态低频不扩限流） |
| `POST` | `/api/account/wishlist/{product_id}` | 👤 user | account | 加入愿望单 |
| `DELETE` | `/api/account/wishlist/{product_id}` | 👤 user | account | 移出愿望单 |

## /api/admin/catalog · 后台 · 商品目录（25 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/admin/catalog/categories` | 🔒 admin | admin-catalog | 分类列表 |
| `POST` | `/api/admin/catalog/categories` | 🔒 admin | admin-catalog | 创建分类 |
| `PUT` | `/api/admin/catalog/categories/{category_id}` | 🔒 admin | admin-catalog | 更新分类 |
| `DELETE` | `/api/admin/catalog/categories/{category_id}` | 🔒 admin | admin-catalog | 删除分类 |
| `GET` | `/api/admin/catalog/collections` | 🔒 admin | admin-catalog | 合集列表 |
| `POST` | `/api/admin/catalog/collections` | 🔒 admin | admin-catalog | 创建合集 |
| `PUT` | `/api/admin/catalog/collections/{collection_id}` | 🔒 admin | admin-catalog | 集合更新（部分字段，含 banner） |
| `DELETE` | `/api/admin/catalog/collections/{collection_id}` | 🔒 admin | admin-catalog | 集合删除（级联清商品关联） |
| `GET` | `/api/admin/catalog/collections/{collection_id}/products` | 🔒 admin | admin-catalog | 集合商品清单 |
| `PUT` | `/api/admin/catalog/collections/{collection_id}/products` | 🔒 admin | admin-catalog | 设置合集商品清单（整表替换） |
| `GET` | `/api/admin/catalog/products` | 🔒 admin | admin-catalog | 商品列表 |
| `POST` | `/api/admin/catalog/products` | 🔒 admin | admin-catalog | 创建商品 |
| `POST` | `/api/admin/catalog/products/bulk` | 🔒 admin | admin-catalog | 创建bulk |
| `GET` | `/api/admin/catalog/products/{product_id}` | 🔒 admin | admin-catalog | 商品详情 |
| `PUT` | `/api/admin/catalog/products/{product_id}` | 🔒 admin | admin-catalog | 更新商品 |
| `POST` | `/api/admin/catalog/products/{product_id}/publish` | 🔒 admin | admin-catalog | 上架商品 |
| `GET` | `/api/admin/catalog/products/{product_id}/translations` | 🔒 admin | admin-catalog | 商品翻译列表 |
| `PUT` | `/api/admin/catalog/products/{product_id}/translations` | 🔒 admin | admin-catalog | 翻译 upsert（locale 维度） |
| `DELETE` | `/api/admin/catalog/products/{product_id}/translations/{locale}` | 🔒 admin | admin-catalog | 删除翻译（按 locale） |
| `POST` | `/api/admin/catalog/products/{product_id}/unpublish` | 🔒 admin | admin-catalog | 下架商品 |
| `POST` | `/api/admin/catalog/products/{product_id}/variants` | 🔒 admin | admin-catalog | 创建变体（支持变体图片 ≤6 张） |
| `GET` | `/api/admin/catalog/stock-notifies` | 🔒 admin | admin-catalog | 到货通知名单（StockNotification 模型在本 catalog 域，端点落位 catalog） |
| `GET` | `/api/admin/catalog/variants` | 🔒 admin | admin-catalog | 变体列表 |
| `PUT` | `/api/admin/catalog/variants/{variant_id}` | 🔒 admin | admin-catalog | 更新变体 |
| `DELETE` | `/api/admin/catalog/variants/{variant_id}` | 🔒 admin | admin-catalog | 删除变体 |

## /api/admin/media（3 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/admin/media` | 🔒 admin | admin-media | media列表 |
| `POST` | `/api/admin/media/upload` | 🔒 admin | admin-media | 创建upload |
| `DELETE` | `/api/admin/media/{filename:path}` | 🔒 admin | admin-media | 删除媒体：路径安全校验（防穿越，:path 兼容 YYYYMM/xxx.png 相对名） |

## /api/admin/member（4 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/admin/member/subscriptions` | 🔒 admin | admin-member | 订阅列表 |
| `POST` | `/api/admin/member/subscriptions/{sub_id}/cancel` | 🔒 admin | admin-member | 取消订阅 |
| `POST` | `/api/admin/member/subscriptions/{sub_id}/pause` | 🔒 admin | admin-member | 暂停订阅 |
| `POST` | `/api/admin/member/subscriptions/{sub_id}/resume` | 🔒 admin | admin-member | 恢复订阅（续期） |

## /api/admin/ops · 后台 · 运营（49 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/admin/ops/abandoned-carts` | 🔒 admin | admin-ops | 弃购队列：口径对齐 worker（有商品 + 最后活跃超 1 小时未下单），按最后活跃倒序 |
| `GET` | `/api/admin/ops/admins` | 🔒 admin | admin-ops | admins列表 |
| `POST` | `/api/admin/ops/admins` | 🌐 public | admin-ops | 创建admins |
| `GET` | `/api/admin/ops/admins/{admin_id}` | 🌐 public | admin-ops | admins详情 |
| `PUT` | `/api/admin/ops/admins/{admin_id}` | 🌐 public | admin-ops | 更新admins |
| `GET` | `/api/admin/ops/articles` | 🔒 admin | admin-ops | 博客文章列表 |
| `POST` | `/api/admin/ops/articles` | 🔒 admin | admin-ops | 创建博客文章 |
| `PUT` | `/api/admin/ops/articles/{article_id}` | 🔒 admin | admin-ops | 更新博客文章 |
| `DELETE` | `/api/admin/ops/articles/{article_id}` | 🔒 admin | admin-ops | 删除博客文章 |
| `GET` | `/api/admin/ops/dashboard` | 🔒 admin | admin-ops | 运营看板（14 天趋势/最近对账/低库存 Top） |
| `GET` | `/api/admin/ops/data-requests` | 🔒 admin | admin-ops | data-requests列表 |
| `POST` | `/api/admin/ops/data-requests/{req_id}/execute` | 🔒 admin | admin-ops | 立即执行（删除类与 worker 共用 anonymize_user）；仅受理中(0)可执行 |
| `POST` | `/api/admin/ops/data-requests/{req_id}/reject` | 🔒 admin | admin-ops | 拒绝 |
| `GET` | `/api/admin/ops/discounts` | 🔒 admin | admin-ops | 折扣码列表 |
| `POST` | `/api/admin/ops/discounts` | 🔒 admin | admin-ops | 创建折扣码 |
| `PUT` | `/api/admin/ops/discounts/{discount_id}` | 🔒 admin | admin-ops | 更新折扣码 |
| `POST` | `/api/admin/ops/discounts/{discount_id}/toggle` | 🔒 admin | admin-ops | 启停折扣码 |
| `GET` | `/api/admin/ops/email-templates` | 🔒 admin | admin-ops | 邮件模板运营预览：8 个自动化邮件 × 固定示例数据渲染（只读 emails.py） |
| `GET` | `/api/admin/ops/faqs` | 🔒 admin | admin-ops | FAQ列表 |
| `POST` | `/api/admin/ops/faqs` | 🔒 admin | admin-ops | 创建FAQ |
| `PUT` | `/api/admin/ops/faqs/{faq_id}` | 🔒 admin | admin-ops | 更新FAQ |
| `DELETE` | `/api/admin/ops/faqs/{faq_id}` | 🔒 admin | admin-ops | 删除FAQ |
| `GET` | `/api/admin/ops/logs` | 🔒 admin | admin-ops | 操作日志列表 |
| `GET` | `/api/admin/ops/members` | 🔒 admin | admin-ops | 会员列表 |
| `GET` | `/api/admin/ops/members/{user_id}` | 🔒 admin | admin-ops | 会员详情 |
| `POST` | `/api/admin/ops/members/{user_id}/points` | 🔒 admin | admin-ops | 创建points |
| `POST` | `/api/admin/ops/members/{user_id}/risk` | 🔒 admin | admin-ops | 标记会员风控 |
| `GET` | `/api/admin/ops/newsletters` | 🔒 admin | admin-ops | newsletters列表 |
| `GET` | `/api/admin/ops/popups` | 🔒 admin | admin-ops | 弹窗列表 |
| `POST` | `/api/admin/ops/popups` | 🔒 admin | admin-ops | 创建弹窗 |
| `PUT` | `/api/admin/ops/popups/{popup_id}` | 🔒 admin | admin-ops | 更新弹窗 |
| `POST` | `/api/admin/ops/popups/{popup_id}/toggle` | 🔒 admin | admin-ops | 启停弹窗 |
| `GET` | `/api/admin/ops/reconciliations` | 🔒 admin | admin-ops | reconciliations列表 |
| `GET` | `/api/admin/ops/reviews`（`/api/admin/ops/reviews/` 双路由） | 🔒 admin | admin-ops | 评价列表 |
| `POST` | `/api/admin/ops/reviews/bulk` | 🔒 admin | admin-ops | 创建bulk |
| `POST` | `/api/admin/ops/reviews/{review_id}/approve` | 🔒 admin | admin-ops | 批准评价 |
| `POST` | `/api/admin/ops/reviews/{review_id}/reject` | 🔒 admin | admin-ops | 拒绝评价 |
| `POST` | `/api/admin/ops/reviews/{review_id}/unapprove` | 🔒 admin | admin-ops | 创建unapprove |
| `GET` | `/api/admin/ops/settings` | 🔒 admin | admin-ops | 运营配置列表 |
| `PUT` | `/api/admin/ops/settings` | 🔒 admin | admin-ops | 更新运营配置 |
| `GET` | `/api/admin/ops/tickets` | 🔒 admin | admin-ops | 工单列表 |
| `POST` | `/api/admin/ops/tickets/{ticket_no}/assign` | 🔒 admin | admin-ops | 指派工单 |
| `POST` | `/api/admin/ops/tickets/{ticket_no}/close` | 🔒 admin | admin-ops | 关闭工单 |
| `POST` | `/api/admin/ops/tickets/{ticket_no}/reply` | 🔒 admin | admin-ops | 回复工单 |
| `GET` | `/api/admin/ops/ugc` | 🔒 admin | admin-ops | UGC列表 |
| `POST` | `/api/admin/ops/ugc/bulk` | 🔒 admin | admin-ops | 创建bulk |
| `POST` | `/api/admin/ops/ugc/{ugc_id}/approve` | 🔒 admin | admin-ops | 批准UGC |
| `POST` | `/api/admin/ops/ugc/{ugc_id}/reject` | 🔒 admin | admin-ops | 拒绝UGC |
| `POST` | `/api/admin/ops/ugc/{ugc_id}/unapprove` | 🔒 admin | admin-ops | 创建unapprove |

## /api/admin/promo（7 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `DELETE` | `/api/admin/promo/discounts/{discount_id}` | 🔒 admin | admin-ops | 删除折扣码 |
| `GET` | `/api/admin/promo/discounts/{discount_id}/usages` | 🔒 admin | admin-ops | usages详情 |
| `GET` | `/api/admin/promo/giftcards` | 🔒 admin | admin-ops | giftcards列表 |
| `POST` | `/api/admin/promo/giftcards` | 🔒 admin | admin-ops | 创建giftcards |
| `PUT` | `/api/admin/promo/giftcards/{gift_card_id}/freeze` | 🔒 admin | admin-ops | 更新freeze |
| `GET` | `/api/admin/promo/giftcards/{gift_card_id}/ledger` | 🔒 admin | admin-ops | 流水详情 |
| `PUT` | `/api/admin/promo/giftcards/{gift_card_id}/unfreeze` | 🔒 admin | admin-ops | 更新unfreeze |

## /api/admin/support（1 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `PUT` | `/api/admin/support/tickets/{ticket_no}/status` | 🔒 admin | admin-ops | 更新status |

## /api/admin/trade · 后台 · 交易/履约（30 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/admin/trade/exchanges` | 🔒 admin | admin-trade | 换货单列表 |
| `POST` | `/api/admin/trade/exchanges/{exchange_no}/approve` | 🔒 admin | admin-trade | 批准换货单 |
| `POST` | `/api/admin/trade/exchanges/{exchange_no}/complete` | 🔒 admin | admin-trade | 完成换货（旧变体回补 + exchanged_qty） |
| `POST` | `/api/admin/trade/exchanges/{exchange_no}/mark-paid` | 🔒 admin | admin-trade | 标记换货差价已收 |
| `POST` | `/api/admin/trade/exchanges/{exchange_no}/reject` | 🔒 admin | admin-trade | 拒绝换货单 |
| `POST` | `/api/admin/trade/exchanges/{exchange_no}/ship` | 🔒 admin | admin-trade | 换货单发货（回填运单号） |
| `GET` | `/api/admin/trade/orders` | 🔒 admin | admin-trade | 订单列表 |
| `GET` | `/api/admin/trade/orders/{order_no}` | 🔒 admin | admin-trade | 订单详情 |
| `PUT` | `/api/admin/trade/orders/{order_no}/address` | 🔒 admin | admin-trade | 更新address |
| `POST` | `/api/admin/trade/orders/{order_no}/cancel` | 🔒 admin | admin-trade | 取消订单 |
| `POST` | `/api/admin/trade/orders/{order_no}/mark-completed` | 🔒 admin | admin-trade | 创建mark-completed |
| `POST` | `/api/admin/trade/orders/{order_no}/mark-delivered` | 🔒 admin | admin-trade | 标记订单送达 |
| `POST` | `/api/admin/trade/orders/{order_no}/note` | 🔒 admin | admin-trade | 创建note |
| `POST` | `/api/admin/trade/orders/{order_no}/prepare` | 🔒 admin | admin-trade | 创建prepare |
| `POST` | `/api/admin/trade/orders/{order_no}/refund` | 🔒 admin | admin-trade | 订单退款 |
| `POST` | `/api/admin/trade/orders/{order_no}/ship` | 🔒 admin | admin-trade | 订单发货（回填运单号） |
| `GET` | `/api/admin/trade/payments` | 🔒 admin | admin-trade | 支付流水分页（跨订单：状态/通道/单号邮箱搜索/日期） |
| `GET` | `/api/admin/trade/webhook-events` | 🔒 admin | admin-trade | 支付回调事件分页（webhook_events 原文：来源/类型/状态） |
| `GET` | `/api/admin/trade/rmas` | 🔒 admin | admin-trade | RMA列表 |
| `POST` | `/api/admin/trade/rmas/{rma_no}/approve` | 🔒 admin | admin-trade | 批准RMA |
| `POST` | `/api/admin/trade/rmas/{rma_no}/receive` | 🔒 admin | admin-trade | RMA 收货（回补库存） |
| `POST` | `/api/admin/trade/rmas/{rma_no}/refund` | 🔒 admin | admin-trade | RMA退款 |
| `POST` | `/api/admin/trade/rmas/{rma_no}/reject` | 🔒 admin | admin-trade | 拒绝RMA |
| `GET` | `/api/admin/trade/shipping-rates` | 🔒 admin | admin-trade | shipping-rates列表 |
| `POST` | `/api/admin/trade/shipping-rates` | 🔒 admin | admin-trade | 创建shipping-rates |
| `PUT` | `/api/admin/trade/shipping-rates/{rate_id}` | 🔒 admin | admin-trade | 更新shipping-rates |
| `DELETE` | `/api/admin/trade/shipping-rates/{rate_id}` | 🔒 admin | admin-trade | 删除shipping-rates |
| `POST` | `/api/admin/trade/stock/adjust` | 🔒 admin | admin-trade | 手工调整库存（写 stock_movements 流水） |
| `GET` | `/api/admin/trade/stock/low` | 🔒 admin | admin-trade | 低库存预警列表 |
| `GET` | `/api/admin/trade/stock/movements` | 🔒 admin | admin-trade | 库存流水查询（唯一真相） |

## /api/ai · AI 服务（3 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `POST` | `/api/ai/chat` | 🌐 public | ai | AI 客服对话（中英意图识别/订单脱敏/未命中转人工） |
| `GET` | `/api/ai/hot` | 🌐 public | ai | 热销榜（猜你喜欢兜底） |
| `GET` | `/api/ai/recommend` | 🌐 public | ai | 个性化推荐（同类→标签→热销→新上架四级降级） |

## /api/cart · 购物车（6 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/cart`（`/api/cart/` 双路由） | 🌐 public | cart | 购物车视图（token/登录解析，响应头回写 X-Cart-Token） |
| `POST` | `/api/cart/items` | 🌐 public | cart | 加购变体（游客可用的 X-Cart-Token） |
| `POST` | `/api/cart/items-batch` | 🌐 public | cart | 批量加购（逐项校验，部分成功） |
| `PUT` | `/api/cart/items/{variant_id}` | 🌐 public | cart | 修改购物车数量 |
| `DELETE` | `/api/cart/items/{variant_id}` | 🌐 public | cart | 移出购物车商品 |
| `POST` | `/api/cart/merge` | 👤 user | cart | 游客购物车合并至登录账户 |

## /api/catalog · 商品目录（13 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/catalog/categories` | 🌐 public | catalog | 分类列表 |
| `GET` | `/api/catalog/collections` | 🌐 public | catalog | 合集列表 |
| `GET` | `/api/catalog/collections/{slug}` | 🌐 public | catalog | 合集详情 |
| `GET` | `/api/catalog/products` | 🌐 public | catalog | 商品列表 |
| `GET` | `/api/catalog/products-by-id/{product_id}` | 🌐 public | catalog | products-by-id详情 |
| `GET` | `/api/catalog/products/{slug}` | 🌐 public | catalog | 商品详情 |
| `GET` | `/api/catalog/reviews` | 🌐 public | catalog | 评价列表 |
| `GET` | `/api/catalog/reviews/distribution` | 🌐 public | catalog | distribution列表 |
| `GET` | `/api/catalog/search` | 🌐 public | catalog | 商品搜索（LIKE，演进 Meilisearch 单点替换） |
| `GET` | `/api/catalog/stock-notify` | 🌐 public | catalog | 到货通知订阅状态查询 |
| `POST` | `/api/catalog/stock-notify` | 🌐 public | catalog | 订阅到货通知（售罄商品，幂等） |
| `DELETE` | `/api/catalog/stock-notify` | 🌐 public | catalog | 取消到货通知订阅 |
| `GET` | `/api/catalog/variants/{variant_id}/siblings` | 🌐 public | catalog | 同商品变体兄弟列表 |

## /api/checkout · 结账（3 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `POST` | `/api/checkout/place` | 🌐 public | checkout | 下单（定价引擎·预扣库存·积分冻结·清空购物车） |
| `POST` | `/api/checkout/preview` | 🌐 public | checkout | 结账试算（小计/码/捆绑/积分/礼品卡/运费/税全分项） |
| `GET` | `/api/checkout/shipping-methods` | 🌐 public | checkout | 公开：可用配送方式（运费模板聚合，checkout 页展示）。 |

## /api/content · 内容（博客/FAQ/评价/UGC）（7 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/content/articles` | 🌐 public | content | 博客文章列表 |
| `GET` | `/api/content/articles/{slug}` | 🌐 public | content | 博客文章详情 |
| `GET` | `/api/content/faqs` | 🌐 public | content | FAQ列表 |
| `GET` | `/api/content/reviews` | 🌐 public | content | 评价列表 |
| `POST` | `/api/content/reviews` | 👤 user | content | 提交商品评价（已购校验/一单一评） |
| `GET` | `/api/content/ugc` | 🌐 public | content | UGC 公开上墙（status=1，id 倒序） |
| `POST` | `/api/content/ugc` | 🌐 public | content | 投稿 UGC（匿名可投，采用奖 100 积分） |

## /api/exchanges · 换货（6 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/exchanges`（`/api/exchanges/` 双路由） | 🌐 public | exchanges | 我的换货单列表 |
| `POST` | `/api/exchanges`（`/api/exchanges/` 双路由） | 🌐 public | exchanges | 创建换货（窗口/可换量校验，差价三态） |
| `GET` | `/api/exchanges/{exchange_no}` | 🌐 public | exchanges | 换货单详情（差价/状态） |
| `POST` | `/api/exchanges/{exchange_no}/cancel` | 👤 user | exchanges | 取消换货单 |
| `POST` | `/api/exchanges/{exchange_no}/mock-pay` | 👤 user | exchanges | 创建mock-pay |
| `POST` | `/api/exchanges/{exchange_no}/pay-intent` | 👤 user | exchanges | 创建pay-intent |

## /api/health · 健康检查（1 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/health` | 🌐 public | - | 健康检查（服务名/版本） |

## /api/orders · 订单（5 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/orders`（`/api/orders/` 双路由） | 👤 user | orders | 订单列表 |
| `GET` | `/api/orders/track` | 🌐 public | orders | 订单物流轨迹（免登录） |
| `GET` | `/api/orders/{order_no}` | 🌐 public | orders | 订单详情（登录本人，或订单号+邮箱双因子） |
| `POST` | `/api/orders/{order_no}/cancel` | 👤 user | orders | 取消订单 |
| `POST` | `/api/orders/{order_no}/confirm-received` | 👤 user | orders | 创建confirm-received |

## /api/payments · 支付（4 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `POST` | `/api/payments/create-intent` | 🌐 public | payments | 创建支付意图（provider 可选 stripe/paypal/mock） |
| `GET` | `/api/payments/methods` | 🌐 public | payments | 可用支付方式矩阵（公开） |
| `POST` | `/api/payments/mock-pay` | 🌐 public | payments | 模拟支付成功（驱动订单状态机） |
| `POST` | `/api/payments/webhook` | 🌐 public | payments | 支付 webhook 回调（验签 + event_id 幂等） |

## /api/points · 积分（3 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/points` | 👤 user | points | 积分三视图（余额/冻结/可用） |
| `GET` | `/api/points/expiring` | 👤 user | points | 即将过期积分汇总 |
| `GET` | `/api/points/ledger` | 👤 user | points | 积分流水（账务唯一真相） |

## /api/promo · 营销（折扣码/礼品卡/弹窗）（6 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `POST` | `/api/promo/giftcard` | 🌐 public | promo | 礼品卡余额查询（兑换码） |
| `POST` | `/api/promo/giftcard/purchase` | 🌐 public | promo | 礼品卡购买（$25/50/100，支付成功后激活） |
| `GET` | `/api/promo/popup` | 🌐 public | promo | 订阅弹窗配置（DB 驱动 + 频控） |
| `POST` | `/api/promo/popup/{popup_id}/convert` | 🌐 public | promo | 创建convert |
| `POST` | `/api/promo/popup/{popup_id}/shown` | 🌐 public | promo | 创建shown |
| `POST` | `/api/promo/validate` | 🌐 public | promo | 折扣码试算校验（唯一闸门 promo_rules） |

## /api/referrals · 推荐返利（2 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/referrals/me` | 👤 user | referrals | 我的推荐（码/邀请脱敏列表/stats） |
| `POST` | `/api/referrals/simulate-invite` | 👤 user | referrals | 模拟受邀下单（演示归因发奖） |

## /api/returns · 退货 RMA（4 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/returns`（`/api/returns/` 双路由） | 👤 user | returns | 我的退货申请列表 |
| `POST` | `/api/returns`（`/api/returns/` 双路由） | 👤 user | returns | 提交 RMA 退货申请（30 天窗口/数量校验） |
| `GET` | `/api/returns/{rma_no}` | 👤 user | returns | 退货单详情 + 时间线 |
| `POST` | `/api/returns/{rma_no}/cancel` | 👤 user | returns | 撤销退货申请 |

## /api/subscriptions · 订阅盒（6 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `POST` | `/api/subscriptions` | 👤 user | subscriptions | 创建订阅（4/6/8 周计划） |
| `GET` | `/api/subscriptions/me` | 👤 user | subscriptions | 我的订阅 |
| `POST` | `/api/subscriptions/{sub_id}/cancel` | 👤 user | subscriptions | 取消订阅 |
| `POST` | `/api/subscriptions/{sub_id}/pause` | 👤 user | subscriptions | 暂停订阅 |
| `POST` | `/api/subscriptions/{sub_id}/resume` | 👤 user | subscriptions | 恢复订阅（续期） |
| `POST` | `/api/subscriptions/{sub_id}/skip` | 👤 user | subscriptions | 跳过一期订阅 |

## /api/support · 客服工单（4 个端点）

| 方法 | 路径 | 鉴权 | tags | 说明 |
|---|---|---|---|---|
| `GET` | `/api/support/templates` | 🌐 public | support | 快捷回复模板列表 |
| `GET` | `/api/support/tickets` | 🌐 public | support | 工单列表（登录仅自查；游客 ticket_no+email 双因子） |
| `POST` | `/api/support/tickets` | 🌐 public | support | 创建工单（游客可投，可关联订单） |
| `POST` | `/api/support/tickets/{ticket_no}/messages` | 🌐 public | support | 工单追加留言 |

## 常见响应约定（静态说明）

- **金额单位**：全部金额字段为**美分 int**（如 `3110` = $31.10），前端除以 100 展示；整型运算消除浮点误差。
- **游客购物车**：无需登录，携带请求头 `X-Cart-Token: <hex>`（首访由服务端签发并在响应头回写）；登录后调用 `POST /api/cart/merge` 合并。
- **鉴权头**：`Authorization: Bearer <jwt>`；后台端点要求 `role >= 2`（运营/仓库/超管），否则 403 `Admin only`。
- **错误风格**：失败返回 4xx/5xx + `{"detail": "<原因短语>"}`（如 401 `Not authenticated`、409 库存不足、429 限流附 `Retry-After`）。
- **列表分页**：统一 `{items, total, page, size}` 结构（page 从 1 起）。
- **时间**：DATETIME 秒级 UTC（naive），前端自行转本地时区。
