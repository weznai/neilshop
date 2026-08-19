<script setup>
/* 后台外壳：侧栏（admin.css anav）+ 顶栏 + 守卫（toast 走全局 composable） */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const guard = ref(true)
const guardErr = ref('')
const collapsed = ref(localStorage.getItem('gm_side_min') === '1')

const P = {
  dash: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  orders: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
  returns: '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
  tickets: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  products: '<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/>',
  inventory: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  promo: '<line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
  content: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  members: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  settings: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  store: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  panel: '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>',
}
const ITEMS = [
  ['dash', '数据看板', '/'],
  ['orders', '订单管理', '/orders'],
  ['returns', '退货审核', '/returns'],
  ['tickets', '客服工单', '/tickets'],
  '-',
  ['products', '商品管理', '/products'],
  ['inventory', '库存中心', '/inventory'],
  ['promo', '营销工具', '/marketing'],
  ['content', '内容管理', '/content'],
  '-',
  ['members', '会员管理', '/members'],
  ['settings', '系统设置', '/settings'],
]

const toasts = ref([])
let seq = 0
function toastLocal(msg, type = '') {
  const id = ++seq
  toasts.value.push({ id, msg, type })
  setTimeout(() => { toasts.value = toasts.value.filter((t) => t.id !== id) }, 2400)
}
window.$gmToast = toast

function toggleSide() {
  collapsed.value = !collapsed.value
  localStorage.setItem('gm_side_min', collapsed.value ? '1' : '0')
}
async function logout() {
  await session.logout()
  router.push('/login')
}

onMounted(async () => {
  try {
    const u = await session.verify()
    if ((u.role | 0) < 2) throw new Error('该账号无后台权限（role=' + (u.role | 0) + '）')
    guard.value = false
  } catch (e) {
    console.error('[admin] 会话校验失败：', e)
    guardErr.value = (e && e.status ? 'HTTP ' + e.status + ' · ' : '') + (e.message || '会话无效')
    session._cache(null)
    /* 停 1.2s 让用户看到失败原因，再回登录页 */
    setTimeout(() => router.push('/login'), 1200)
  }
})
</script>

<template>
  <div v-if="!guard" class="admin" :class="{ 'side-min': collapsed }">
    <aside class="aside" id="admSide">
      <router-link class="logo" to="/">GLOW<span>MAG</span></router-link>
      <div style="font-size:10px;letter-spacing:2px;color:var(--gray);padding:0 12px 14px">管理控制台</div>
      <nav class="anav">
        <template v-for="(it, i) in ITEMS" :key="i">
          <div v-if="it === '-'" class="sep"></div>
          <router-link v-else :to="it[2]" :class="{ on: route.path === it[2] }" :title="it[1]">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="flex:none" v-html="P[it[0]]" />
            <span>{{ it[1] }}</span>
          </router-link>
        </template>
        <div class="sep"></div>
        <a href="/" title="查看店铺">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="flex:none" v-html="P.store" />
          <span>查看店铺</span>
        </a>
        <div class="sep"></div>
        <a href="javascript:void(0)" title="退出登录" @click="logout">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="flex:none" v-html="P.logout" />
          <span>退出登录</span>
        </a>
      </nav>
      <button class="side-toggle" title="折叠/展开侧栏" aria-label="折叠或展开侧栏" @click="toggleSide">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" v-html="P.panel" />
      </button>
    </aside>

    <main class="main">
      <router-view />
    </main>
  </div>
  <div v-else class="admin" style="align-items:center;justify-content:center">
    <div style="text-align:center;color:var(--gray)">
      <div style="font-size:34px;margin-bottom:8px">⏳</div>正在验证管理会话…
    </div>
  </div>

  <div class="gm-toast-wrap">
    <div v-for="t in toasts" :key="t.id" class="gm-toast" :class="t.type">{{ t.msg }}</div>
  </div>
</template>
