/**
 * 共享 CSV 导出工具：消除 6 个视图的重复导出代码
 * - 公式注入防护：= + - @ 开头前缀单引号
 * - 逗号/引号/换行字段自动包引号
 * - BOM 头兼容 Excel 中文
 */

/** CSV 单元格转义：公式注入防护 + 特殊字符包引号 */
export function csvCell(v) {
  let s = String(v ?? '')
  if (/^[=+\-@]/.test(s)) s = "'" + s
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}

/**
 * 导出 CSV 文件
 * @param {Object} opts
 * @param {string} opts.filename - 文件名（不含 .csv）
 * @param {string[]} opts.headers - 表头
 * @param {Array<Array>} opts.rows - 数据行
 */
export function downloadCsv({ filename, headers, rows }) {
  const all = [headers, ...rows]
  const csv = all.map((r) => r.map(csvCell).join(',')).join('\n')
  const url = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `${filename}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * 分页拉取全量数据（供 CSV 导出使用）
 * @param {Function} fetchFn - async (page) => { items, total }
 * @param {Object} opts
 * @param {number} opts.pageSize - 每页条数（默认 100）
 * @param {number} opts.maxPages - 最大页数（默认 50）
 * @returns {{ all: Array, truncated: boolean, total: number }}
 */
export async function fetchAllPages(fetchFn, { pageSize = 100, maxPages = 50 } = {}) {
  const first = await fetchFn(1)
  const all = [...(first.items || [])]
  const total = first.total ?? all.length
  const maxPage = Math.min(Math.ceil(total / pageSize) || 1, maxPages)

  for (let s = 2; s <= maxPage; s += 5) {
    const end = Math.min(s + 4, maxPage)
    const batch = await Promise.all(
      Array.from({ length: end - s + 1 }, (_, i) => fetchFn(s + i))
    )
    for (const d of batch) all.push(...(d.items || []))
  }

  const truncated = Math.ceil(total / pageSize) > maxPages
  return { all, truncated, total }
}
