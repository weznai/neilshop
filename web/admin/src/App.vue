<script setup>
import { onMounted } from 'vue'
import { useSessionStore } from './stores/session'

const session = useSessionStore()

/* 应用启动即校验后台会话（路由守卫兜底） */
onMounted(async () => {
  if (session.user) {
    try { await session.verify() } catch (_) { session._cache(null) }
  }
})
</script>

<template>
  <router-view />
</template>

<style>
/* 全局轻提示（替代旧 toast） */
.gm-toast-wrap{position:fixed;top:18px;right:18px;z-index:9999;display:grid;gap:8px}
.gm-toast{background:var(--ink);color:#fff;font-size:13px;padding:10px 16px;border-radius:10px;box-shadow:var(--shadow-pop);animation:gmTIn .25s ease-out}
.gm-toast.success{background:var(--success)}
.gm-toast.error{background:var(--error)}
@keyframes gmTIn{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
</style>
