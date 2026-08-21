/* GLOWMAG 前台 API 客户端（SPA 版：恒为 API 模式，Cookie 会话 + 服务端权威购物车）
 * 拆独立 API 域时：window.GM_API_BASE = 'https://api.glowmag.com'（需服务端 CORS 白名单）。 */

const API_BASE = window.GM_API_BASE || ''
const DEFAULT_TIMEOUT = 15000

/* 这些端点自身的 401 是业务结果（密码错/未登录可选接口），不广播会话过期 */
const AUTH_401_SKIP = ['/api/account/login', '/api/account/register']

const state = {
  cartToken: localStorage.getItem('gm_cart_token') || '',
}

/* 全局 pending 计数：0↔1 边沿广播事件，App.vue 收口驱动顶栏细进度条（与 store 解耦） */
let _pending = 0
function _pendingStart() {
  if (_pending++ === 0) window.dispatchEvent(new Event('gm:pending-on'))
}
function _pendingEnd() {
  _pending = Math.max(0, _pending - 1)
  if (_pending === 0) window.dispatchEvent(new Event('gm:pending-off'))
}

export function authHeaders() {
  const h = { 'Content-Type': 'application/json' }
  if (state.cartToken) h['X-Cart-Token'] = state.cartToken
  return h
}

/* FastAPI 错误 detail 统一格式化：
 * - string → 原样
 * - list[dict]（422 校验）→ "field: msg; field2: msg2"
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
  if (typeof detail === 'object') return d_msg(detail) || JSON.stringify(detail)
  return String(detail)
}
function d_msg(o) { return o.msg || o.detail || '' }

/* 页面通用错误文案：catch (e) → ui.toast(errMessage(e), 'error') */
export function errMessage(e) {
  if (!e) return 'Request failed'
  return fmtDetail(e.data && e.data.detail) || e.message || 'Request failed'
}

export async function req(method, path, body, opts) {
  const o = Object.assign(
    { method, headers: authHeaders(), credentials: 'same-origin', timeout: DEFAULT_TIMEOUT },
    opts || {},
  )
  if (body !== undefined) o.body = JSON.stringify(body)
  const ctrl = new AbortController()
  o.signal = ctrl.signal
  const timer = setTimeout(() => ctrl.abort(), o.timeout)
  let r
  _pendingStart()
  try {
    r = await fetch(API_BASE + path, o)
  } catch (netErr) {
    const e = netErr && netErr.name === 'AbortError'
      ? new Error('Request timed out — please retry')
      : new Error('Network unreachable — please check your connection')
    e.status = 0
    throw e
  } finally {
    clearTimeout(timer)
    _pendingEnd()
  }
  const tok = r.headers.get('X-Cart-Token')
  if (tok && tok !== state.cartToken) {
    state.cartToken = tok
    localStorage.setItem('gm_cart_token', tok)
  }
  let data = null
  try { data = await r.json() } catch (_) { /* 204 etc */ }
  if (!r.ok) {
    const e = new Error(fmtDetail(data && data.detail) || 'HTTP ' + r.status)
    e.status = r.status
    e.data = data
    /* 会话过期统一广播（HttpOnly Cookie 失效）：App.vue 收口清 gm_user 缓存并跳登录 */
    if (r.status === 401 && !AUTH_401_SKIP.includes(path)) {
      window.dispatchEvent(new Event('gm:auth-expired'))
    }
    throw e
  }
  return data
}

/* 商品动态解析（内存缓存 + 60s TTL，替代旧 SLUGS 硬编码表）；
   在途请求 at=Infinity 不判过期；rejected promise 不滞留缓存（重进可重试） */
const _byId = {}
const DETAIL_TTL = 60000
export function productDetail(pid) {
  const hit = _byId[pid]
  if (hit && Date.now() - hit.at < DETAIL_TTL) return hit.promise
  const rec = { at: Infinity, promise: null }
  rec.promise = req('GET', '/api/catalog/products-by-id/' + pid)
    .then((d) => { rec.at = Date.now(); return d })
    .catch((e) => { if (_byId[pid] === rec) delete _byId[pid]; throw e })
  _byId[pid] = rec
  return rec.promise
}

/* 心愿单：加入 / 查询是否已收藏 / 移除（端点形态对齐 WishlistView：POST|DELETE /api/account/wishlist/{pid}）
   _wlKnown 会话内缓存已确认收藏的 id，避免 PDP 重复发 has 请求 */
const _wlKnown = new Set()
export function wishlistAdd(pid) {
  return req('POST', '/api/account/wishlist/' + pid).then((d) => { _wlKnown.add(pid); return d })
}
export function wishlistHas(pid) {
  if (_wlKnown.has(pid)) return Promise.resolve(true)
  return req('GET', '/api/account/wishlist/has?product_id=' + pid).then((d) => {
    const hit = !!(d && d.in_wishlist)
    if (hit) _wlKnown.add(pid)
    return hit
  })
}
export function wishlistRemove(pid) {
  return req('DELETE', '/api/account/wishlist/' + pid).then((d) => { _wlKnown.delete(pid); return d })
}
