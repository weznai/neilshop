/* GLOWMAG 前台 API 客户端（SPA 版：恒为 API 模式，Cookie 会话 + 服务端权威购物车）
 * 拆独立 API 域时：window.GM_API_BASE = 'https://api.glowmag.com'（需服务端 CORS 白名单）。 */

const API_BASE = window.GM_API_BASE || ''

const state = {
  cartToken: localStorage.getItem('gm_cart_token') || '',
}

export function authHeaders() {
  const h = { 'Content-Type': 'application/json' }
  if (state.cartToken) h['X-Cart-Token'] = state.cartToken
  return h
}

export async function req(method, path, body, opts) {
  const o = Object.assign(
    { method, headers: authHeaders(), credentials: 'same-origin' },
    opts || {},
  )
  if (body !== undefined) o.body = JSON.stringify(body)
  const r = await fetch(API_BASE + path, o)
  const tok = r.headers.get('X-Cart-Token')
  if (tok && tok !== state.cartToken) {
    state.cartToken = tok
    localStorage.setItem('gm_cart_token', tok)
  }
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

/* 商品动态解析（内存缓存，替代旧 SLUGS 硬编码表） */
const _byId = {}
export function productDetail(pid) {
  if (!_byId[pid]) _byId[pid] = req('GET', '/api/catalog/products-by-id/' + pid)
  return _byId[pid]
}
