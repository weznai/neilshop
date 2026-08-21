/* 全局 toast（composable）：任意组件/页面可用，不依赖 AdminLayout
 * v2：错误类存续 5s / 堆叠上限 4 条 / 可手动关闭（dismiss）/ 退场动画标记（leaving） */
import { reactive } from 'vue'

const state = reactive({ toasts: [] })
let seq = 0
const MAX_TOASTS = 4
const EXIT_MS = 200

/* 关闭：先标记 leaving 触发退场动画，动画结束后移除 */
function dismiss(id) {
  const t = state.toasts.find((x) => x.id === id)
  if (!t || t.leaving) return
  t.leaving = true
  setTimeout(() => {
    const i = state.toasts.findIndex((x) => x.id === id)
    if (i > -1) state.toasts.splice(i, 1)
  }, EXIT_MS)
}

export function toast(msg, type = '') {
  const id = ++seq
  /* 堆叠上限：把最早的「存活」toast 挤出去（已退场中的不重复计数） */
  const live = state.toasts.filter((t) => !t.leaving)
  while (live.length >= MAX_TOASTS) dismiss(live.shift().id)
  state.toasts.push({ id, msg, type, leaving: false })
  setTimeout(() => dismiss(id), type === 'error' ? 5000 : 3200)
}

/* 挂到 window 供非 setup 上下文应急（保持旧调用兼容） */
window.$gmToast = toast

export function useToast() {
  return { state, toast, dismiss }
}
