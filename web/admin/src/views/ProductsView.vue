<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { dt } from '../composables/format'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const router = useRouter()
const items = ref([])
const total = ref(0)
const pages = ref(1)
const loaded = ref(false)
const loadErr = ref('')
const bulk = ref(false)
const bulkText = ref('')
const bulkResult = ref(null)

const TABS = [[null, '全部'], [1, '在售'], [0, '草稿'], [2, '归档']]
const SMeta = { 0: ['草稿', 'tag-pending'], 1: ['在售', 'tag-paid'], 2: ['归档', 'tag'] }
const BULK_ERR = { 'slug already exists': 'slug 已存在', 'category not found': '分类不存在' }
const failures = computed(() => (bulkResult.value?.results || []).filter((r) => !r.ok))

/* ===== URL 同步：page/q/status（tab 映射，'all'=全部）+ 原有 category_id/sort 一并并入 useQuerySync ===== */
const SORTABLE = ['title', '-title', 'price', '-price', 'created_at', '-created_at']
const state = reactive({ page: 1, q: '', status: 'all', category_id: '', sort: '' })
useQuerySync(state, { nums: ['page', 'category_id'], defaults: { page: 1, q: '', status: 'all', category_id: '', sort: '' } })
/* 回填清洗：非法值回落默认（顺带触发 watch 清掉 URL 脏键） */
if (!SORTABLE.includes(state.sort)) state.sort = ''
if (!['all', '0', '1', '2'].includes(state.status)) state.status = 'all'
if (!(state.page >= 1)) state.page = 1
if (!(state.category_id >= 1)) state.category_id = ''
const status = computed(() => (state.status === 'all' ? null : Number(state.status)))

/* 分类白名单：onMounted 拉分类列表，批量导入的 category_id 校验以此为准（动态） */
const categories = ref([])
const catIdSet = computed(() => new Set(categories.value.map((c) => c.id)))
async function loadCategories() {
  try {
    /* 后端返回裸数组（兼容 {items} 包装），此前误取 .items 导致白名单恒空 */
    const d = await req('GET', '/api/admin/catalog/categories')
    categories.value = Array.isArray(d) ? d : (d.items || [])
  }
  catch (_) { /* 拉取失败时导入校验回退为「任意正整数」，后端仍会兜底 */ }
}

/* 分类筛选：category_id 传后端真过滤（分页生效），选中值与 sort 一并同步 URL（已并入 useQuerySync 的 state） */

/* 请求序号 token：快速切换筛选/翻页时丢弃过期响应（竞态） */
let reqSeq = 0
async function load() {
  /* 刷新保留旧数据，骨架只在首载出现；翻页/切 tab/搜索均经此入口，顺带重置勾选 */
  selIds.value = []
  const token = ++reqSeq
  try {
    const qs = { page: state.page, size: 50, q: state.q.trim() }
    if (status.value !== null) qs.status = status.value
    if (state.category_id !== '') qs.category_id = state.category_id
    if (state.sort) qs.sort = state.sort
    const d = await req('GET', '/api/admin/catalog/products?' + new URLSearchParams(qs))
    if (token !== reqSeq) return
    items.value = d.items || []
    total.value = d.total ?? 0
    pages.value = Math.max(1, Math.ceil(total.value / 50))
  } catch (e) {
    if (token !== reqSeq) return
    /* 首载失败记错误走错误空态（不再误导为「暂无商品」）；刷新失败保留旧数据仅 toast */
    if (!loaded.value) { items.value = []; loadErr.value = e.message || '请求失败' }
    toast('加载失败', 'error')
  }
  if (token === reqSeq) loaded.value = true
}
onMounted(() => { loadCategories(); load() })
function retryLoad() { loadErr.value = ''; loaded.value = false; load() }

function search() { state.page = 1; load() }
function clearSearch() { state.q = ''; state.page = 1; load() }
function tab(sv) { state.status = sv === null ? 'all' : String(sv); state.page = 1; load() }
function filterCat() { state.page = 1; load() }
/* 空态引导：有搜索/分类筛选时空态文案区分 + 一键清除 */
const filtered = computed(() => !!(state.q.trim() || state.category_id !== ''))
function clearFilters() { state.q = ''; state.category_id = ''; state.page = 1; load() }

/* 服务端排序：sort 直传后端（title/price/created_at，- 前缀降序），三态循环（无 → 升 → 降 → 无），切换重置页码 */
function sortBy(k) {
  state.sort = state.sort === k ? '-' + k : (state.sort === '-' + k ? '' : k)
  state.page = 1
  load()
}
const sortInd = (k) => (state.sort === k ? '▲' : state.sort === '-' + k ? '▼' : '')
const ariaSort = (k) => (state.sort === k ? 'ascending' : state.sort === '-' + k ? 'descending' : 'none')

/* ===== 批量上下架：全选作用于当前页可见行；翻页/筛选后勾选重置；上架/归档均走 ConfirmDialog ===== */
const selIds = ref([])
const visIds = computed(() => items.value.map((p) => p.id))
const allChecked = computed(() => visIds.value.length > 0 && visIds.value.every((id) => selIds.value.includes(id)))
function toggleAll() { selIds.value = allChecked.value ? [] : [...visIds.value] }

const batchDlg = reactive({ open: false, action: 'publish' })
const batchBusy = ref(false)
const batchProg = reactive({ done: 0, total: 0 })
const failText = (d) => (typeof d === 'string' && d ? (BULK_ERR[d] || d) : '请求失败')
const batchBody = computed(() => {
  const n = selIds.value.length
  let s = batchDlg.action === 'unpublish'
    ? `确认归档选中的 ${n} 款商品？归档后前台不再展示，可在「归档」tab 查看。`
    : `确认上架选中的 ${n} 款商品？上架后前台立即可见。`
  if (batchBusy.value) s += `\n\n正在处理：${batchProg.done}/${batchProg.total}`
  return s
})
function askBatch(action) { if (batchBusy.value) return; batchDlg.action = action; batchDlg.open = true }
/* 循环逐个调 publish/unpublish 端点（无批量接口），确认弹窗内实时进度，失败明细 toast 列出 slug 与原因 */
async function runBatch(action) {
  const ids = [...selIds.value]
  if (!ids.length || batchBusy.value) return
  batchBusy.value = true
  batchProg.total = ids.length
  batchProg.done = 0
  const fails = []
  for (let i = 0; i < ids.length; i++) {
    try { await req('POST', `/api/admin/catalog/products/${ids[i]}/${action}`) }
    catch (e) { fails.push({ id: ids[i], err: e.data?.detail || e.message || '' }) }
    batchProg.done = i + 1
  }
  const ok = ids.length - fails.length
  if (fails.length) {
    const lines = fails.map((f) => `${items.value.find((x) => x.id === f.id)?.slug || '#' + f.id}（${failText(f.err)}）`)
    toast(`批量${action === 'publish' ? '上架' : '归档'}失败 ${fails.length} 项：` + lines.join('、'), 'error')
  }
  toast(`批量${action === 'publish' ? '上架' : '归档'}完成：成功 ${ok}${fails.length ? '，失败 ' + fails.length : ''}`, fails.length ? 'error' : 'success')
  batchBusy.value = false
  batchDlg.open = false
  selIds.value = []
  load()
}

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

/* ===== CSV 导出：按当前状态tab+搜索+分类+排序循环翻页拉全量（size=50，上限 20 页）；转义/BOM 照抄 OrdersView ===== */
const exporting = ref(false)
const EXPORT_PER_PAGE = 50
const EXPORT_MAX_PAGES = 20
async function exportCsv() {
  if (exporting.value) return
  exporting.value = true
  try {
    const params = { page: 1, size: EXPORT_PER_PAGE }
    if (state.q.trim()) params.q = state.q.trim()
    if (status.value !== null) params.status = status.value
    if (state.category_id !== '') params.category_id = state.category_id
    if (state.sort) params.sort = state.sort
    const first = await req('GET', '/api/admin/catalog/products?' + new URLSearchParams(params))
    const all = [...(first.items || [])]
    const totalMatch = first.total ?? all.length
    const maxPage = Math.min(Math.ceil(totalMatch / EXPORT_PER_PAGE) || 1, EXPORT_MAX_PAGES)
    /* 第 2 页起每 5 页一批 Promise.all 并发（批间 await 控压，结果按页序拼接） */
    for (let s = 2; s <= maxPage; s += 5) {
      const end = Math.min(s + 4, maxPage)
      const batch = await Promise.all(
        Array.from({ length: end - s + 1 }, (_, i) =>
          req('GET', '/api/admin/catalog/products?' + new URLSearchParams({ ...params, page: s + i })))
      )
      for (const d of batch) all.push(...(d.items || []))
    }
    if (Math.ceil(totalMatch / EXPORT_PER_PAGE) > EXPORT_MAX_PAGES) {
      toast(`匹配结果超过 ${EXPORT_MAX_PAGES * EXPORT_PER_PAGE} 款，仅导出前 ${all.length} 款`, 'error')
    }
    /* CSV 转义：含逗号/引号/换行的字段包引号并双写引号 */
    const cell = (v) => {
      const s = String(v ?? '')
      return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
    }
    const catName = (p) => categories.value.find((c) => c.id === p.category_id)?.name || ''
    const rows = [['ID', '标题', 'slug', '状态', '分类', '价格区间', '变体数', '创建时间'],
      ...all.map((p) => [p.id, p.title, p.slug, SMeta[p.status]?.[0] || p.status, catName(p),
        p.price_max > p.price_min ? money(p.price_min) + '~' + money(p.price_max) : money(p.price_min),
        p.variant_count ?? '', dt(p.created_at)])]
    const csv = rows.map((r) => r.map(cell).join(',')).join('\n')
    const stLabel = TABS.find(([sv]) => sv === status.value)?.[1] || '全部'
    const url = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `products-${stLabel}-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast('已导出 ' + all.length + ' 款 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  exporting.value = false
}

/* 上架/归档确认弹窗：归档为危险操作；定时商品上架按计划时间生效（后端不再覆盖定时） */
const dlg = reactive({ open: false, busy: false, p: null, action: 'publish' })
const dlgBody = computed(() => {
  if (!dlg.p) return ''
  let s = dlg.action === 'publish'
    ? `上架「${dlg.p.title}」后前台立即可见。`
    : `归档「${dlg.p.title}」后前台不再展示，可在「归档」tab 查看。`
  if (dlg.action === 'publish' && dlg.p.scheduled) s += '\nℹ️ 该商品已设定时上架，将按计划时间生效。'
  return s
})
function toggle(p) {
  dlg.p = p
  dlg.action = p.status === 1 ? 'unpublish' : 'publish'
  dlg.open = true
}
async function doToggle() {
  if (!dlg.p) return
  dlg.busy = true
  try {
    await req('POST', `/api/admin/catalog/products/${dlg.p.id}/${dlg.action}`)
    toast(dlg.action === 'publish' ? '已上架 ✓' : '已归档 ✓', 'success')
    dlg.open = false
    load()
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
  finally { dlg.busy = false }
}

/* 关闭批量导入弹窗时清空草稿与上次结果 */
function closeBulk() { bulk.value = false; bulkText.value = ''; bulkResult.value = null }

async function bulkImport() {
  try {
    /* 分类白名单：动态分类集合（拉取失败回退任意正整数，后端兜底校验） */
    const catHint = categories.value.length
      ? '可用分类 id：' + categories.value.map((c) => `${c.id}（${c.name}）`).join('、')
      : '分类列表为空或未加载成功，暂仅校验为正整数（后端会再校验一次）'
    const lines = bulkText.value.trim().split(/\n+/).filter(Boolean)
    const bad = []
    const rows = lines.map((l, i) => {
      const c = l.split(',').map((s) => s.trim())
      /* 固定列序 slug,title,price,category_id：列数不足 4 直接判格式错误 */
      if (c.length < 4) { bad.push(`第 ${i + 1} 行：列数不足 4（需 slug,title,price,category_id）`); return null }
      const price = Math.round(parseFloat(c[2]) * 100)
      const cat = Number(c[3])
      if (!c[0] || !c[1] || !Number.isFinite(price) || price < 0) { bad.push(`第 ${i + 1} 行：slug/标题缺失或价格无效`); return null }
      const catOk = catIdSet.value.size ? catIdSet.value.has(cat) : (Number.isInteger(cat) && cat >= 1)
      if (!catOk) { bad.push(`第 ${i + 1} 行：category_id 无效（当前 ${c[3]}）。${catHint}`); return null }
      return { slug: c[0], title: c[1], price_min: price, price_max: price, category_id: cat }
    }).filter(Boolean)
    if (bad.length) { toast('存在格式错误的行，未导入：' + bad[0] + (bad.length > 1 ? ` 等 ${bad.length} 处` : ''), 'error'); return }
    if (!rows.length) { toast('没有可导入的行', 'error'); return }
    const d = await req('POST', '/api/admin/catalog/products/bulk', { items: rows })
    bulkResult.value = d
    toast(d.failed ? `导入完成：成功 ${d.created} / 失败 ${d.failed}` : `全部导入成功（${d.created}）✓`, d.failed ? 'error' : 'success')
    load()
  } catch (e) { toast('导入失败：' + (e.data?.detail || e.message), 'error') }
}

/* ===== 分类管理：列表展示 + 新建（CategoryCreateIn：name/slug 必填，parent_id 可选） ===== */
const catDlg = ref(false)
const catBusy = ref(false)
const catForm = reactive({ name: '', slug: '', parent_id: null })
async function createCat() {
  const name = catForm.name.trim()
  const slug = catForm.slug.trim()
  if (!name || !slug) { toast('名称与 slug 必填', 'error'); return }
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug)) { toast('slug 格式：仅小写字母、数字与连字符（如 press-on-nails）', 'error'); return }
  catBusy.value = true
  try {
    await req('POST', '/api/admin/catalog/categories', { name, slug, parent_id: catForm.parent_id })
    toast('分类已创建 ✓', 'success')
    Object.assign(catForm, { name: '', slug: '', parent_id: null })
    catDlg.value = false
    loadCategories()
  } catch (e) {
    const d = e.data?.detail
    toast('创建失败：' + (d === 'slug already exists' ? 'slug 已存在' : (d || e.message)), 'error')
  } finally { catBusy.value = false }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">商品管理</h1>
      <span class="page-sub">共 {{ total }} 款</span>
    </div>
    <!-- 主按钮「新建商品」保持突出，次要操作（分类/导入/导出）收为一组；整行 flex-wrap 防窄屏溢出 -->
    <div class="topbar-actions">
      <div style="position:relative">
        <input v-model="state.q" class="input" style="width:220px;padding-right:30px" placeholder="搜标题 / slug" @keydown.enter="search">
        <button v-if="state.q" type="button" class="q-clear" aria-label="清空搜索" @click="clearSearch">×</button>
      </div>
      <button class="btn btn-secondary" @click="search">搜索</button>
      <router-link to="/product-edit" class="btn btn-primary">＋ 新建商品</router-link>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;border-left:1px solid var(--gray-light);padding-left:10px">
        <button class="btn btn-secondary" @click="catDlg = true">🏷 分类管理</button>
        <button class="btn btn-secondary" @click="bulk = true">📦 批量导入</button>
        <button class="btn btn-secondary" :disabled="exporting" @click="exportCsv">{{ exporting ? '导出中…' : '⌄ 导出 CSV' }}</button>
      </div>
    </div>
  </div>

  <div class="otab">
    <button v-for="[sv, label] in TABS" :key="String(sv)" :class="{ on: status === sv }" @click="tab(sv)">{{ label }}</button>
    <div style="margin-left:auto;align-self:center;display:flex;align-items:center;gap:6px">
      <select v-model="state.category_id" class="input" style="width:auto;max-width:180px;padding:6px 10px;font-size:12.5px" title="按分类筛选（作用于全部页）" @change="filterCat">
        <option :value="''">全部分类</option>
        <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
    </div>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px" />

  <!-- 首载失败：错误空态 + 重试（不再误导为「暂无商品」） -->
  <div v-else-if="loadErr" class="card">
    <EmptyState icon="⚠️" title="商品列表加载失败" :sub="loadErr">
      <template #action>
        <button class="btn btn-primary btn-sm" @click="retryLoad">重试</button>
        <router-link to="/product-edit" class="btn btn-secondary btn-sm">➕ 新建商品</router-link>
      </template>
    </EmptyState>
  </div>

  <div v-else class="card tbl-wrap">
    <!-- 批量操作条：勾选任意行后出现，上架/归档均走确认弹窗 -->
    <div v-if="selIds.length" style="display:flex;gap:10px;align-items:center;padding:10px 12px;background:var(--rose-pale);font-size:13px;flex-wrap:wrap">
      已选 <b>{{ selIds.length }}</b> 款
      <button class="btn btn-primary btn-sm" :disabled="batchBusy" @click="askBatch('publish')">上架</button>
      <button class="btn btn-sm" style="background:var(--error);color:#fff" :disabled="batchBusy" @click="askBatch('unpublish')">归档</button>
      <button class="btn btn-ghost btn-sm" style="margin-left:auto" :disabled="batchBusy" @click="selIds = []">取消</button>
    </div>
    <table v-if="items.length" style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="width:28px"><input type="checkbox" :checked="allChecked" :disabled="!visIds.length" title="全选本页" @change="toggleAll"></th>
        <th class="sortable" tabindex="0" role="button" :aria-sort="ariaSort('title')" title="点击排序（回车/空格亦可）" @click="sortBy('title')" @keydown.enter.prevent="sortBy('title')" @keydown.space.prevent="sortBy('title')">商品<span v-if="sortInd('title')" class="sort-ind">{{ sortInd('title') }}</span></th>
        <th class="sortable" tabindex="0" role="button" :aria-sort="ariaSort('price')" title="点击排序（回车/空格亦可）" @click="sortBy('price')" @keydown.enter.prevent="sortBy('price')" @keydown.space.prevent="sortBy('price')">价格<span v-if="sortInd('price')" class="sort-ind">{{ sortInd('price') }}</span></th>
        <th>库存</th>
        <th>销量</th>
        <th>评分</th>
        <th class="sortable" tabindex="0" role="button" :aria-sort="ariaSort('created_at')" title="点击排序（回车/空格亦可）" @click="sortBy('created_at')" @keydown.enter.prevent="sortBy('created_at')" @keydown.space.prevent="sortBy('created_at')">创建时间<span v-if="sortInd('created_at')" class="sort-ind">{{ sortInd('created_at') }}</span></th>
        <th>状态</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="p in items" :key="p.id" style="border-top:1px solid var(--gray-light)">
          <td><input type="checkbox" :value="p.id" v-model="selIds"></td>
          <td>
            <div style="display:flex;gap:10px;align-items:center">
              <img v-if="p.hero_image && !p.broken" :src="p.hero_image" :alt="p.title" style="width:42px;height:42px;border-radius:8px;object-fit:cover" @error="p.broken = true">
              <div v-else style="width:42px;height:42px;border-radius:8px;background:var(--rose-pale);color:var(--plum);display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;flex:none">{{ (p.title || '?').slice(0, 1).toUpperCase() }}</div>
              <div>
                <b>{{ p.title }}</b>
                <span v-if="p.is_new" class="tag tag-paid" style="margin-left:6px;font-size:10px">NEW</span>
                <span v-if="p.is_best_seller" class="tag tag-done" style="margin-left:4px;font-size:10px">HOT</span>
                <div style="font-size:11.5px;color:var(--gray)">{{ p.slug }} · {{ p.variant_count ?? 0 }} 变体</div>
              </div>
            </div>
          </td>
          <td>
            <b>{{ money(p.price_min) }}</b><span v-if="p.price_max > p.price_min" style="color:var(--gray)">–{{ money(p.price_max) }}</span>
            <div v-if="p.compare_at_price" style="font-size:11px;color:var(--gray);text-decoration:line-through">{{ money(p.compare_at_price) }}</div>
          </td>
          <td>
            <!-- 颜色语义与编辑页统一：为 0 红 error、低于安全线黄 warn、充足灰 done -->
            <span class="tag" :class="!p.total_stock ? 'tag-error' : (p.low_stock_count ? 'tag-pending' : 'tag-done')">{{ p.total_stock ?? 0 }}</span>
            <div v-if="p.low_stock_count" style="font-size:11px;color:var(--warn)">{{ p.low_stock_count }} 个低水位</div>
          </td>
          <td style="color:var(--gray)">{{ p.sold_count ?? 0 }}</td>
          <td style="color:var(--gray)">{{ ((p.rating_avg || 0) / 100).toFixed(1) }} <small v-if="p.rating_count">({{ p.rating_count }})</small></td>
          <td style="color:var(--gray)">{{ dt(p.created_at) || '—' }}</td>
          <td>
            <span class="tag" :class="SMeta[p.status]?.[1] || 'tag'">{{ SMeta[p.status]?.[0] || p.status }}</span>
            <!-- 定时徽标按状态区分：已上架=到点前台可见；草稿/归档=需手动上架后才生效 -->
            <span v-if="p.scheduled" class="tag tag-sched" style="margin-left:4px" :title="p.status === 1 ? '到点后在前台可见' : '注意：需手动上架后才会生效'">定时</span>
          </td>
          <td style="text-align:right;white-space:nowrap">
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/product-edit', query: { id: p.id } }">编辑</router-link>
            <button class="btn btn-ghost btn-sm" style="margin-left:6px" title="复制商品" @click="router.push('/product-edit?copy=' + p.id)">⧉</button>
            <button class="btn btn-ghost btn-sm" style="margin-left:6px" @click="toggle(p)">{{ p.status === 1 ? '归档' : '上架' }}</button>
          </td>
        </tr>
      </tbody>
    </table>
    <EmptyState v-else icon="🔍" :title="filtered ? '未找到匹配的商品' : '暂无商品'" :sub="filtered ? '试试清除筛选' : '点击右上角「新建商品」创建第一个'">
      <template #action>
        <button v-if="filtered" class="btn btn-secondary btn-sm" @click="clearFilters">清除筛选</button>
        <router-link to="/product-edit" class="btn btn-primary btn-sm">➕ 新建商品</router-link>
      </template>
    </EmptyState>
  </div>

  <Pagination v-if="loaded && !loadErr" :page="state.page" :pages="pages" :total="total" unit="款" @go="state.page = $event; load()" />

  <!-- 批量导入弹窗 -->
  <div v-if="bulk" class="modal open" @click.self="closeBulk">
    <div class="modal-box" style="max-width:560px">
      <button class="modal-x" @click="closeBulk">×</button>
      <div class="dhead"><h3 class="dtitle">📦 批量导入</h3></div>
      <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">CSV 粘贴（slug,title,price,category_id）≤100 行，部分成功不回滚；price 单位美元，库存请在变体中维护。</p>
      <textarea v-model="bulkText" class="input" rows="8" placeholder="nova-set,Nova Set,15.99,1"></textarea>
      <button class="btn btn-primary btn-block" style="margin-top:12px" @click="bulkImport">导入</button>
      <div v-if="bulkResult" style="margin-top:12px;font-size:12.5px">
        <p style="color:var(--gray)">结果：成功 <b style="color:var(--success)">{{ bulkResult.created }}</b> · 失败 <b :style="{ color: bulkResult.failed ? 'var(--error)' : 'var(--gray)' }">{{ bulkResult.failed }}</b></p>
        <div v-if="failures.length" style="max-height:180px;overflow-y:auto;border-top:1px dashed var(--gray-light);padding-top:8px">
          <div v-for="f in failures" :key="f.index" style="padding:3px 0;color:var(--error)">
            第 {{ f.index + 1 }} 行 · {{ f.slug || '（无 slug）' }}：{{ BULK_ERR[f.error] || f.error }}
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 分类管理弹窗：列表 + 新建（后端无商品计数字段，仅展示名称/id/slug） -->
  <div v-if="catDlg" class="modal open" @click.self="catDlg = false">
    <div class="modal-box" style="max-width:480px">
      <button class="modal-x" @click="catDlg = false">×</button>
      <div class="dhead"><h3 class="dtitle">🏷 分类管理</h3></div>
      <div style="max-height:200px;overflow-y:auto;margin-bottom:14px;border:1px solid var(--gray-light);border-radius:8px">
        <div v-for="c in categories" :key="c.id" style="display:flex;gap:10px;align-items:center;padding:7px 10px;border-bottom:1px solid var(--gray-light);font-size:13px">
          <b>{{ c.name }}</b>
          <span style="color:var(--gray);font-size:12px">id {{ c.id }} · {{ c.slug }}</span>
          <span v-if="!c.is_active" class="tag tag-pending" style="margin-left:auto;font-size:10px">停用</span>
        </div>
        <div v-if="!categories.length" style="padding:10px;font-size:13px;color:var(--gray)">暂无分类</div>
      </div>
      <div style="display:grid;gap:12px">
        <div class="field"><label>名称 *</label><input v-model="catForm.name" class="input" placeholder="Press-On Nails"></div>
        <div class="field"><label>Slug *</label><input v-model="catForm.slug" class="input" placeholder="press-on-nails"></div>
        <div class="field"><label>父分类（可选）</label>
          <select v-model="catForm.parent_id" class="input">
            <option :value="null">无（顶级分类）</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </div>
      </div>
      <div style="display:flex;gap:10px;margin-top:16px">
        <button class="btn btn-secondary" style="flex:1" :disabled="catBusy" @click="catDlg = false">取消</button>
        <button class="btn btn-primary" style="flex:1" :class="{ loading: catBusy }" :disabled="catBusy" @click="createCat">保存</button>
      </div>
    </div>
  </div>

  <!-- 上架/归档确认 -->
  <ConfirmDialog :open="dlg.open" :title="dlg.action === 'unpublish' ? '归档商品' : '上架商品'" :body="dlgBody"
                 :danger="dlg.action === 'unpublish'" :confirm-text="dlg.action === 'unpublish' ? '归档' : '上架'"
                 :busy="dlg.busy" @confirm="doToggle" @close="dlg.open = false" />
  <!-- 批量上架/归档确认（归档危险；执行中弹窗内显示进度 n/total，busy 期间不可关闭） -->
  <ConfirmDialog :open="batchDlg.open" :title="batchDlg.action === 'unpublish' ? '批量归档' : '批量上架'" :body="batchBody"
                 :danger="batchDlg.action === 'unpublish'" :confirm-text="batchDlg.action === 'unpublish' ? '归档' : '上架'"
                 :busy="batchBusy" @confirm="runBatch(batchDlg.action)" @close="batchDlg.open = false" />
</template>

<style scoped>
td,th{padding:10px 12px}
.otab button{background:none;border:none;border-bottom:2.5px solid transparent;cursor:pointer}
.otab button.on{color:var(--plum);border-color:var(--plum)}
/* 顶栏操作组：主按钮+次要组整行可换行（全局类由 admin.css 提供，此处兜底同规则） */
.topbar-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
/* 可排序表头键盘可达：焦点环 */
th.sortable:focus-visible{outline:2px solid var(--plum);outline-offset:-2px}
/* 搜索框清空钮：悬浮输入框右侧 */
.q-clear{position:absolute;right:8px;top:50%;transform:translateY(-50%);width:17px;height:17px;border:none;border-radius:50%;background:var(--gray-light);color:#fff;font-size:11px;line-height:1;cursor:pointer;padding:0}
.q-clear:hover{background:var(--gray)}
</style>
