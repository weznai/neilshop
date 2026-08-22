/* 全站格式化工具：分转美元金额 / 后端 UTC 时间转本地时区显示（修复全站时间偏移） */
export function money(c) {
  return '$' + ((c || 0) / 100).toFixed(2)
}

export function dt(iso) {
  if (!iso) return ''
  const s = String(iso)
  /* 后端 ISO 无时区后缀（按 UTC 存储）——必须补 'Z' 再转本地；已带 Z/±HH:MM 的原样解析 */
  const d = new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(s) ? s : s + 'Z')
  if (isNaN(d.getTime())) return ''
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/* 仅日期（YYYY-MM-DD）：复用 dt 的补 Z 本地化口径，供列表“日期粒度”列使用（替代 UTC 直切 slice(0,10)） */
export function dDate(iso) {
  return dt(iso).slice(0, 10)
}
