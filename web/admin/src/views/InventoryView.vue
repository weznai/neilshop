<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'
import { dt, money } from '../composables/format'
import { downloadCsv, fetchAllPages } from '../composables/exportCsv'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const session = useSessionStore()
const variants = ref([])
const low = ref([])
const movements = ref([])
const loaded = ref(false)
const pages = ref(1)
const varTotal = ref(0)        /* SKU 列表总数（Pagination total） */
const movTotal = ref(0)        /* 流水总数（Pagination total） */
const mPages = ref(1)
const adjust = ref(null)
const adjChange = ref(0)
const adjReason = ref('')
const adjBusy = ref(false)
const adjCloseDlg = ref(false)
/* 各区错误信息（空串=正常）：兼作错误标志与空态 sub */
const varErr = ref('')
const lowErr = ref('')
const movErr = ref('')

const MTYPE = { 1: '采购', 2: '预扣', 3: '实扣', 4: '释放', 5: '回补', 6: '盘点', 7: '手工', 8: '损耗' }
/* 类型 chips 数据源：[值, 文案]，首项「全部」= null（数字值与 MTYPE 常量一致） */
const MTYPES = [[null, '全部'], ...Object.entries(MTYPE).map(([k, v]) => [Number(k), v])]
const ADJ_ERR = { variant_not_found: '变体不存在', zero_change: '调整量不能为 0', stock_adjust_conflict: '库存并发冲突，请刷新重试' }

/* ===== URL 同步：page/sort/threshold（SKU 列表）+ mv（流水选中 SKU id）/mt（类型）/mfrom/mto（日期）/mp（流水页）
 * q 拆出同步态为本地 ref：输入不逐字符 router.replace，仅搜索触发/回车时才写回 URL（做法同 OrdersView） ===== */
const SORTABLE = ['sku', '-sku', 'stock', '-stock']
const state = reactive({ page: 1, mv: '', mt: 'all', mfrom: '', mto: '', mp: 1, sort: '', threshold: 8 })
useQuerySync(state, { nums: ['page', 'mv', 'mp'], defaults: { page: 1, mv: '', mt: 'all', mfrom: '', mto: '', mp: 1, sort: '', threshold: 8 }, onPop: () => load() })
/* 回填清洗：非法值回落默认 */
if (!['all', ...Object.keys(MTYPE)].includes(state.mt)) state.mt = 'all'
if (!SORTABLE.includes(state.sort)) state.sort = ''
if (!(state.page >= 1)) state.page = 1
if (!(state.mp >= 1)) state.mp = 1
if (!(state.mv >= 1)) state.mv = ''
const route = useRoute()
const router = useRouter()
/* 搜索词独立 ref：初始化读 query.q，搜索/清空时才 replace 写回（useQuerySync 不追踪 q，无回环） */
const q = ref(typeof route.query.q === 'string' ? route.query.q : '')
function syncQ() {
  const kw = q.value.trim()
  if ((route.query.q || '') !== kw) router.replace({ query: { ...route.query, q: kw || undefined } })
}
/* 浏览器回退/前进：q 变化只同步回本地 ref 并重载 SKU 列表（不触发导航）；页码键由 useQuerySync 的
 * query-watcher 先行回落默认并经 onPop 重载（其 watch 创建早于本处，同批 flush 先执行） */
watch(() => route.query.q, (v) => {
  if (route.name !== 'inventory') return   /* 已离开本页（卸载前最后一次 route 变更）：忽略 */
  const s = typeof v === 'string' ? v : ''
  if (s !== q.value) {
    q.value = s
    loadVariants()
  }
})
const thrNum = Number(state.threshold)
state.threshold = Number.isInteger(thrNum) && thrNum >= 0 && thrNum <= 9999 ? thrNum : 8
/* 流水选中 SKU：URL 存 id，展示 sku 从已加载变体列表解析；未命中时用点击时带来的 skuHint（URL 直开暂以 #id 占位，列表载入后自动替换） */
const skuHint = ref(null)
const mVar = computed(() => {
  if (!state.mv) return null
  const hit = variants.value.find((x) => x.id === state.mv)
  return { id: state.mv, sku: hit ? hit.sku : (skuHint.value || '#' + state.mv) }
})
const mType = computed(() => (state.mt === 'all' ? null : Number(state.mt)))

const adjAfter = computed(() => (adjust.value ? adjust.value.stock + (adjChange.value || 0) : null))

/* 请求序号 token：三区各自防竞态（快速切换筛选丢弃过期响应） */
let varSeq = 0
let lowSeq = 0
let movSeq = 0
async function loadVariants() {
  const t = ++varSeq
  varErr.value = ''
  try {
    const params = { page: state.page, size: 50, q: q.value.trim() }
    if (state.sort) params.sort = state.sort
    const d = await req('GET', '/api/admin/catalog/variants?' + new URLSearchParams(params))
    if (t !== varSeq) return
    variants.value = d.items || []
    varTotal.value = d.total ?? 0
    pages.value = Math.max(1, Math.ceil(varTotal.value / 50))
    /* 当前页删空回落：本页 SKU 被删光且不在第 1 页时回第 1 页重拉一次（已在第 1 页则空态渲染，无递归） */
    if (!variants.value.length && state.page > 1) { state.page = 1; loadVariants(); return }
  } catch (e) { if (t !== varSeq) return; varErr.value = e.message || '请求失败'; toast('SKU 列表加载失败：' + (e.message || ''), 'error') }
}
async function loadLow() {
  const t = ++lowSeq
  lowErr.value = ''
  try {
    const d = await req('GET', '/api/admin/trade/stock/low?threshold=' + state.threshold)
    if (t !== lowSeq) return
    low.value = d.items || []
  }
  catch (e) { if (t !== lowSeq) return; lowErr.value = e.message || '请求失败'; toast('低库存预警加载失败：' + (e.message || ''), 'error') }
}
async function loadMovements() {
  /* 日期校验：截止早于起始时不发请求（对齐 OrdersView） */
  if (state.mfrom && state.mto && state.mto < state.mfrom) {
    toast('结束日期不能早于开始日期', 'error')
    return
  }
  const t = ++movSeq
  movErr.value = ''
  try {
    const p = new URLSearchParams({ page: state.mp })
    if (mVar.value) p.set('variant_id', mVar.value.id)
    if (mType.value !== null) p.set('type', mType.value)
    if (state.mfrom) p.set('date_from', state.mfrom)
    if (state.mto) p.set('date_to', state.mto)
    const d = await req('GET', '/api/admin/trade/stock/movements?' + p)
    if (t !== movSeq) return
    movements.value = d.items || []
    movTotal.value = d.total ?? 0
    mPages.value = Math.max(1, d.pages || 1)
  } catch (e) { if (t !== movSeq) return; movErr.value = e.message || '请求失败'; toast('变动流水加载失败：' + (e.message || ''), 'error') }
}
async function load() {
  /* 刷新保留旧数据，骨架只在首载出现 */
  await Promise.all([loadVariants(), loadLow(), loadMovements()])
  loaded.value = true
}
onMounted(load)

/* 水位条：按 stock / max(safety_stock,1) 相对着色（≤0.25 红 / ≤0.6 橙 / 其余绿），宽度随比值 */
const stockRatio = (v) => (v.stock || 0) / Math.max(v.safety_stock ?? 0, 1)
const stockCls = (v) => { const r = stockRatio(v); return r <= 0.25 ? 'low' : r <= 0.6 ? 'mid' : 'ok' }
/* 规格列：option2 存在且非 Default 时拼接（如 "Short Almond / XL"） */
const specLabel = (v) => (v.option2_value && v.option2_value !== 'Default' ? v.option1_value + ' / ' + v.option2_value : v.option1_value)

function search() { state.page = 1; syncQ(); loadVariants() }
function clearSearch() { q.value = ''; state.page = 1; syncQ(); loadVariants() }

/* 服务端排序：sort 直传后端（sku/stock，- 前缀降序），三态循环（无 → 升 → 降 → 无），切换重置页码（URL 同步） */
function sortBy(k) {
  state.sort = state.sort === k ? '-' + k : (state.sort === '-' + k ? '' : k)
  state.page = 1
  loadVariants()
}
const sortInd = (k) => (state.sort === k ? '▲' : state.sort === '-' + k ? '▼' : '')
const ariaSort = (k) => (state.sort === k ? 'ascending' : state.sort === '-' + k ? 'descending' : 'none')
function applyThreshold() {
  /* 输入清空 → 0（列出所有 SKU），应用前明确提示语义 */
  if (state.threshold === '' || state.threshold === null || state.threshold === undefined) {
    toast('0 表示列出所有 SKU')
    state.threshold = 0
    loadLow()
    return
  }
  state.threshold = Math.max(0, Math.min(9999, parseInt(state.threshold, 10) || 0))
  loadLow()
}
function filterVar(v) { skuHint.value = v.sku || null; state.mv = v.id; state.mp = 1; loadMovements() }
function clearVar() { state.mv = ''; skuHint.value = null; state.mp = 1; loadMovements() }
function filterType(t) { state.mt = t === null ? 'all' : String(t); state.mp = 1; loadMovements() }
function clearMDates() { state.mfrom = ''; state.mto = ''; state.mp = 1; loadMovements() }
/* 流水空态文案：SKU/类型/日期任一筛选生效→未匹配，否则暂无 */
const movFiltered = computed(() => !!(state.mv || mType.value !== null || state.mfrom || state.mto))

/* CSV 导出：按当前 SKU + 类型筛选循环翻页拉全量（导出请求带 per_page=100 提速，后端 10-100 钳制；
 * 页数以响应回显 pages 为准，与实际每页条数联动）
 * 流水仅含 variant_id：已选 SKU 直接用其 sku，否则拉变体列表建 id→sku 映射 */
const exporting = ref(false)
const EXPORT_MAX_PAGES = 50
async function exportCsv() {
  if (exporting.value) return
  exporting.value = true
  try {
    const qs = () => {
      const p = { page: 1, per_page: 100 }
      if (mVar.value) p.variant_id = mVar.value.id
      if (mType.value !== null) p.type = mType.value
      if (state.mfrom) p.date_from = state.mfrom
      if (state.mto) p.date_to = state.mto
      return p
    }
    const all = []
    let pg = 1
    let totalPages = 1
    while (pg <= totalPages && pg <= EXPORT_MAX_PAGES) {
      const params = qs(); params.page = pg
      const d = await req('GET', '/api/admin/trade/stock/movements?' + new URLSearchParams(params))
      all.push(...(d.items || []))
      totalPages = d.pages || 1
      if (!(d.items || []).length) break
      pg++
    }
    if (totalPages > EXPORT_MAX_PAGES) toast(`流水超过 ${EXPORT_MAX_PAGES} 页，仅导出前 ${all.length} 条`, 'error')
    const skuMap = {}
    if (!mVar.value) {
      let vp = 1
      while (vp <= EXPORT_MAX_PAGES) {
        const d = await req('GET', `/api/admin/catalog/variants?page=${vp}&size=200`)
        ;(d.items || []).forEach((v) => { skuMap[v.id] = v.sku })
        if (!(d.items || []).length || vp * 200 >= (d.total ?? 0)) break
        vp++
      }
    }
    downloadCsv({
      filename: `movements-${mType.value !== null ? MTYPE[mType.value] : '全部'}-${new Date().toISOString().slice(0, 10)}`,
      headers: ['时间', 'SKU', '类型', '变更数', '结果库存', '关联', '操作人'],
      rows: all.map((m) => [dt(m.created_at), mVar.value ? mVar.value.sku : (skuMap[m.variant_id] || '#' + m.variant_id),
        MTYPE[m.type] || m.type, m.change, m.stock_after, m.ref_type ? `${m.ref_type}#${m.ref_id ?? ''}` : '', m.operator || '']),
    })
    toast('已导出 ' + all.length + ' 条 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  exporting.value = false
}

/* SKU 列表导出：当前搜索/排序筛选全量翻页（size=200 上限 50 页，与流水导出同按钮风格） */
const varExporting = ref(false)
async function exportVariants() {
  if (varExporting.value) return
  varExporting.value = true
  try {
    const kw = q.value.trim()
    const { all, truncated } = await fetchAllPages((p) => req('GET', '/api/admin/catalog/variants?' + new URLSearchParams({
      page: p, size: 200,
      ...(kw ? { q: kw } : {}),
      ...(state.sort ? { sort: state.sort } : {}),
    })), { pageSize: 200, maxPages: 50 })
    if (truncated) toast('匹配结果过多，仅导出前 ' + all.length + ' 条', 'error')
    downloadCsv({
      filename: 'variants-' + new Date().toISOString().slice(0, 10),
      headers: ['SKU', '商品', '价格', '库存', '安全库存', '状态'],
      rows: all.map((v) => [v.sku, v.product_title || '', money(v.price), v.stock ?? 0, v.safety_stock ?? 0, v.is_active ? '启用' : '停用']),
    })
    toast('已导出 ' + all.length + ' 条 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  varExporting.value = false
}

/* 调整弹窗：打开统一入口（表格行/低库存行共用） */
function openAdjust(v) { adjust.value = v; adjChange.value = 0; adjReason.value = '' }
/* 遮罩仅在未填写时可关（防误触丢输入）；✕ 已填写时先确认再关 */
function closeAdjust() { if (adjChange.value || adjReason.value.trim()) return; adjust.value = null }
function xAdjust() {
  if (adjBusy.value) return
  if (adjChange.value || adjReason.value.trim()) adjCloseDlg.value = true
  else closeAdjust()
}
function confirmCloseAdjust() { adjCloseDlg.value = false; adjust.value = null; adjChange.value = 0; adjReason.value = '' }

async function doAdjust() {
  if (!adjust.value || adjBusy.value) return
  if (!adjChange.value) { toast('请填写增减数量（±）', 'error'); return }
  if (!Number.isInteger(adjChange.value)) { toast('调整数量需为整数', 'error'); return }
  if (adjAfter.value < 0) { toast('调整后库存不能为负', 'error'); return }
  adjBusy.value = true
  try {
    await req('POST', '/api/admin/trade/stock/adjust', {
      variant_id: adjust.value.id, change: adjChange.value, reason: adjReason.value.trim() || 'ops-manual',
    })
    toast(`已调整 ${adjust.value.sku} ${adjChange.value > 0 ? '+' : ''}${adjChange.value} ✓`, 'success')
    adjust.value = null
    adjChange.value = 0
    adjReason.value = ''
    load()
  } catch (e) { toast('调整失败：' + (ADJ_ERR[e.data?.detail] || e.data?.detail || e.message), 'error') }
  finally { adjBusy.value = false }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">库存中心</h1>
      <span class="page-sub">SKU 概览 · 低库存 {{ low.length }}（阈值 ≤{{ state.threshold }}）· 变动流水</span>
    </div>
    <div style="display:flex;gap:10px">
      <div style="position:relative">
        <input v-model="q" class="input js-search" style="width:220px;padding-right:30px" placeholder="搜 SKU / 标题" @keydown.enter="search">
        <button v-if="q" type="button" class="q-clear" aria-label="清空搜索" @click="clearSearch">×</button>
      </div>
      <button class="btn btn-secondary" @click="search">搜索</button>
      <button class="btn btn-secondary" :disabled="varExporting" @click="exportVariants">{{ varExporting ? '导出中…' : '⌄ 导出 CSV' }}</button>
    </div>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px;margin-bottom:16px" />

  <template v-else>
    <div class="card tbl-wrap" style="margin-bottom:16px">
    <!-- 首屏失败（无旧数据）：错误空态置顶，隐藏表格 -->
    <EmptyState v-if="varErr && !variants.length" icon="⚠️" title="SKU 列表加载失败" :sub="varErr">
      <template #action><button class="btn btn-secondary btn-sm" @click="loadVariants">重试</button></template>
    </EmptyState>
    <template v-else>
      <!-- 刷新失败（有旧数据）：卡内顶部横幅，旧数据保留 -->
      <div v-if="varErr" class="err-banner">
        <span>⚠️ 刷新失败：{{ varErr }}</span>
        <button class="btn btn-secondary btn-sm" @click="loadVariants">重试</button>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th class="sortable" tabindex="0" role="button" :aria-sort="ariaSort('sku')" title="点击排序（回车/空格亦可）" @click="sortBy('sku')" @keydown.enter.prevent="sortBy('sku')" @keydown.space.prevent="sortBy('sku')">SKU<span v-if="sortInd('sku')" class="sort-ind">{{ sortInd('sku') }}</span></th><th>商品</th><th>规格</th><th>价格</th>
        <th class="sortable" tabindex="0" role="button" :aria-sort="ariaSort('stock')" title="点击排序（回车/空格亦可）" @click="sortBy('stock')" @keydown.enter.prevent="sortBy('stock')" @keydown.space.prevent="sortBy('stock')">现货<span v-if="sortInd('stock')" class="sort-ind">{{ sortInd('stock') }}</span></th>
        <th>安全库存</th><th>水位</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="v in variants" :key="v.id" style="border-top:1px solid var(--gray-light)">
          <td><b>{{ v.sku }}</b></td>
          <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            <router-link :to="{ path: '/product-edit', query: { id: v.product_id } }" style="color:inherit" :title="v.product_title">{{ v.product_title }}</router-link>
          </td>
          <td>{{ specLabel(v) }}</td>
          <td>{{ money(v.price) }}</td>
          <td><b :style="{ color: v.stock ? '' : 'var(--error)' }">{{ v.stock }}</b>
            <span v-if="!v.is_active" class="tag tag-pending" style="margin-left:4px;font-size:10px">停用</span></td>
          <td style="color:var(--gray)">{{ v.safety_stock }}</td>
          <td>
            <!-- 相对着色：stock/max(安全线,1) ≤0.25 红 / ≤0.6 橙 / 其余绿 -->
            <div class="stock-track" style="width:70px" :title="`库存 ${v.stock} / 安全线 ${v.safety_stock ?? 0}`">
              <div class="stock-fill" :class="stockCls(v)" :style="{ width: Math.min(100, Math.round(stockRatio(v) * 100)) + '%' }"></div>
            </div>
          </td>
          <td style="text-align:right;white-space:nowrap">
            <button class="btn btn-ghost btn-sm" title="查看该 SKU 变动流水" @click="filterVar(v)">流水</button>
            <button v-if="session.hasPerm('stock:manage')" class="btn btn-secondary btn-sm" style="margin-left:6px" @click="openAdjust(v)">调整</button>
          </td>
        </tr>
      </tbody>
      </table>
      <EmptyState v-if="!variants.length" :icon="q.trim() ? '🔍' : '📦'" :title="q.trim() ? '未找到匹配的 SKU' : '暂无 SKU'" :sub="q.trim() ? '试试调整或清除筛选' : '商品变体将显示在这里'" />
      <Pagination embed :page="state.page" :pages="pages" :total="varTotal" unit="条" @go="state.page = $event; loadVariants()" />
    </template>
  </div>

  <div class="grid-2" style="align-items:start">
    <div class="card" style="padding:18px">
      <div class="dhead">
        <h3 class="dtitle">⚠️ 低库存预警<span class="item-cnt">{{ low.length }} 项 · 阈值 ≤{{ state.threshold }}</span></h3>
        <div style="display:flex;gap:6px">
          <input v-model.number="state.threshold" class="input" type="number" min="0" style="width:64px;padding:5px 8px" @keydown.enter="applyThreshold">
          <button class="btn btn-secondary btn-sm" @click="applyThreshold">应用</button>
        </div>
      </div>
      <!-- 首屏失败：错误空态置顶；刷新失败：横幅置顶保留旧数据 -->
      <EmptyState v-if="lowErr && !low.length" icon="⚠️" title="低库存预警加载失败" :sub="lowErr">
        <template #action><button class="btn btn-secondary btn-sm" @click="loadLow">重试</button></template>
      </EmptyState>
      <template v-else>
        <div v-if="lowErr" class="err-banner" style="margin:10px 0 0">
          <span>⚠️ 刷新失败：{{ lowErr }}</span>
          <button class="btn btn-secondary btn-sm" @click="loadLow">重试</button>
        </div>
        <!-- 预警列表限高内部滚动 -->
        <div style="max-height:320px;overflow-y:auto">
          <div v-for="l in low" :key="l.variant_id" title="点击查看该 SKU 变动流水"
               style="display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:13px;padding:7px 0;border-bottom:1px solid var(--gray-light);cursor:pointer"
               @click="filterVar({ id: l.variant_id, sku: l.sku })">
            <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ l.sku }} <small style="color:var(--gray)">{{ l.product_title }}</small></span>
            <span style="display:flex;gap:8px;align-items:center;flex:none">
              <b style="color:var(--error)">{{ l.stock }}<small style="color:var(--gray)"> / 安全线 {{ l.safety_stock }}</small></b>
              <button v-if="session.hasPerm('stock:manage')" class="btn btn-secondary btn-sm" title="调整该 SKU 库存" @click.stop="openAdjust({ id: l.variant_id, sku: l.sku, stock: l.stock, safety_stock: l.safety_stock })">调整</button>
            </span>
          </div>
          <div v-if="!low.length" style="font-size:13px;color:var(--gray);padding:10px 0">库存充足，无预警项 ✓</div>
        </div>
      </template>
    </div>
    <div class="card" style="padding:18px">
      <div class="dhead">
        <h3 class="dtitle">📜 变动流水</h3>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <input v-model="state.mfrom" class="input" type="date" aria-label="流水起始日期" style="width:140px;padding:5px 8px;font-size:12.5px" @change="state.mp = 1; loadMovements()">
          <input v-model="state.mto" class="input" type="date" aria-label="流水截止日期" style="width:140px;padding:5px 8px;font-size:12.5px" @change="state.mp = 1; loadMovements()">
          <button v-if="state.mfrom || state.mto" class="btn btn-ghost btn-sm" @click="clearMDates">清空</button>
          <button v-if="mVar" class="btn btn-secondary btn-sm" @click="clearVar">SKU {{ mVar.sku }} ✕</button>
          <button class="btn btn-secondary btn-sm" :disabled="exporting" @click="exportCsv">{{ exporting ? '导出中…' : '⌄ 导出 CSV' }}</button>
        </div>
      </div>
      <div class="filter-bar" style="margin-bottom:10px">
        <button v-for="[tv, tl] in MTYPES" :key="String(tv)" class="mchip" :class="{ on: mType === tv }" @click="filterType(tv)">{{ tl }}</button>
      </div>
      <!-- 首屏失败：错误空态置顶；刷新失败：横幅置顶保留旧数据 -->
      <EmptyState v-if="movErr && !movements.length" icon="⚠️" title="变动流水加载失败" :sub="movErr">
        <template #action><button class="btn btn-secondary btn-sm" @click="loadMovements">重试</button></template>
      </EmptyState>
      <template v-else>
        <div v-if="movErr" class="err-banner" style="margin:10px 0 4px">
          <span>⚠️ 刷新失败：{{ movErr }}</span>
          <button class="btn btn-secondary btn-sm" @click="loadMovements">重试</button>
        </div>
        <div v-for="m in movements" :key="m.id" style="display:flex;justify-content:space-between;font-size:13px;padding:7px 0;border-bottom:1px solid var(--gray-light)">
          <span style="color:var(--gray)" :title="m.operator || ''">{{ dt(m.created_at) }} · {{ MTYPE[m.type] || m.type }}<span v-if="m.ref_id" title="关联单号（内部ID）"> #{{ m.ref_id }}</span></span>
          <b :style="{ color: m.change >= 0 ? 'var(--success)' : 'var(--error)' }">{{ m.change >= 0 ? '+' : '' }}{{ m.change }} → {{ m.stock_after }}</b>
        </div>
        <EmptyState v-if="!movements.length" :icon="movFiltered ? '🔍' : '📜'" :title="movFiltered ? '未找到匹配的流水' : '暂无流水'" :sub="movFiltered ? '试试调整或清除筛选' : '库存变动记录将显示在这里'" />
        <Pagination embed :page="state.mp" :pages="mPages" :total="movTotal" unit="条" @go="state.mp = $event; loadMovements()" />
      </template>
    </div>
  </div>
  </template>

  <!-- 调整弹窗：busy 防双击重复提交；✕ 已填写时先确认再关 -->
  <div v-if="adjust" class="modal open" @click.self="closeAdjust">
    <div class="modal-box" style="max-width:400px">
      <button class="modal-x" :disabled="adjBusy" @click="xAdjust">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">调整库存</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:12px">
        {{ adjust.sku }} · 当前 <b>{{ adjust.stock }}</b>（安全库存 {{ adjust.safety_stock }}）
      </p>
      <div class="field"><label>增减数量（±）</label><input v-model.number="adjChange" class="input" type="number" step="1" :disabled="adjBusy" placeholder="如 20 或 -5"></div>
      <div class="field"><label>原因</label><input v-model="adjReason" class="input" :disabled="adjBusy" placeholder="ops-manual"></div>
      <p v-if="adjChange" style="font-size:13px;margin-top:10px">
        调整后库存：<b :style="{ color: adjAfter < 0 ? 'var(--error)' : 'var(--plum)' }">{{ adjust.stock }} {{ adjChange > 0 ? '+' : '' }}{{ adjChange }} = {{ adjAfter }}</b>
        <span v-if="adjAfter < 0" style="color:var(--error)">（不能为负）</span>
      </p>
      <button v-if="session.hasPerm('stock:manage')" class="btn btn-primary btn-block" style="margin-top:12px" :class="{ loading: adjBusy }" :disabled="adjBusy" @click="doAdjust">{{ adjBusy ? '调整中…' : '确认调整' }}</button>
    </div>
  </div>

  <!-- 放弃调整确认（✕ 且已填写时） -->
  <ConfirmDialog :open="adjCloseDlg" title="放弃本次调整？" body="已填写数量或原因，确认关闭并放弃本次调整？" danger confirm-text="放弃" @confirm="confirmCloseAdjust" @close="adjCloseDlg = false" />
</template>

<style scoped>
/* 刷新失败横幅：pale-error 底 + error 字，圆角，卡内顶部 */
.err-banner{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 14px;margin:12px 12px 0;background:var(--pale-error);color:var(--error);border-radius:10px;font-size:12.5px}
.mchip{padding:3px 11px;border-radius:999px;border:1px solid var(--gray-light);background:#fff;color:var(--gray);font-size:12px;cursor:pointer}
.mchip:hover{border-color:var(--rose);color:var(--plum)}
.mchip.on{border-color:var(--plum);background:var(--plum);color:#fff}
/* 可排序表头键盘可达：焦点环 */
th.sortable:focus-visible{outline:2px solid var(--plum);outline-offset:-2px}
/* .q-clear 已上移 admin.css（v16 公共类，样式完全一致） */
</style>
