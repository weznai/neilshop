<script setup>
/* 403 无权访问页：router.beforeEach 权限拦截目标（会话仍有效，仅无该面权限） */
import { useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { firstAllowedPath } from '../constants/nav'

const router = useRouter()
const session = useSessionStore()
function backHome() {
  router.push(firstAllowedPath(session.hasPerm))
}
</script>

<template>
  <div class="forbidden">
    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="var(--error)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
    <div class="title">无权访问该页面</div>
    <div class="desc">当前账号（{{ session.name }}）没有此功能面的权限，如需开通请联系超管调整角色。</div>
    <button class="btn btn-primary" @click="backHome">返回工作台</button>
  </div>
</template>

<style scoped>
.forbidden{min-height:60vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;text-align:center}
.title{font-size:15px;font-weight:700;color:var(--ink);margin-top:4px}
.desc{font-size:12.5px;color:var(--gray);max-width:360px}
.btn{margin-top:10px}
</style>
