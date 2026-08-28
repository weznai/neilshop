import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 前台门店 SPA：开发代理 /api → 本地 FastAPI；产物并入 web/dist（统一发布目录）
// 注意：构建顺序必须 client 先于 admin（client 的 emptyOutDir 会清空整个 dist）
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // vue 家族独立 vendor chunk：与应用代码分离，可被浏览器并行加载与长效缓存
        manualChunks: { vendor: ['vue', 'vue-router', 'pinia'] },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      // 后端静态资源（商品/评价等本地上传图片 /static/uploads 直链，与 admin 口径一致）
      '/static': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
