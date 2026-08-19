import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 前台门店 SPA：开发代理 /api → 本地 FastAPI；产物并入 web/dist（统一发布目录）
// 注意：构建顺序必须 client 先于 admin（client 的 emptyOutDir 会清空整个 dist）
export default defineConfig({
  plugins: [vue()],
  build: { outDir: '../dist', emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
