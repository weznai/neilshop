<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
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
const adjust = ref(null)
const adjChange = ref(0)
const adjReason = ref('')

const MTYPE = { 1: '采购', 2: '预扣', 3: '实扣', 4: '释放', 5: '回补', 6: '盘点', 7: '手工', 8: '损耗' }
const ADJ_ERR = { variant_not_found: '变体不存在', zero_change: '调整量不能为 0', stock_adjust_conflict: '库存并发冲突，请刷新重试' }

const adjAfter = computed(() => (adjust.value ? adjust.value.stock + (adjChange.value || 0) : null))

async function loadVariants() {
  try {
    const d = await req('GET', '/api/admin/catalog/variants?' + new URLSearchParams({ page: page.value, size: 50, q: q.value.trim() }))
    variants.value = d.items || []
    pages.value = Math.max(1, Math.ceil((d.total ?? 0) / 50))
  } catch (e) { toast('SKU 列表加载失败：' + (e.message || ''), 'error') }
}
async function loadLow() {
  try { low.value = (await req('GET', '/api/admin/trade/stock/low?threshold=' + threshold.value)).items || [] }
  catch (e) { toast('低库存预警加载失败：' + (e.message || ''), 'error') }
}
async function loadMovements() {
  try {
    const p = new URLSearchParams({ page: mPage.value })
    if (mVar.value) p.set('variant_id', mVar.value.id)
    const d = await req('GET', '/api/admin/trade/stock/movements?' + p)
    movements.value = d.items || []
    mPages.value = Math.max(1, d.pages || 1)
  } catch (e) { toast('变动流水加载失败：' + (e.message || ''), 'error') }
}
async function load() {
  /* 刷新保留旧数据，骨架只在首载出现 */
  await Promise.all([loadVariants(), loadLow(), loadMovements()])
  loaded.value = true
}
onMounted(load)

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

function search() { page.value = 1; loadVariants() }

/* 当前页前端排序（现货库存）：三态切换，空值恒沉底 */
const sort = reactive({ key: '', dir: 1 })
function sortBy(k) {
  if (sort.key !== k) { sort.key = k; sort.dir = 1 }
  else if (sort.dir === 1) { sort.dir = -1 }
  else { sort.key = ''; sort.dir = 1 }
}
const sortInd = (k) => (sort.key === k ? (sort.dir === 1 ? '▲' : '▼') : '')
const sortedVariants = computed(() => {
  if (!sort.key) return variants.value
  const k = sort.key
  return [...variants.value].sort((a, b) => {
    const av = a[k], bv = b[k]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (av === bv) return 0
    return (av > bv ? 1 : -1) * sort.dir
  })
})
function applyThreshold() {
  threshold.value = Math.max(0, Math.min(9999, parseInt(threshold.value, 10) || 0))
  loadLow()
}
function filterVar(v) { mVar.value = v; mPage.value = 1; loadMovements() }
function clearVar() { mVar.value = null; mPage.value = 1; loadMovements() }

async function doAdjust() {
  if (!adjust.value || !adjChange.value) { toast('请填写增减数量（±）', 'error'); return }
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
      <h1 style="font-size:22px">库存中心</h1>
      <span style="font-size:12.5px;color:var(--gray)">SKU 概览 · 低库存 {{ low.length }}（阈值 ≤{{ threshold }}）· 变动流水</span>
    </div>
    <div style="display:flex;gap:10px">
      <input v-model="q" class="input" style="width:220px" placeholder="搜 SKU / 标题" @keydown.enter="search">
      <button class="btn btn-secondary" @click="search">搜索</button>
    </div>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px;margin-bottom:16px" />

  <template v-else>
    <div class="card tbl-wrap" style="margin-bottom:16px">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="padding:10px">SKU</th><th>商品</th><th>规格</th><th>价格</th>
        <th class="sortable" title="点击排序（当前页）" @click="sortBy('stock')">现货<span v-if="sortInd('stock')" class="sort-ind">{{ sortInd('stock') }}</span></th>
        <th>安全库存</th><th>水位</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="v in sortedVariants" :key="v.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:10px"><b>{{ v.sku }}</b></td>
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
    <EmptyState v-if="!variants.length" icon="📦" title="无匹配 SKU" sub="试试其他关键词" />
    <Pagination embed :page="page" :pages="pages" @go="page = $event; loadVariants()" />
    <div v-if="sort.key" style="text-align:center;font-size:11.5px;color:var(--gray)">⇅ 本页内排序（仅当前页数据）</div>
  </div>

  <div class="grid-2" style="align-items:start">
    <div class="card" style="padding:18px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;gap:8px">
        <h3 style="font-size:14.5px">⚠️ 低库存预警（≤{{ threshold }}）</h3>
        <div style="display:flex;gap:6px">
          <input v-model.number="threshold" class="input" type="number" min="0" style="width:64px;padding:5px 8px" @keydown.enter="applyThreshold">
          <button class="btn btn-secondary btn-sm" @click="applyThreshold">应用</button>
        </div>
      </div>
      <div v-for="l in low" :key="l.variant_id" title="点击查看该 SKU 变动流水"
           style="display:flex;justify-content:space-between;font-size:13px;padding:7px 0;border-bottom:1px solid var(--gray-light);cursor:pointer"
           @click="filterVar({ id: l.variant_id, sku: l.sku })">
        <span>{{ l.sku }} <small style="color:var(--gray)">{{ l.product_title }}</small></span>
        <b style="color:var(--error)">{{ l.stock }}<small style="color:var(--gray)"> / 安全线 {{ l.safety_stock }}</small></b>
      </div>
      <div v-if="!low.length" style="font-size:13px;color:var(--gray);padding:10px 0">全部水位健康 ✓</div>
    </div>
    <div class="card" style="padding:18px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <h3 style="font-size:14.5px">📜 变动流水</h3>
        <button v-if="mVar" class="btn btn-secondary btn-sm" @click="clearVar">SKU {{ mVar.sku }} ✕</button>
      </div>
      <div v-for="m in movements" :key="m.id" style="display:flex;justify-content:space-between;font-size:13px;padding:7px 0;border-bottom:1px solid var(--gray-light)">
        <span style="color:var(--gray)" :title="m.operator || ''">{{ (m.created_at || '').slice(5, 16).replace('T', ' ') }} · {{ MTYPE[m.type] || m.type }}<span v-if="m.ref_id" title="关联单号（内部ID）"> #{{ m.ref_id }}</span></span>
        <b :style="{ color: m.change >= 0 ? 'var(--success)' : 'var(--error)' }">{{ m.change >= 0 ? '+' : '' }}{{ m.change }} → {{ m.stock_after }}</b>
      </div>
      <EmptyState v-if="!movements.length" icon="📜" :title="mVar ? '该 SKU 暂无流水' : '暂无流水'" />
      <Pagination embed :page="mPage" :pages="mPages" @go="mPage = $event; loadMovements()" />
    </div>
  </div>
  </template>

  <!-- 调整弹窗 -->
  <div v-if="adjust" class="modal open" @click.self="adjust = null">
    <div class="modal-box" style="max-width:400px">
      <button class="modal-x" @click="adjust = null">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">调整库存</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:12px">
        {{ adjust.sku }} · 当前 <b>{{ adjust.stock }}</b>（安全库存 {{ adjust.safety_stock }}）
      </p>
      <div class="field"><label>增减数量（±）</label><input v-model.number="adjChange" class="input" type="number" placeholder="如 20 或 -5"></div>
      <div class="field"><label>原因</label><input v-model="adjReason" class="input" placeholder="ops-manual"></div>
      <p v-if="adjChange" style="font-size:13px;margin-top:10px">
        调整后库存：<b :style="{ color: adjAfter < 0 ? 'var(--error)' : 'var(--plum)' }">{{ adjust.stock }} {{ adjChange > 0 ? '+' : '' }}{{ adjChange }} = {{ adjAfter }}</b>
        <span v-if="adjAfter < 0" style="color:var(--error)">（不能为负）</span>
      </p>
      <button class="btn btn-primary btn-block" style="margin-top:12px" @click="doAdjust">确认调整</button>
    </div>
  </div>
</template>
