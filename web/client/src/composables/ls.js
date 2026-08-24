/* localStorage 安全读写：隐私模式 / 配额异常时静默降级 */
export function lsGet(k) {
  try { return localStorage.getItem(k) } catch (_) { return null }
}
export function lsSet(k, v) {
  try { localStorage.setItem(k, v) } catch (_) { /* 隐私模式忽略 */ }
}
export function lsDel(k) {
  try { localStorage.removeItem(k) } catch (_) { /* 隐私模式忽略 */ }
}
