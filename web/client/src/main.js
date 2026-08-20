import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { useUiStore } from './stores/ui'
import './assets/style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

/* 全局错误兜底：渲染/生命周期异常 → console 保留完整堆栈，用户侧仅见轻提示 */
app.config.errorHandler = (err, instance, info) => {
  console.error('[GLOWMAG]', info, err)
  try { useUiStore().toast('Something went wrong — please refresh', 'error') } catch (_) { /* pinia 未就绪的极端场景 */ }
}

app.mount('#app')
