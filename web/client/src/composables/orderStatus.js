/* 订单状态共享映射 —— 对齐 server/app/core/enums.py OrderStatus（禁止 6/7 幻影下标）
 * 0待付 1已付 2履约中(拣货打包) 3已发货 4已送达 5已完成 8已取消 9已退款 */
import { i18n } from '../i18n'

export const OSTATUS = {
  0: ['Pending payment', '待付款', 'tag-pending'],
  1: ['Paid', '已支付', 'tag-paid'],
  2: ['Packing', '备货中', 'tag-pending'],
  3: ['Shipped', '已发货', 'tag-ship'],
  4: ['Delivered', '已送达', 'tag-ship'],
  5: ['Completed', '已完成', 'tag-done'],
  8: ['Cancelled', '已取消', 'tag-error'],
  9: ['Refunded', '已退款', 'tag-error'],
}

export function statusLabel(s) {
  const row = OSTATUS[s]
  if (!row) return i18n.lang === 'zh' ? '未知' : 'Unknown'
  return i18n.lang === 'zh' ? row[1] : row[0]
}

export function statusTag(s) {
  return (OSTATUS[s] || [])[2] || 'tag-pending'
}
