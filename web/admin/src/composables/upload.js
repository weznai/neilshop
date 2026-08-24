/* 统一图片上传（POST /api/admin/media/upload：multipart 字段 file，png/jpg/jpeg/webp/gif ≤5MB）
 * 401 → 广播 gm-admin-401（App.vue 接管跳登录）；403 → 仅 toast 提示（对齐 api/client.js：不清会话不跳转） */
import { API_BASE, fmtDetail } from '../api/client'
import { toast } from '../composables/toast'

export async function uploadMedia(file) {
  const fd = new FormData()
  fd.append('file', file)
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 30000)
  let r
  try { r = await fetch(API_BASE + '/api/admin/media/upload', { method: 'POST', credentials: 'include', body: fd, signal: ctrl.signal }) }
  catch (err) { throw new Error(err && err.name === 'AbortError' ? '上传超时，请稍后重试' : '网络错误，请检查连接') }
  finally { clearTimeout(timer) }
  const data = await r.json().catch(() => null)
  if (r.ok) {
    if (!data || !data.url) throw new Error('响应缺少 url')
    return data.url
  }
  if (r.status === 401) window.dispatchEvent(new CustomEvent('gm-admin-401'))
  /* 权限不足：会话仍有效（401 才代表过期），仅就地提示，不跳转、不清会话（与 api/client.js 403 口径一致） */
  if (r.status === 403) toast('无权限执行该操作', 'error')
  const e = new Error(fmtDetail(data && data.detail) || 'HTTP ' + r.status)
  e.status = r.status
  throw e
}

/* 上传错误 → 中文提示；401/403 已全局兜底返回空串（调用方判空跳过 toast） */
export function uploadErrText(err) {
  const s = err && err.status
  if (s === 401 || s === 403) return ''
  if (s === 413) return '图片不能超过 5MB'
  if (s === 400 || s === 422) return '仅支持 PNG/JPG/WebP/GIF 图片'
  return '上传失败：' + (err?.message || '')
}
