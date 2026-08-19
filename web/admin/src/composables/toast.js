/* 全局 toast（composable）：任意组件/页面可用，不依赖 AdminLayout */
import { reactive } from 'vue'

const state = reactive({ toasts: [] })
let seq = 0

export function toast(msg, type = '') {
  const id = ++seq
  state.toasts.push({ id, msg, type })
  setTimeout(() => {
    const i = state.toasts.findIndex((t) => t.id === id)
    if (i > -1) state.toasts.splice(i, 1)
  }, 3200)
}

/* 挂到 window 供非 setup 上下文应急（保持旧调用兼容） */
window.$gmToast = toast

export function useToast() {
  return { state, toast }
}
