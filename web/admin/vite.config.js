import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 后台 SPA：base /admin/（产物并入 web/dist/admin 统一发布，FastAPI 挂 web/dist 一个目录）
export default defineConfig({
  plugins: [vue()],
  base: '/admin/',
  build: {
    outDir: '../dist/admin',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // vue 家族独立 vendor chunk：与应用代码分离，可被浏览器并行加载与长效缓存
        manualChunks: { vendor: ['vue', 'vue-router', 'pinia'] },
      },
    },
  },
  server: {
    port: 5174,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
