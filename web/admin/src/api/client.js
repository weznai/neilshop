/* GLOWMAG 后台 API 客户端（独立站点 · Cookie gm_admin_token 会话）
 * 拆独立 API 域时：window.GM_ADMIN_API_BASE = 'https://api.glowmag.com'
 * 并在服务端 GM_ALLOWED_ORIGINS 白名单加上后台域名。 */
const API_BASE = window.GM_ADMIN_API_BASE || ''

export async function req(method, path, body) {
  const o = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  }
  if (body !== undefined) o.body = JSON.stringify(body)
  const r = await fetch(API_BASE + path, o)
  let data = null
  try { data = await r.json() } catch (_) { /* 204 etc */ }
  if (!r.ok) {
    const e = new Error((data && data.detail) || 'HTTP ' + r.status)
    e.status = r.status
    e.data = data
    throw e
  }
  return data
}
