/* 交易/工单域共享映射：订单/订单详情/退换货/工单四视图共用（收敛各页重复定义，值以 models 真值为准） */

/* Order.status：0待支付 1已支付 2备货中 3已发货 4已送达 5已完成 8已取消 9已退款 */
export const OSTATUS = {
  0: { label: '待支付', cls: 'tag-pending' },
  1: { label: '已支付', cls: 'tag-paid' },
  2: { label: '备货中', cls: 'tag-pending' },
  3: { label: '已发货', cls: 'tag-ship' },
  4: { label: '已送达', cls: 'tag-ship' },
  5: { label: '已完成', cls: 'tag-done' },
  8: { label: '已取消', cls: 'tag-error' },
  9: { label: '已退款', cls: 'tag-error' },
}

/* Order.shipping_status（订单表字段，非 Shipment 表状态）：0未发货 1部分发货 2已全部发货 */
export const OSHIP = {
  0: { label: '未发货', cls: 'tag-pending' },
  1: { label: '部分发货', cls: 'tag-pending' },
  2: { label: '已发货', cls: 'tag-ship' },
}

/* Shipment.status：0待打单 1已打单待拣货 2待交接 3运输中 4送达 5异常 6面单作废 */
export const SHIP = {
  0: { label: '待打单', cls: 'tag-pending' },
  1: { label: '待拣货', cls: 'tag-pending' },
  2: { label: '待交接', cls: 'tag-pending' },
  3: { label: '运输中', cls: 'tag-ship' },
  4: { label: '已送达', cls: 'tag-done' },
  5: { label: '异常', cls: 'tag-error' },
  6: { label: '面单作废', cls: 'tag-error' },
}

/* PaymentStatus：0待支付 1成功 2失败 3已退款 4部分退款（退款语义统一红） */
export const PAY = {
  0: { label: '待支付', cls: 'tag-pending' },
  1: { label: '支付成功', cls: 'tag-paid' },
  2: { label: '支付失败', cls: 'tag-error' },
  3: { label: '已退款', cls: 'tag-error' },
  4: { label: '部分退款', cls: 'tag-ship' },
}

/* RmaStatus：0待审核 1已批准 2标签已发(待收货) 3在途 4已收货 5已退款 6已拒绝 7部分退款 */
export const RMA_STATUS = {
  0: { label: '待审核', cls: 'tag-pending' },
  1: { label: '已批准', cls: 'tag-paid' },
  2: { label: '标签已发', cls: 'tag-paid' },
  3: { label: '退货运送中', cls: 'tag-pending' },
  4: { label: '已收货', cls: 'tag-ship' },
  5: { label: '已退款', cls: 'tag-done' },
  6: { label: '已拒绝', cls: 'tag-error' },
  7: { label: '部分退款', cls: 'tag-done' },
}

/* ExchangeStatus：0待审核 1已批准待重发 2待买家补差价 3已重发 4已完成 5已拒绝 */
export const ESTATUS = {
  0: { label: '待审核', cls: 'tag-pending' },
  1: { label: '已批准·待重发', cls: 'tag-paid' },
  2: { label: '待买家付差价', cls: 'tag-pending' },
  3: { label: '已重发', cls: 'tag-ship' },
  4: { label: '已完成', cls: 'tag-done' },
  5: { label: '已拒绝', cls: 'tag-error' },
}

/* RmaReason：1尺码不合 2质量问题 3不喜欢 4损坏 5发错货 6其他 */
export const RMA_REASON = { 1: '尺码不合', 2: '质量问题', 3: '不喜欢', 4: '损坏', 5: '发错货', 6: '其他' }

/* Ticket.status：0新工单 1处理中 2等待客户 3已解决 4已关闭 */
export const TSTATUS = {
  0: { label: '新工单', cls: 'tag-pending' },
  1: { label: '处理中', cls: 'tag-ship' },
  2: { label: '等待客户', cls: 'tag-pending' },
  3: { label: '已解决', cls: 'tag-paid' },
  4: { label: '已关闭', cls: 'tag-done' },
}

/* ===== 后端错误码 → 中文文案 =====
 * detail 形如 "not_shippable:1"（冒号后带参数），需按前缀匹配，见 mapErr() */

/* 订单写操作 */
export const ORDER_ERR = {
  not_shippable: '当前状态不可发货',
  only_pending_can_cancel: '仅待支付订单可取消',
  no_refundable_payment: '无的可退支付',
  already_fully_refunded: '该支付已全额退款',
  invalid_refund_amount: '退款金额超出可退余额',
  variant_out_of_stock: '库存不足',
}

/* RMA 写操作 */
export const RMA_ERR = {
  rma_not_rejectable: '仅待审核申请可拒绝',
  rma_not_approvable: '该申请不在待审核状态',
  rma_not_receivable: '当前状态不可收货',
  rma_not_refundable: '当前状态不可退款',
}

/* 换货写操作（detail 精确串采集自 service_exchanges.py，冒号后带当前状态码按前缀匹配） */
export const EXCH_ERR = {
  exchange_not_approvable: '当前状态不允许批准该换货',
  exchange_not_rejectable: '当前状态不允许拒绝该换货',
  exchange_not_awaiting_diff: '该换货不在待付差价状态',
  exchange_not_shippable: '当前状态不允许重发新商品',
  exchange_not_completable: '当前状态不可完成该换货',
  diff_already_paid: '差价已支付，请勿重复操作',
  variant_out_of_stock: '新变体库存不足',
  exchange_not_found: '换货单不存在',
}

/* 工单操作 */
export const TICKET_ERR = {
  invalid_status_transition: '非法状态流转',
  ticket_already_closed: '工单已关闭',
  'ticket closed': '工单已关闭，如需继续处理请先重开',
  'not ticket owner': '无权操作该工单（非工单所有者）',
  'ticket not found': '工单不存在',
}

/* 错误 detail 前缀匹配 → 映射文案（无匹配返回 ''，调用方回退原始 detail/message） */
export function mapErr(detail, map) {
  if (typeof detail !== 'string' || !detail) return ''
  return map[detail.split(':')[0]] || ''
}
