/* 政策页「最后更新」统一口径：四页共用，改版只动这里 */
export const LAST_UPDATED = '2026-08'

const MON_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function updatedLabel(tt) {
  const y = LAST_UPDATED.slice(0, 4)
  const m = parseInt(LAST_UPDATED.slice(5), 10)
  return tt('Last updated: ' + MON_EN[m - 1] + ' ' + y, '最后更新：' + y + ' 年 ' + m)
}
