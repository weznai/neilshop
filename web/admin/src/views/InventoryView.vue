<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { dt } from '../composables/format'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const variants = ref([])
const low = ref([])
const movements = ref([])
const loaded = ref(false)
const q = ref('')
const page = ref(1)
const pages = ref(1)
const threshold = ref(8)
const mPage = ref(1)
const mPages = ref(1)
const mVar = ref(null)
const mType = ref(null)
/* 流水日期范围：date input 原生值即 YYYY-MM-DD，直传后端 date_from/date_to */
const mFrom = ref('')
const mTo = ref('')
const adjust = ref(null)
const adjChange = ref(0)
const adjReason = ref('')
/* 各区错误信息（空串=正常）：兼作错误标志与空态 sub */
const varErr = ref('')
const lowErr = ref('')
const movErr = ref('')

const MTYPE = { 1: '采购', 2: '预扣', 3: '实扣', 4: '释放', 5: '回补', 6: '盘点', 7: '手工', 8: '损耗' }
/* 类型 chips 数据源：[值, 文案]，首项「全部」= null（数字值与 MTYPE 常量一致） */
const MTYPES = [[null, '全部'], ...Object.entries(MTYPE).map(([k, v]) => [Number(k), v])]
const ADJ_ERR = { variant_not_found: '变体不存在', zero_change: '调整量不能为 0', stock_adjust_conflict: '库存并发冲突，请刷新重试' }

const adjAfter = computed(() => (adjust.value ? adjust.value.stock + (adjChange.value || 0) : null))

async function loadVariants() {
  varErr.value = ''
  try {
    const params = { page: page.value, size: 50, q: q.value.trim() }
    if (sort.value) params.sort = sort.value
    const d = await req('GET', '/api/admin/catalog/variants?' + new URLSearchParams(params))
    variants.value = d.items || []
    pages.value = Math.max(1, Math.ceil((d.total ?? 0) / 50))
  } catch (e) { varErr.value = e.message || '请求失败'; toast('SKU 列表加载失败：' + (e.message || ''), 'error') }
}
async function loadLow() {
  lowErr.value = ''
  try { low.value = (await req('GET', '/api/admin/trade/stock/low?threshold=' + threshold.value)).items || [] }
  catch (e) { lowErr.value = e.message || '请求失败'; toast('低库存预警加载失败：' + (e.message || ''), 'error') }
}
async function loadMovements() {
  movErr.value = ''
  try {
    const p = new URLSearchParams({ page: mPage.value })
    if (mVar.value) p.set('variant_id', mVar.value.id)
    if (mType.value !== null) p.set('type', mType.value)
    if (mFrom.value) p.set('date_from', mFrom.value)
    if (mTo.value) p.set('date_to', mTo.value)
    const d = await req('GET', '/api/admin/trade/stock/movements?' + p)
    movements.value = d.items || []
    mPages.value = Math.max(1, d.pages || 1)
  } catch (e) { movErr.value = e.message || '请求失败'; toast('变动流水加载失败：' + (e.message || ''), 'error') }
}
async function load() {
  /* 刷新保留旧数据，骨架只在首载出现 */
  await Promise.all([loadVariants(), loadLow(), loadMovements()])
  loaded.value = true
}
onMounted(load)

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

function search() { page.value = 1; loadVariants() }
function clearSearch() { q.value = ''; page.value = 1; loadVariants() }

/* 服务端排序：sort 直传后端（sku/stock，- 前缀降序），三态循环（无 → 升 → 降 → 无），切换重置页码 */
const sort = ref('')
function sortBy(k) {
  sort.value = sort.value === k ? '-' + k : (sort.value === '-' + k ? '' : k)
  page.value = 1
  loadVariants()
}
const sortInd = (k) => (sort.value === k ? '▲' : sort.value === '-' + k ? '▼' : '')
function applyThreshold() {
  threshold.value = Math.max(0, Math.min(9999, parseInt(threshold.value, 10) || 0))
  loadLow()
}
function filterVar(v) { mVar.value = v; mPage.value = 1; loadMovements() }
function clearVar() { mVar.value = null; mPage.value = 1; loadMovements() }
function filterType(t) { mType.value = t; mPage.value = 1; loadMovements() }
function clearMDates() { mFrom.value = ''; mTo.value = ''; mPage.value = 1; loadMovements() }
/* 流水空态文案：SKU/类型/日期任一筛选生效→未匹配，否则暂无 */
const movFiltered = computed(() => !!(mVar.value || mType.value !== null || mFrom.value || mTo.value))

/* CSV 导出：按当前 SKU + 类型筛选循环翻页拉全量（后端每页 20，上限 20 页）
 * 流水仅含 variant_id：已选 SKU 直接用其 sku，否则拉变体列表建 id→sku 映射 */
const exporting = ref(false)
const EXPORT_MAX_PAGES = 20
async function exportCsv() {
  if (exporting.value) return
  exporting.value = true
  try {
    const qs = () => {
      const p = { page: 1 }
      if (mVar.value) p.variant_id = mVar.value.id
      if (mType.value !== null) p.type = mType.value
      if (mFrom.value) p.date_from = mFrom.value
      if (mTo.value) p.date_to = mTo.value
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
    /* CSV 转义：含逗号/引号/换行的字段包引号并双写引号（同 OrdersView） */
    const cell = (v) => {
      const s = String(v ?? '')
      return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
    }
    const rows = [['时间', 'SKU', '类型', '变更数', '结果库存', '关联', '操作人'],
      ...all.map((m) => [dt(m.created_at), mVar.value ? mVar.value.sku : (skuMap[m.variant_id] || '#' + m.variant_id),
        MTYPE[m.type] || m.type, m.change, m.stock_after, m.ref_type ? `${m.ref_type}#${m.ref_id ?? ''}` : '', m.operator || ''])]
    const csv = rows.map((r) => r.map(cell).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `movements-${mType.value !== null ? MTYPE[mType.value] : '全部'}-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast('已导出 ' + all.length + ' 条 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  exporting.value = false
}

/* 遮罩仅在未填写时可关（防误触丢输入）；右上 × 恒可关 */
function closeAdjust() { if (adjChange.value || adjReason.value.trim()) return; adjust.value = null }

async function doAdjust() {
  if (!adjust.value || !adjChange.value) { toast('请填写增减数量（±）', 'error'); return }
  if (!Number.isInteger(adjChange.value)) { toast('调整数量需为整数', 'error'); return }
  if (adjAfter.value < 0) { toast('调整后库存不能为负', 'error'); return }
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
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">库存中心</h1>
      <span class="page-sub">SKU 概览 · 低库存 {{ low.length }}（阈值 ≤{{ threshold }}）· 变动流水</span>
    </div>
    <div style="display:flex;gap:10px">
      <div style="position:relative">
        <input v-model="q" class="input" style="width:220px;padding-right:30px" placeholder="搜 SKU / 标题" @keydown.enter="search">
        <button v-if="q" type="button" class="q-clear" aria-label="清空搜索" @click="clearSearch">×</button>
      </div>
      <button class="btn btn-secondary" @click="search">搜索</button>
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
        <th class="sortable" title="点击排序" @click="sortBy('sku')">SKU<span v-if="sortInd('sku')" class="sort-ind">{{ sortInd('sku') }}</span></th><th>商品</th><th>规格</th><th>价格</th>
        <th class="sortable" title="点击排序" @click="sortBy('stock')">现货<span v-if="sortInd('stock')" class="sort-ind">{{ sortInd('stock') }}</span></th>
        <th>安全库存</th><th>水位</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="v in variants" :key="v.id" style="border-top:1px solid var(--gray-light)">
          <td><b>{{ v.sku }}</b></td>
          <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis">{{ v.product_title }}</td>
          <td>{{ v.option1_value }}</td>
          <td>{{ money(v.price) }}</td>
          <td><b :style="{ color: v.stock ? '' : 'var(--error)' }">{{ v.stock }}</b>
            <span v-if="!v.is_active" class="tag tag-pending" style="margin-left:4px;font-size:10px">停用</span></td>
          <td style="color:var(--gray)">{{ v.safety_stock }}</td>
          <td>
            <div class="stock-track" style="width:70px" :title="`库存 ${v.stock} / 安全线 ${v.safety_stock ?? 0}`">
              <div class="stock-fill" :class="v.stock < 10 ? 'low' : v.stock < 30 ? 'mid' : 'ok'" :style="{ width: Math.min(100, v.stock * 3) + '%' }"></div>
            </div>
          </td>
          <td style="text-align:right;white-space:nowrap">
            <button class="btn btn-ghost btn-sm" title="查看该 SKU 变动流水" @click="filterVar(v)">流水</button>
            <button class="btn btn-secondary btn-sm" style="margin-left:6px" @click="adjust = v; adjChange = 0; adjReason = ''">调整</button>
          </td>
        </tr>
      </tbody>
      </table>
      <EmptyState v-if="!variants.length" :icon="q.trim() ? '🔍' : '📦'" :title="q.trim() ? '未找到匹配的 SKU' : '暂无 SKU'" :sub="q.trim() ? '试试调整或清除筛选' : '商品变体将显示在这里'" />
      <Pagination embed :page="page" :pages="pages" @go="page = $event; loadVariants()" />
    </template>
  </div>

  <div class="grid-2" style="align-items:start">
    <div class="card" style="padding:18px">
      <div class="dhead">
        <h3 class="dtitle">⚠️ 低库存预警（≤{{ threshold }}）</h3>
        <div style="display:flex;gap:6px">
          <input v-model.number="threshold" class="input" type="number" min="0" style="width:64px;padding:5px 8px" @keydown.enter="applyThreshold">
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
        <div v-for="l in low" :key="l.variant_id" title="点击查看该 SKU 变动流水"
             style="display:flex;justify-content:space-between;font-size:13px;padding:7px 0;border-bottom:1px solid var(--gray-light);cursor:pointer"
             @click="filterVar({ id: l.variant_id, sku: l.sku })">
          <span>{{ l.sku }} <small style="color:var(--gray)">{{ l.product_title }}</small></span>
          <b style="color:var(--error)">{{ l.stock }}<small style="color:var(--gray)"> / 安全线 {{ l.safety_stock }}</small></b>
        </div>
        <div v-if="!low.length" style="font-size:13px;color:var(--gray);padding:10px 0">库存充足，无预警项 ✓</div>
      </template>
    </div>
    <div class="card" style="padding:18px">
      <div class="dhead">
        <h3 class="dtitle">📜 变动流水</h3>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <input v-model="mFrom" class="input" type="date" aria-label="流水起始日期" style="width:140px;padding:5px 8px;font-size:12.5px" @change="mPage = 1; loadMovements()">
          <input v-model="mTo" class="input" type="date" aria-label="流水截止日期" style="width:140px;padding:5px 8px;font-size:12.5px" @change="mPage = 1; loadMovements()">
          <button v-if="mFrom || mTo" class="btn btn-ghost btn-sm" @click="clearMDates">清空</button>
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
        <Pagination embed :page="mPage" :pages="mPages" @go="mPage = $event; loadMovements()" />
      </template>
    </div>
  </div>
  </template>

  <!-- 调整弹窗 -->
  <div v-if="adjust" class="modal open" @click.self="closeAdjust">
    <div class="modal-box" style="max-width:400px">
      <button class="modal-x" @click="adjust = null">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">调整库存</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:12px">
        {{ adjust.sku }} · 当前 <b>{{ adjust.stock }}</b>（安全库存 {{ adjust.safety_stock }}）
      </p>
      <div class="field"><label>增减数量（±）</label><input v-model.number="adjChange" class="input" type="number" step="1" placeholder="如 20 或 -5"></div>
      <div class="field"><label>原因</label><input v-model="adjReason" class="input" placeholder="ops-manual"></div>
      <p v-if="adjChange" style="font-size:13px;margin-top:10px">
        调整后库存：<b :style="{ color: adjAfter < 0 ? 'var(--error)' : 'var(--plum)' }">{{ adjust.stock }} {{ adjChange > 0 ? '+' : '' }}{{ adjChange }} = {{ adjAfter }}</b>
        <span v-if="adjAfter < 0" style="color:var(--error)">（不能为负）</span>
      </p>
      <button class="btn btn-primary btn-block" style="margin-top:12px" @click="doAdjust">确认调整</button>
    </div>
  </div>
</template>

<style scoped>
td,th{padding:10px 12px}
/* 刷新失败横幅：pale-error 底 + error 字，圆角，卡内顶部 */
.err-banner{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 14px;margin:12px 12px 0;background:var(--pale-error);color:var(--error);border-radius:10px;font-size:12.5px}
.mchip{padding:3px 11px;border-radius:999px;border:1px solid var(--gray-light);background:#fff;color:var(--gray);font-size:12px;cursor:pointer}
.mchip:hover{border-color:var(--rose);color:var(--plum)}
.mchip.on{border-color:var(--plum);background:var(--plum);color:#fff}
/* 搜索框清空钮：悬浮输入框右侧 */
.q-clear{position:absolute;right:8px;top:50%;transform:translateY(-50%);width:17px;height:17px;border:none;border-radius:50%;background:var(--gray-light);color:#fff;font-size:11px;line-height:1;cursor:pointer;padding:0}
.q-clear:hover{background:var(--gray)}
</style>
