<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
/* 返回上一页：无历史记录（直链进入）时兜底回仪表盘 */
function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}
</script>

<template>
  <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg-page)">
    <div class="card" style="padding:44px 52px;text-align:center;max-width:400px">
      <div style="font-family:var(--font-title);font-size:46px;font-weight:800;color:var(--plum);letter-spacing:-1px">404</div>
      <div style="font-size:15px;font-weight:700;margin:10px 0 4px">页面不存在</div>
      <div style="font-size:12.5px;color:var(--gray);margin-bottom:20px">访问的地址不存在或已被移除。</div>
      <div style="display:flex;gap:10px;justify-content:center">
        <button class="btn btn-secondary" @click="goBack">← 返回上一页</button>
        <router-link to="/" class="btn btn-primary">回仪表盘</router-link>
      </div>
    </div>
  </div>
</template>
