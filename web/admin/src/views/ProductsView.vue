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

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
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

/* ===== URL 同步：page/status（tab 映射，'all'=全部）+ 原有 category_id/sort/per_page 一并并入 useQuerySync
 * q 拆出同步态为本地 ref：输入不逐字符 router.replace，仅搜索触发/回车/清空时写回 URL（做法同 OrdersView） ===== */
const SORTABLE = ['title', '-title', 'price', '-price', 'created_at', '-created_at']
const state = reactive({ page: 1, status: 'all', category_id: '', sort: '', per_page: 50 })
useQuerySync(state, { nums: ['page', 'category_id', 'per_page'], defaults: { page: 1, status: 'all', category_id: '', sort: '', per_page: 50 }, onPop: () => load() })
/* 回填清洗：非法值回落默认（顺带触发 watch 清掉 URL 脏键） */
if (!SORTABLE.includes(state.sort)) state.sort = ''
if (!['all', '0', '1', '2'].includes(state.status)) state.status = 'all'
if (!(state.page >= 1)) state.page = 1
if (!(state.category_id >= 1)) state.category_id = ''
if (![20, 50, 100].includes(state.per_page)) state.per_page = 50
const q = ref(typeof route.query.q === 'string' ? route.query.q : '')
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
    const qs = { page: state.page, size: state.per_page, q: q.value.trim() }
    if (status.value !== null) qs.status = status.value
    if (state.category_id !== '') qs.category_id = state.category_id
    if (state.sort) qs.sort = state.sort
    const d = await req('GET', '/api/admin/catalog/products?' + new URLSearchParams(qs))
    if (token !== reqSeq) return
    items.value = d.items || []
    total.value = d.total ?? 0
    /* 后端 admin_products 响应已含 pages（ceil(total/size)），直消费避免本地口径漂移 */
    pages.value = Math.max(1, d.pages ?? Math.ceil(total.value / state.per_page))
    /* 当前页删空回落：本页记录被删光且不在第 1 页时回第 1 页重拉一次（已在第 1 页则空态渲染，无递归） */
    if (!items.value.length && state.page > 1) { state.page = 1; load(); return }
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

/* 顶栏搜索：回车/按钮触发才写回 URL（一次性 replace 同批清掉 page 键，防 useQuerySync 的 deep watcher
 * 基于旧 query 再发一次 replace 把刚写入的 q 覆盖丢失，做法同 ReturnsView）；页码键被清除时其
 * query-watcher 已重置页码并经 onPop 重载，否则手动重载 */
async function search() {
  const kw = q.value.trim()
  q.value = kw   /* 归一化输入与 URL/请求一致 */
  const hadPageKey = route.query.page !== undefined
  if ((route.query.q || '') !== kw || hadPageKey) {
    await router.replace({ query: { ...route.query, q: kw || undefined, page: undefined } })
  }
  state.page = 1
  if (!hadPageKey) load()
}
function clearSearch() { q.value = ''; search() }
function tab(sv) { state.status = sv === null ? 'all' : String(sv); state.page = 1; load() }
function filterCat() { state.page = 1; load() }
/* 空态引导：有搜索/分类筛选时空态文案区分 + 一键清除 */
const filtered = computed(() => !!(q.value.trim() || state.category_id !== ''))
/* 清除筛选：q 先 replace 落地再清 category_id（tracked 键突变交由 deep watcher 写回，防同批覆盖丢 q） */
async function clearFilters() {
  q.value = ''
  const hadPageKey = route.query.page !== undefined
  if (route.query.q !== undefined || hadPageKey) {
    await router.replace({ query: { ...route.query, q: undefined, page: undefined } })
  }
  state.category_id = ''
  state.page = 1
  if (!hadPageKey) load()
}
/* 浏览器回退/前进：q 变化只同步回本地 ref 并重载（不触发导航）；页码键由 useQuerySync 的
 * query-watcher 先行回落默认（其 watch 创建早于本处，同批 flush 先执行） */
watch(() => route.query.q, (v) => {
  if (route.name !== 'products') return   /* 已离开本页（卸载前最后一次 route 变更）：忽略 */
  const s = typeof v === 'string' ? v : ''
  if (s !== q.value) {
    q.value = s
    load()
  }
})

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
/* 批量上下架走后端批量端点（单次 POST batch-status：1=上架、2=归档，ids ≤100），failed 明细按「#id reason」汇总 toast */
async function runBatch(action) {
  const ids = [...selIds.value]
  if (!ids.length || batchBusy.value) return
  batchBusy.value = true
  batchProg.total = ids.length
  batchProg.done = 0
  let fails = []
  try {
    const d = await req('POST', '/api/admin/catalog/products/batch-status', { ids, status: action === 'publish' ? 1 : 2 })
    batchProg.done = ids.length
    fails = d.failed || []
    if (fails.length) {
      const lines = fails.map((f) => `#${f.id} ${failText(f.reason)}`)
      toast(`批量${action === 'publish' ? '上架' : '归档'}失败 ${fails.length} 项：` + lines.join('、'), 'error')
    }
    const ok = d.updated ?? (ids.length - fails.length)
    toast(`批量${action === 'publish' ? '上架' : '归档'}完成：成功 ${ok}${fails.length ? '，失败 ' + fails.length : ''}`, fails.length ? 'error' : 'success')
  } catch (e) { toast('批量操作失败：' + (e.data?.detail || e.message), 'error') }
  batchBusy.value = false
  batchDlg.open = false
  selIds.value = []
  load()
}

/* ===== CSV 导出 ===== */
const exporting = ref(false)
async function exportCsv() {
  if (exporting.value) return
  exporting.value = true
  try {
    if (!categories.value.length) await loadCategories()
    if (!categories.value.length) toast('分类列缺失（分类数据加载失败）', 'error')
    const { all, truncated } = await fetchAllPages((p) => req('GET', '/api/admin/catalog/products?' + new URLSearchParams({
      page: p, size: 100,
      ...(q.value.trim() ? { q: q.value.trim() } : {}),
      ...(status.value !== null ? { status: status.value } : {}),
      ...(state.category_id !== '' ? { category_id: state.category_id } : {}),
      ...(state.sort ? { sort: state.sort } : {}),
    })), { pageSize: 100, maxPages: 20 })
    if (truncated) toast(`匹配结果超过 2000 款，已截断至 ${all.length} 条`, 'error')
    const catName = (p) => categories.value.find((c) => c.id === p.category_id)?.name || ''
    const stLabel = TABS.find(([sv]) => sv === status.value)?.[1] || '全部'
    downloadCsv({
      filename: `products-${stLabel}-${new Date().toISOString().slice(0, 10)}${truncated ? `-已截断至${all.length}条` : ''}`,
      headers: ['ID', '标题', 'slug', '状态', '分类', '价格区间', '变体数', '创建时间'],
      rows: all.map((p) => [p.id, p.title, p.slug, SMeta[p.status]?.[0] || p.status, catName(p),
        p.price_max > p.price_min ? money(p.price_min) + '~' + money(p.price_max).slice(1) : money(p.price_min),
        p.variant_count ?? '', dt(p.created_at)]),
    })
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

/* 归档行「恢复草稿」：走批量端点单条 status=0（仅归档态可恢复），失败显示后端原因，成功后刷新 */
const restoreDlg = ref(false)
const restoreBusy = ref(false)
const restoreTarget = ref(null)
function askRestore(p) { restoreTarget.value = p; restoreDlg.value = true }
async function restoreDraft() {
  const p = restoreTarget.value
  if (!p || restoreBusy.value) return
  restoreBusy.value = true
  try {
    const d = await req('POST', '/api/admin/catalog/products/batch-status', { ids: [p.id], status: 0 })
    const fails = d.failed || []
    if (fails.length) toast(`恢复草稿失败：#${fails[0].id} ${failText(fails[0].reason)}`, 'error')
    else { toast('已恢复为草稿 ✓', 'success'); restoreDlg.value = false; load() }
  } catch (e) { toast('恢复草稿失败：' + (e.data?.detail || e.message), 'error') }
  finally { restoreBusy.value = false }
}

/* 关闭批量导入弹窗时清空草稿、上次结果与待确认导入 */
function closeBulk() { if (bulkBusy.value) return; bulk.value = false; bulkText.value = ''; bulkResult.value = null; bulkPending.value = null }

/* 批量导入防呆：bulkBusy 提交期间禁用按钮/关弹窗；行数 >100 前端拦截；提交前 ConfirmDialog 确认（显示将导入行数） */
const bulkBusy = ref(false)
const bulkPending = ref(null)   /* 校验通过的待导入行（非空即弹出确认弹窗） */
async function bulkImport() {
  if (bulkBusy.value) return
  /* 分类白名单：动态分类集合（拉取失败回退任意正整数，后端兜底校验） */
  const catHint = categories.value.length
    ? '可用分类 id：' + categories.value.map((c) => `${c.id}（${c.name}）`).join('、')
    : '分类列表为空或未加载成功，暂仅校验为正整数（后端会再校验一次）'
  const lines = bulkText.value.trim().split(/\n+/).filter(Boolean)
  if (lines.length > 100) { toast(`一次最多导入 100 行（当前 ${lines.length} 行），请分批粘贴`, 'error'); return }
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
  bulkPending.value = rows
}
const bulkConfirmBody = computed(() => `确认导入 ${bulkPending.value?.length || 0} 款商品？部分成功不回滚，库存需在变体中维护。`)
async function doBulkImport() {
  if (bulkBusy.value || !bulkPending.value) return
  bulkBusy.value = true
  try {
    const d = await req('POST', '/api/admin/catalog/products/bulk', { items: bulkPending.value })
    bulkResult.value = d
    toast(d.failed ? `导入完成：成功 ${d.created} / 失败 ${d.failed}` : `全部导入成功（${d.created}）✓`, d.failed ? 'error' : 'success')
    load()
  } catch (e) { toast('导入失败：' + (e.data?.detail || e.message), 'error') }
  bulkBusy.value = false
  bulkPending.value = null
}

/* ===== 分类管理：列表展示 + 新建/编辑（新建 name/slug 必填；PUT 全可选：name/slug/parent_id/sort_order/is_active）/ 删除（409 引用拦截） ===== */
const catDlg = ref(false)
const catBusy = ref(false)
const catForm = reactive({ id: null, name: '', slug: '', parent_id: null, sort_order: 0, is_active: 1 })
/* 后端错误码 → 中文（409：被商品/子分类引用不可删） */
const CAT_ERR = {
  'slug already exists': 'slug 已存在',
  'category in use': '分类下仍有商品',
  'category has children': '存在子分类，需先处理子分类',
  'parent is self': '父分类不能是自己',
  'category cycle detected': '不能将分类移到自己的子分类下（会形成循环）',
  'parent category not found': '父分类不存在',
  'category not found': '分类不存在',
}
function newCat() {
  Object.assign(catForm, { id: null, name: '', slug: '', parent_id: null, sort_order: 0, is_active: 1 })
  catDlg.value = true
}
function editCat(c) {
  Object.assign(catForm, { id: c.id, name: c.name || '', slug: c.slug || '', parent_id: c.parent_id ?? null, sort_order: c.sort_order ?? 0, is_active: c.is_active ? 1 : 0 })
  catDlg.value = true
}
/* 编辑时父分类选项排除自身，防自引用环路 */
const catParentOptions = computed(() => categories.value.filter((c) => c.id !== catForm.id))
async function saveCat() {
  const name = catForm.name.trim()
  const slug = catForm.slug.trim()
  if (!name || !slug) { toast('名称与 slug 必填', 'error'); return }
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug)) { toast('slug 格式：仅小写字母、数字与连字符（如 press-on-nails）', 'error'); return }
  catBusy.value = true
  try {
    if (catForm.id) {
      await req('PUT', '/api/admin/catalog/categories/' + catForm.id, {
        name, slug,
        parent_id: catForm.parent_id ?? null,
        sort_order: catForm.sort_order | 0,
        is_active: catForm.is_active ? 1 : 0,
      })
      toast('分类已保存 ✓', 'success')
    } else {
      await req('POST', '/api/admin/catalog/categories', { name, slug, parent_id: catForm.parent_id })
      toast('分类已创建 ✓', 'success')
    }
    catDlg.value = false
    loadCategories()
  } catch (e) {
    const d = e.data?.detail
    toast((catForm.id ? '保存失败：' : '创建失败：') + (CAT_ERR[d] || d || e.message), 'error')
  } finally { catBusy.value = false }
}
/* 删除分类：危险确认；被商品/子分类引用时后端 409（toast 翻译） */
const catDelDlg = ref(false)
const catDelBusy = ref(false)
const catDelTarget = ref(null)
function delCat(c) { catDelTarget.value = c; catDelDlg.value = true }
async function doDelCat() {
  const c = catDelTarget.value
  if (!c || catDelBusy.value) return
  catDelBusy.value = true
  try {
    await req('DELETE', '/api/admin/catalog/categories/' + c.id)
    toast('分类已删除', 'success')
    catDelDlg.value = false
    loadCategories()
    /* 被删分类恰为当前筛选：清空筛选并重载，防列表对已删 id 恒空 */
    if (state.category_id === c.id) { state.category_id = ''; state.page = 1; load() }
  } catch (e) {
    const d = e.data?.detail
    toast('删除失败：' + (CAT_ERR[d] || d || e.message), 'error')
  }
  catDelBusy.value = false
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
      <span style="font-size:12px;color:var(--gray)">每页</span>
      <select v-model.number="state.per_page" class="input" aria-label="每页条数" style="width:auto;height:36px;font-size:13px" @change="state.page = 1; load()">
        <option :value="20">20 条/页</option>
        <option :value="50">50 条/页</option>
        <option :value="100">100 条/页</option>
      </select>
      <div style="position:relative">
        <input v-model="q" class="input js-search" style="width:220px;padding-right:30px" placeholder="搜标题 / slug" @keydown.enter="search">
        <button v-if="q" type="button" class="q-clear" aria-label="清空搜索" @click="clearSearch">×</button>
      </div>
      <button class="btn btn-secondary" @click="search">搜索</button>
      <router-link v-if="session.hasPerm('catalog:manage')" to="/product-edit" class="btn btn-primary">＋ 新建商品</router-link>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;border-left:1px solid var(--gray-light);padding-left:10px">
        <button class="btn btn-secondary" @click="newCat">🏷 分类管理</button>
        <button v-if="session.hasPerm('catalog:manage')" class="btn btn-secondary" @click="bulk = true">📦 批量导入</button>
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
        <router-link v-if="session.hasPerm('catalog:manage')" to="/product-edit" class="btn btn-secondary btn-sm">➕ 新建商品</router-link>
      </template>
    </EmptyState>
  </div>

  <div v-else class="card tbl-wrap">
    <!-- 批量操作条：勾选任意行后出现，上架/归档均走确认弹窗 -->
    <div v-if="selIds.length" style="display:flex;gap:10px;align-items:center;padding:10px 12px;background:var(--rose-pale);font-size:13px;flex-wrap:wrap">
      已选 <b>{{ selIds.length }}</b> 款
      <button v-if="session.hasPerm('catalog:manage')" class="btn btn-primary btn-sm" :disabled="batchBusy" @click="askBatch('publish')">上架</button>
      <button v-if="session.hasPerm('catalog:manage')" class="btn btn-sm" style="background:var(--error);color:#fff" :disabled="batchBusy" @click="askBatch('unpublish')">归档</button>
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
          <td style="color:var(--gray)">{{ p.rating_count ? ((p.rating_avg || 0) / 100).toFixed(1) : '—' }} <small v-if="p.rating_count">({{ p.rating_count }})</small></td>
          <td style="color:var(--gray)">{{ dt(p.created_at) || '—' }}</td>
          <td>
            <span class="tag" :class="SMeta[p.status]?.[1] || 'tag'">{{ SMeta[p.status]?.[0] || p.status }}</span>
            <!-- 定时徽标按状态区分：已上架=到点前台可见；草稿/归档=需手动上架后才生效 -->
            <span v-if="p.scheduled" class="tag tag-sched" style="margin-left:4px" :title="p.status === 1 ? '到点后在前台可见' : '注意：需手动上架后才会生效'">定时</span>
          </td>
          <td style="text-align:right;white-space:nowrap">
            <router-link v-if="session.hasPerm('catalog:manage')" class="btn btn-secondary btn-sm" :to="{ path: '/product-edit', query: { id: p.id } }">编辑</router-link>
            <button v-if="session.hasPerm('catalog:manage')" class="btn btn-ghost btn-sm" style="margin-left:6px" title="复制商品" @click="router.push('/product-edit?copy=' + p.id)">⧉</button>
            <button v-if="session.hasPerm('catalog:manage')" class="btn btn-ghost btn-sm" style="margin-left:6px" @click="toggle(p)">{{ p.status === 1 ? '归档' : '上架' }}</button>
            <button v-if="p.status === 2 && session.hasPerm('catalog:manage')" class="btn btn-ghost btn-sm" style="margin-left:6px" @click="askRestore(p)">恢复草稿</button>
          </td>
        </tr>
      </tbody>
    </table>
    <EmptyState v-else icon="🔍" :title="filtered ? '未找到匹配的商品' : '暂无商品'" :sub="filtered ? '试试清除筛选' : '点击右上角「新建商品」创建第一个'">
      <template #action>
        <button v-if="filtered" class="btn btn-secondary btn-sm" @click="clearFilters">清除筛选</button>
        <router-link v-if="session.hasPerm('catalog:manage')" to="/product-edit" class="btn btn-primary btn-sm">➕ 新建商品</router-link>
      </template>
    </EmptyState>
  </div>

  <Pagination v-if="loaded && !loadErr" :page="state.page" :pages="pages" :total="total" unit="款" @go="state.page = $event; load()" />

  <!-- 批量导入弹窗（提交走确认弹窗；bulkBusy 期间不可关闭防丢输入） -->
  <div v-if="bulk" class="modal open" @click.self="!bulkBusy && closeBulk()">
    <div class="modal-box" style="max-width:560px">
      <button class="modal-x" @click="!bulkBusy && closeBulk()">×</button>
      <div class="dhead"><h3 class="dtitle">📦 批量导入</h3></div>
      <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">CSV 粘贴（slug,title,price,category_id）≤100 行，部分成功不回滚；price 单位美元，库存请在变体中维护。</p>
      <textarea v-model="bulkText" class="input" rows="8" placeholder="nova-set,Nova Set,15.99,1"></textarea>
      <button class="btn btn-primary btn-block" style="margin-top:12px" :class="{ loading: bulkBusy }" :disabled="bulkBusy" @click="bulkImport">导入</button>
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

  <!-- 分类管理弹窗：列表（编辑/删除）+ 新建/编辑表单（后端无商品计数字段，仅展示名称/id/slug） -->
  <div v-if="catDlg" class="modal open" @click.self="!catBusy && (catDlg = false)">
    <div class="modal-box" style="max-width:480px">
      <button class="modal-x" @click="!catBusy && (catDlg = false)">×</button>
      <div class="dhead"><h3 class="dtitle">🏷 分类管理</h3></div>
      <div style="max-height:200px;overflow-y:auto;margin-bottom:14px;border:1px solid var(--gray-light);border-radius:8px">
        <div v-for="c in categories" :key="c.id" style="display:flex;gap:10px;align-items:center;padding:7px 10px;border-bottom:1px solid var(--gray-light);font-size:13px">
          <b>{{ c.name }}</b>
          <span style="color:var(--gray);font-size:12px">id {{ c.id }} · {{ c.slug }}</span>
          <span style="margin-left:auto;display:flex;gap:4px;align-items:center">
            <span v-if="!c.is_active" class="tag tag-pending" style="font-size:10px">停用</span>
            <button v-if="session.hasPerm('catalog:manage')" class="btn btn-ghost btn-sm" style="padding:2px 10px" @click="editCat(c)">编辑</button>
            <button v-if="session.hasPerm('catalog:manage')" class="btn btn-ghost btn-sm" style="padding:2px 10px;color:var(--error)" @click="delCat(c)">删除</button>
          </span>
        </div>
        <div v-if="!categories.length" style="padding:10px;font-size:13px;color:var(--gray)">暂无分类</div>
      </div>
      <!-- 新建/编辑表单与保存按钮：catalog:manage 可见（只读角色仅可查看列表） -->
      <template v-if="session.hasPerm('catalog:manage')">
      <div style="display:grid;gap:12px">
        <div class="field"><label>名称 *</label><input v-model="catForm.name" class="input" placeholder="Press-On Nails"></div>
        <div class="field"><label>Slug *</label><input v-model="catForm.slug" class="input" placeholder="press-on-nails"></div>
        <div class="field"><label>父分类（可选）</label>
          <select v-model="catForm.parent_id" class="input">
            <option :value="null">无（顶级分类）</option>
            <option v-for="c in catParentOptions" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field"><label>排序（小的在前）</label><input v-model.number="catForm.sort_order" class="input" type="number"></div>
          <div class="field"><label>启用状态</label>
            <select v-model.number="catForm.is_active" class="input">
              <option :value="1">启用</option><option :value="0">停用</option>
            </select>
          </div>
        </div>
      </div>
      <div style="display:flex;gap:10px;margin-top:16px">
        <button class="btn btn-secondary" style="flex:1" :disabled="catBusy" @click="catDlg = false">取消</button>
        <button class="btn btn-primary" style="flex:1" :class="{ loading: catBusy }" :disabled="catBusy" @click="saveCat">{{ catForm.id ? '保存修改' : '创建' }}</button>
      </div>
      </template>
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
  <!-- 批量导入确认（显示将导入的行数；导入中 busy 不可关闭） -->
  <ConfirmDialog :open="!!bulkPending" title="确认批量导入" :body="bulkConfirmBody"
                 confirm-text="导入" :busy="bulkBusy" @confirm="doBulkImport" @close="bulkPending = null" />
  <!-- 删除分类确认（被商品/子分类引用时后端 409，toast 翻译） -->
  <ConfirmDialog :open="catDelDlg" title="删除分类"
                 :body="'删除分类「' + (catDelTarget?.name || '') + '」？删除后不可恢复；被商品或子分类引用时将无法删除。'"
                 danger confirm-text="删除" :busy="catDelBusy" @confirm="doDelCat" @close="catDelDlg = false" />
  <!-- 恢复草稿确认 -->
  <ConfirmDialog :open="restoreDlg" title="恢复为草稿"
                 :body="'将「' + (restoreTarget?.title || '') + '」从归档恢复为草稿？恢复后前台不可见，需重新上架。'"
                 confirm-text="恢复草稿" :busy="restoreBusy" @confirm="restoreDraft" @close="restoreDlg = false" />
</template>

<style scoped>
.otab button{background:none;border:none;border-bottom:2.5px solid transparent;cursor:pointer}
.otab button.on{color:var(--plum);border-color:var(--plum)}
/* 顶栏操作组：主按钮+次要组整行可换行（全局类由 admin.css 提供，此处兜底同规则） */
.topbar-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
/* 可排序表头键盘可达：焦点环 */
th.sortable:focus-visible{outline:2px solid var(--plum);outline-offset:-2px}
/* .q-clear 已上移 admin.css（v16 公共类，样式完全一致） */
</style>
