<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from './stores/session'
import ToastHost from './components/ToastHost.vue'
import { toast } from './composables/toast'

const session = useSessionStore()
const router = useRouter()

/* 启动即校验已移除：AdminLayout 守卫对所有后台路由做权威 verify()（含 role 检查），
 * 此处重复调用只会在硬加载时多发一次 /admin/me；/login 页无人依赖刷新后的 user 快照 */
onMounted(() => {
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
 * v2：关闭按钮 + 退场动画（.out → gmTOut）；错误类由 toast composable 存续 5s
 * v3：z-index 9999 → 1200（对齐 admin.css 顶部刻度表）；新增左侧状态图标（白底圆片 + 语义色描边，深浅底 toast 均可读） */
.gm-toast-wrap{position:fixed;top:18px;right:18px;z-index:1200;display:grid;gap:8px}
.gm-toast{background:var(--ink);color:#fff;font-size:13px;padding:10px 12px 10px 14px;border-radius:10px;box-shadow:var(--shadow-pop);animation:gmTIn .25s ease-out;max-width:340px;display:flex;align-items:flex-start;gap:10px}
.gm-toast.success{background:var(--success)}
.gm-toast.error{background:var(--error)}
.gm-toast.out{animation:gmTOut .2s ease-in forwards}
.gm-toast-ico{flex:none;width:18px;height:18px;margin-top:1px;border-radius:50%;background:rgba(255,255,255,.92);display:inline-flex;align-items:center;justify-content:center}
.gm-toast-ico svg{width:11px;height:11px;fill:none;stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round}
.gm-toast-ico.success svg{stroke:var(--success)}
.gm-toast-ico.error svg{stroke:var(--error)}
.gm-toast-ico.info svg{stroke:var(--gray)}
.gm-toast-msg{flex:1;min-width:0;word-break:break-word}
.gm-toast-x{flex:none;background:none;border:none;color:rgba(255,255,255,.72);font-size:15px;line-height:1.15;cursor:pointer;padding:0 2px;border-radius:4px}
.gm-toast-x:hover{color:#fff}
@keyframes gmTIn{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
@keyframes gmTOut{to{opacity:0;transform:translateX(14px)}}
</style>
