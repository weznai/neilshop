/* GLOWMAG 后台 API 客户端（独立站点 · Cookie gm_admin_token 会话）
 * 拆独立 API 域时：window.GM_ADMIN_API_BASE = 'https://api.glowmag.com'
  * 并在服务端 GM_ALLOWED_ORIGINS 白名单加上后台域名。 */
import { toast } from '../composables/toast'

export const API_BASE = window.GM_ADMIN_API_BASE || ''

const TIMEOUT_MS = 30000
let fired401 = false   /* 并发请求同时 401 只广播一次 */
let fired403 = false   /* 并发请求同时 403 只提示/跳转一次 */

/* FastAPI 错误 detail 统一格式化（与 web/client 同款）：
 * - string → 原样
 * - list[dict]（422 校验）→ "field: msg; field2: msg2"（loc 取末段）
 * - object → 取 msg/detail 字段，兜底 JSON 串 */
export function fmtDetail(detail) {
  if (detail == null) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (d && typeof d === 'object') {
          const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== 'body').pop() : ''
          return field ? field + ': ' + (d.msg || 'invalid') : (d.msg || 'invalid')
        }
        return String(d)
      })
      .join('; ')
  }
  if (typeof detail === 'object') return (detail.msg || detail.detail) || JSON.stringify(detail)
  return String(detail)
}

/* opts 可选：{ credentials } 透传 fetch（默认 'include'；'omit' 用于匿名端点不发 cookie）；
 * { timeout } 覆盖默认 30s 超时（毫秒，如 RAG 全量重建等长耗时操作） */
export async function req(method, path, body, opts) {
  const o = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: opts?.credentials || 'include',
  }
  if (body !== undefined) o.body = JSON.stringify(body)
  const ctrl = new AbortController()
  o.signal = ctrl.signal
  const timer = setTimeout(() => ctrl.abort(), opts?.timeout || TIMEOUT_MS)
  let r
  try {
    r = await fetch(API_BASE + path, o)
  } catch (err) {
    throw new Error(err && err.name === 'AbortError' ? '请求超时，请稍后重试' : '网络错误，请检查连接')
  } finally {
    clearTimeout(timer)
  }
  let data = null
  try { data = await r.json() } catch (_) { /* 204 etc */ }
  if (!r.ok) {
    /* 会话过期统一广播（登录接口自身除外）；App.vue 收口跳登录页 */
    if (r.status === 401 && !path.includes('/login') && !fired401) {
      fired401 = true
      window.dispatchEvent(new CustomEvent('gm-admin-401'))
      setTimeout(() => { fired401 = false }, 3000)
    }
    /* 权限不足（/api/admin/ 前缀且非登录接口）：仅 toast 提示，不清会话不跳转 ——
     * 会话仍有效（401 才代表过期），按钮级越权由调用方就地处理 */
    if (r.status === 403 && path.startsWith('/api/admin/') && !path.includes('/login') && !fired403) {
      fired403 = true
      toast('当前账号无此操作权限', 'error')
      setTimeout(() => { fired403 = false }, 3000)
    }
    const e = new Error(fmtDetail(data && data.detail) || 'HTTP ' + r.status)
    e.status = r.status
    /* 非 string detail（422 数组/对象）换成格式化字符串，杜绝视图层拼出 [object Object] */
    e.data = data && typeof data.detail !== 'string' && data.detail != null ? { ...data, detail: e.message } : data
    throw e
  }
  return data
}
