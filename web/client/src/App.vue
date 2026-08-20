<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUiStore } from './stores/ui'
import { useCartStore } from './stores/cart'
import { useAuthStore } from './stores/auth'
import ToastHost from './components/ToastHost.vue'

const ui = useUiStore()
const cart = useCartStore()
const auth = useAuthStore()
const router = useRouter()

/* ESC 关闭所有浮层（对齐旧 app.js 全局委托） */
function onKey(e) {
  if (e.key === 'Escape') ui.onEsc()
}

/* 401 会话过期收口（client.js 只广播事件）：HttpOnly Cookie 由服务端管理，此处清 gm_user
 * 本地缓存；仅当本地确有登录态时才提示+跳登录（游客请求可选接口的 401 不打扰），3s 去抖防并发风暴 */
let _authExpiredAt = 0
function onAuthExpired() {
  const wasLoggedIn = !!auth.user
  auth._cache(null)
  auth.points = null
  if (!wasLoggedIn) return
  const now = Date.now()
  if (now - _authExpiredAt < 3000) return
  _authExpiredAt = now
  const cur = router.currentRoute.value
  if (cur.path !== '/login' && cur.path !== '/register') {
    ui.toast('Session expired — please sign in again', 'error')
    router.push({ path: '/login', query: { next: cur.fullPath } })
  }
}

/* 顶栏请求进度条：监听 client.js pending 0↔1 边沿事件，run（缓进 80%）→ done（冲 100% 淡出） */
const barState = ref('')
let barTimer = null
function onPendingOn() {
  clearTimeout(barTimer)
  barState.value = 'run'
}
function onPendingOff() {
  if (barState.value === 'run') {
    barState.value = 'done'
    barTimer = setTimeout(() => { barState.value = '' }, 400)
  }
}

/* 移动端 TabBar 让位：.tabbar 为 fixed，body.has-tabbar 预留底部空间（样式规则已有，此处挂载） */
const mq = window.matchMedia('(max-width: 768px)')
function onMq() { document.body.classList.toggle('has-tabbar', mq.matches) }

onMounted(() => {
  document.addEventListener('keydown', onKey)
  window.addEventListener('gm:auth-expired', onAuthExpired)
  window.addEventListener('gm:pending-on', onPendingOn)
  window.addEventListener('gm:pending-off', onPendingOff)
  if (mq.addEventListener) mq.addEventListener('change', onMq)
  else if (mq.addListener) mq.addListener(onMq)
  onMq()
  cart.refresh().catch(() => { /* 服务端不可达时保留本地快照 */ })
  if (auth.isLoggedIn) auth.me().catch(() => auth._cache(null))
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKey)
  window.removeEventListener('gm:auth-expired', onAuthExpired)
  window.removeEventListener('gm:pending-on', onPendingOn)
  window.removeEventListener('gm:pending-off', onPendingOff)
  if (mq.removeEventListener) mq.removeEventListener('change', onMq)
  else if (mq.removeListener) mq.removeListener(onMq)
  clearTimeout(barTimer)
})
</script>

<template>
  <div class="gm-progress" :data-state="barState" aria-hidden="true"></div>
  <router-view />
  <ToastHost />
</template>
