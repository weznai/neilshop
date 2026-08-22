/* 时间统一处理：后端时间为 naive UTC ISO 串（无 Z 后缀），new Date() 按本地时区解析会偏移；
   zulu() 补 Z 归一为 UTC，格式化沿用项目既有风格（同年省年份 / YYYY-MM-DD） */

export function zulu(iso) {
  if (typeof iso !== 'string') return iso
  if (/z$/i.test(iso) || /[+-]\d{2}:?\d{2}$/.test(iso)) return iso
  return iso + 'Z'
}

const p2 = (n) => String(n).padStart(2, '0')

export function fmtDateTime(iso, empty = '—') {
  if (!iso) return empty
  const d = new Date(zulu(iso))
  if (isNaN(d)) return empty
  const hm = `${p2(d.getHours())}:${p2(d.getMinutes())}`
  return d.getFullYear() === new Date().getFullYear()
    ? `${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${hm}`
    : `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${hm}`
}

export function fmtDate(iso, empty = '—') {
  if (!iso) return empty
  const d = new Date(zulu(iso))
  if (isNaN(d)) return empty
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`
}
