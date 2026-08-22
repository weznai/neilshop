<script setup>
/* 后台外壳：侧栏（admin.css anav）+ 顶栏 + 守卫（toast 走全局 composable） */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'
import RouteProgress from '../components/RouteProgress.vue'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const guard = ref(true)
const guardErr = ref('')
const collapsed = ref(localStorage.getItem('gm_side_min') === '1')

/* 当前登录人角色 badge（UserRole：9=超管 3=仓库 2=运营；1=客服被守卫拒绝，不进后台） */
const ROLE_BADGE = { 9: '超管', 3: '仓库', 2: '运营' }
const roleBadge = computed(() => ROLE_BADGE[session.role] || '管理')

/* 导航高亮：详情页别名 + 前缀匹配（/order-detail → 订单管理，/product-edit → 商品管理） */
const ALIAS = { '/order-detail': '/orders', '/product-edit': '/products' }
function navOn(p) {
  const cur = ALIAS[route.path] || route.path
  if (p === '/') return cur === '/'
  return cur === p || cur.startsWith(p + '/')
}

/* 面包屑中间项（列表页名）→ 路径映射，末项为当前页直接加粗展示 */
const CRUMB_LINKS = { '订单管理': '/orders', '商品管理': '/products' }

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
  logs: '<path d="M3 3v5h5"/><path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"/><polyline points="12 7 12 12 15 15"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  panel: '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/>',
}
/* 侧栏结构：字符串 = 分组小节标题（交易/商品/运营），数组 = [图标, 名称, 路径]；
 * 营销工具/内容管理归「运营」组，与会员/日志/设置并列 */
const ITEMS = [
  ['dash', '数据看板', '/'],
  '交易',
  ['orders', '订单管理', '/orders'],
  ['returns', '退货审核', '/returns'],
  ['tickets', '客服工单', '/tickets'],
  '商品',
  ['products', '商品管理', '/products'],
  ['inventory', '库存中心', '/inventory'],
  '运营',
  ['promo', '营销工具', '/marketing'],
  ['content', '内容管理', '/content'],
  ['members', '会员管理', '/members'],
  ['logs', '审计日志', '/logs'],
  ['settings', '系统设置', '/settings'],
]

function toggleSide() {
  collapsed.value = !collapsed.value
  localStorage.setItem('gm_side_min', collapsed.value ? '1' : '0')
}

/* 宽表右缘渐隐提示条件化：.can-scroll（横向可滚）/.at-end（已滚到右缘）由这里切换，
 * admin.css 据此套/撤 mask。MutationObserver 兼顾路由切换后新增的表格（childList 不含输入类改动，开销可控） */
function watchTblWrap() {
  const sync = (el) => {
    el.classList.toggle('can-scroll', el.scrollWidth > el.clientWidth + 1)
    el.classList.toggle('at-end', el.scrollLeft + el.clientWidth >= el.scrollWidth - 1)
  }
  const ro = new ResizeObserver((entries) => { for (const en of entries) sync(en.target) })
  const attach = (el) => {
    if (!el.dataset.tblWatched) {
      el.dataset.tblWatched = '1'
      el.addEventListener('scroll', () => sync(el), { passive: true })
      ro.observe(el)
    }
    sync(el)
  }
  const scan = () => document.querySelectorAll('.tbl-wrap').forEach(attach)
  /* 挂 body 而非 .main：守卫通过前 .main 尚未渲染，路由切换/表格新增都能捕获 */
  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true })
  scan()
}
async function logout() {
  await session.logout()
  router.push('/login')
}

/* ===== 全局键盘兜底（DOM 方案，不侵入各页面/弹窗组件）=====
 * Esc：关闭最上层 .modal.open（模拟点其 .modal-x；无 modal-x 则忽略）。
 *   ConfirmDialog 无 modal-x 且自带 Esc 处理，重复触发幂等无害。
 * /：非输入焦点（input/textarea/select/可编辑区）且无修饰键时，聚焦 .main 内第一个可见搜索框。 */
const SEARCH_SELS = ['[type=search]', 'input.js-search', '.filter-bar input[type=text]', '.main input[placeholder*=搜索]', '.main input[placeholder*=单号]']
function focusSearch() {
  for (const sel of SEARCH_SELS) {
    for (const el of document.querySelectorAll(sel)) {
      if (el.offsetParent !== null) { el.focus(); return }
    }
  }
}
function onGlobalKey(e) {
  if (e.key === 'Escape') {
    const opens = document.querySelectorAll('.modal.open')
    const top = opens[opens.length - 1]
    if (top) top.querySelector('.modal-x')?.click()
  } else if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey) {
    const ae = document.activeElement
    if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.tagName === 'SELECT' || ae.isContentEditable)) return
    e.preventDefault()
    focusSearch()
  }
}

onMounted(async () => {
  try {
    const u = await session.verify()
    if ((u.role | 0) < 2) throw new Error('该账号无后台权限（role=' + (u.role | 0) + '）')
    guard.value = false
  } catch (e) {
    console.error('[admin] 会话校验失败：', e)
    /* 常见错误映射中文，未识别再回退原始信息 */
    const GUARD_ERR = {
      401: '登录已过期，请重新登录',
      403: '该账号无后台权限',
      404: '会话接口不可用，请确认服务端已启动',
    }
    const mapped = e.status ? GUARD_ERR[e.status] : ''
    guardErr.value = mapped || ((e && e.status ? 'HTTP ' + e.status + ' · ' : '') + (e.message || '会话无效'))
    session._cache(null)
    /* 停 1.5s 让用户看到失败原因，再回登录页 */
    setTimeout(() => router.push('/login'), 1500)
  }
  watchTblWrap()
  window.addEventListener('keydown', onGlobalKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobalKey))
</script>

<template>
  <div v-if="!guard" class="admin" :class="{ 'side-min': collapsed }">
    <RouteProgress />
    <aside class="aside" id="admSide">
      <router-link class="logo" to="/">GLOW<span>MAG</span></router-link>
      <div style="font-size:10px;letter-spacing:2px;color:var(--gray);padding:0 12px 14px">管理控制台</div>
      <nav class="anav">
        <template v-for="(it, i) in ITEMS" :key="i">
          <div v-if="typeof it === 'string'" class="group">{{ it }}</div>
          <router-link v-else :to="it[2]" :class="{ on: navOn(it[2]) }" :title="it[1]">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="flex:none" v-html="P[it[0]]" />
            <span>{{ it[1] }}</span>
          </router-link>
        </template>
        <div class="sep"></div>
        <a href="/" title="在新窗口查看店铺" target="_blank" rel="noopener">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="flex:none" v-html="P.store" />
          <span>查看店铺</span>
        </a>
        <div class="sep"></div>
        <a href="javascript:void(0)" :title="'当前登录：' + session.name" style="cursor:default">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="flex:none" v-html="P.members" />
          <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ session.name }}</span>
          <span class="abadge">{{ roleBadge }}</span>
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
      <!-- 面包屑：仅详情页（meta.crumbs）渲染，是各页 topbar 的补充而非替代 -->
      <div v-if="route.meta.crumbs" class="crumbs">
        <router-link to="/">首页</router-link>
        <template v-for="(c, i) in route.meta.crumbs" :key="i">
          <span class="sep">/</span>
          <router-link v-if="i < route.meta.crumbs.length - 1 && CRUMB_LINKS[c]" :to="CRUMB_LINKS[c]">{{ c }}</router-link>
          <b v-else>{{ c }}</b>
        </template>
      </div>
      <router-view />
    </main>
  </div>
  <div v-else class="admin" style="align-items:center;justify-content:center">
    <div style="text-align:center;color:var(--gray)">
      <template v-if="guardErr">
        <div style="font-size:34px;margin-bottom:8px">⚠️</div>
        <div style="font-size:14px;color:var(--error);margin-bottom:6px">会话校验失败</div>
        <div style="font-size:12.5px">{{ guardErr }}</div>
        <div style="font-size:12px;margin-top:10px">即将返回登录页…</div>
      </template>
      <template v-else>
        <div style="font-size:34px;margin-bottom:8px">⏳</div>正在验证管理会话…
      </template>
    </div>
  </div>
</template>

<style scoped>
.crumbs{font-size:12px;margin-bottom:12px;display:flex;align-items:center;gap:7px}
.crumbs a{color:var(--gray)}
.crumbs a:hover{color:var(--plum)}
.crumbs .sep{color:var(--gray)}
.crumbs b{color:var(--plum);font-weight:700}
</style>
