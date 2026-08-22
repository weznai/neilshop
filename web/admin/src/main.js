import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { toast } from './composables/toast'
import './assets/style.css'
import './assets/admin.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
/* 全局渲染异常兜底：控制台留痕 + toast 提示（不白屏） */
app.config.errorHandler = (err) => {
  console.error(err)
  toast('页面渲染出错，请刷新重试', 'error')
}
app.mount('#app')
