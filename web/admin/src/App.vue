<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from './stores/session'
import ToastHost from './components/ToastHost.vue'
import { toast } from './composables/toast'

const session = useSessionStore()
const router = useRouter()

/* 应用启动即校验后台会话（路由守卫兜底；失败静默——用户未登录是正常态） */
onMounted(async () => {
  if (session.user) {
    try { await session.verify() } catch (_) { session._cache(null) }
  }
  /* 会话过期（任意 API 401）：清本地缓存 → 提示 → 回登录页（带 next 便于重登续位） */
  window.addEventListener('gm-admin-401', onSessionExpired)
})
onBeforeUnmount(() => window.removeEventListener('gm-admin-401', onSessionExpired))

function onSessionExpired() {
  if (router.currentRoute.value.path === '/login') return
  session._cache(null)
  toast('登录已过期，请重新登录', 'error')
  router.push({ path: '/login', query: { next: router.currentRoute.value.fullPath } })
}
</script>

<template>
  <router-view />
  <ToastHost />
</template>

<style>
/* 全局轻提示（原 AdminLayout 内样式移此，全站可用） */
.gm-toast-wrap{position:fixed;top:18px;right:18px;z-index:9999;display:grid;gap:8px}
.gm-toast{background:var(--ink);color:#fff;font-size:13px;padding:10px 16px;border-radius:10px;box-shadow:var(--shadow-pop);animation:gmTIn .25s ease-out;max-width:340px}
.gm-toast.success{background:var(--success)}
.gm-toast.error{background:var(--error)}
@keyframes gmTIn{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
</style>
