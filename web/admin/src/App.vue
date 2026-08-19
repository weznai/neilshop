<script setup>
import { onMounted } from 'vue'
import { useSessionStore } from './stores/session'
import ToastHost from './components/ToastHost.vue'

const session = useSessionStore()

/* 应用启动即校验后台会话（路由守卫兜底；失败静默——用户未登录是正常态） */
onMounted(async () => {
  if (session.user) {
    try { await session.verify() } catch (_) { session._cache(null) }
  }
})
</script>

<template>
  <router-view />
  <ToastHost />
</template>
