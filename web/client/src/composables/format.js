/* 金额统一格式化：美分 → $x.xx；nullTbd 时 null/undefined 显示 TBD（退货预计退款等未知金额） */
import { tt } from '../i18n'

export function money(cents, { nullTbd } = {}) {
  if (cents === null || cents === undefined) return nullTbd ? tt('TBD', '待定') : '$0.00'
  return '$' + (cents / 100).toFixed(2)
}
