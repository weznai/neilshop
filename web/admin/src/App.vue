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
/* 全局轻提示（原 AdminLayout 内样式移此，全站可用）
 * v2：关闭按钮 + 退场动画（.out → gmTOut）；错误类由 toast composable 存续 5s */
.gm-toast-wrap{position:fixed;top:18px;right:18px;z-index:9999;display:grid;gap:8px}
.gm-toast{background:var(--ink);color:#fff;font-size:13px;padding:10px 12px 10px 16px;border-radius:10px;box-shadow:var(--shadow-pop);animation:gmTIn .25s ease-out;max-width:340px;display:flex;align-items:flex-start;gap:10px}
.gm-toast.success{background:var(--success)}
.gm-toast.error{background:var(--error)}
.gm-toast.out{animation:gmTOut .2s ease-in forwards}
.gm-toast-msg{flex:1;min-width:0;word-break:break-word}
.gm-toast-x{flex:none;background:none;border:none;color:rgba(255,255,255,.72);font-size:15px;line-height:1.15;cursor:pointer;padding:0 2px;border-radius:4px}
.gm-toast-x:hover{color:#fff}
@keyframes gmTIn{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
@keyframes gmTOut{to{opacity:0;transform:translateX(14px)}}
</style>
