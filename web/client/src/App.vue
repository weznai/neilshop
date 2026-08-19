<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useUiStore } from './stores/ui'
import { useCartStore } from './stores/cart'
import { useAuthStore } from './stores/auth'
import ToastHost from './components/ToastHost.vue'

const ui = useUiStore()
const cart = useCartStore()
const auth = useAuthStore()

/* ESC 关闭所有浮层（对齐旧 app.js 全局委托） */
function onKey(e) {
  if (e.key === 'Escape') ui.onEsc()
}

onMounted(() => {
  document.addEventListener('keydown', onKey)
  cart.refresh().catch(() => { /* 服务端不可达时保留本地快照 */ })
  if (auth.isLoggedIn) auth.me().catch(() => auth._cache(null))
})
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <router-view />
  <ToastHost />
</template>
