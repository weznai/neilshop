import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 后台 SPA：base /admin/（产物并入 web/dist/admin 统一发布，FastAPI 挂 web/dist 一个目录）
export default defineConfig({
  plugins: [vue()],
  base: '/admin/',
  build: { outDir: '../dist/admin', emptyOutDir: true },
  server: {
    port: 5174,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
