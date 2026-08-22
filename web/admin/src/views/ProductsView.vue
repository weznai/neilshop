<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const router = useRouter()
const items = ref([])
const total = ref(0)
const pages = ref(1)
const page = ref(1)
const q = ref('')
const status = ref(null)
const loaded = ref(false)
const bulk = ref(false)
const bulkText = ref('')
const bulkResult = ref(null)

const TABS = [[null, '全部'], [1, '在售'], [0, '草稿'], [2, '归档']]
const SMeta = { 0: ['草稿', 'tag-pending'], 1: ['在售', 'tag-paid'], 2: ['归档', 'tag'] }
const BULK_ERR = { 'slug already exists': 'slug 已存在', 'category not found': '分类不存在' }
const failures = computed(() => (bulkResult.value?.results || []).filter((r) => !r.ok))

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

/* 分类筛选：后端列表无 category 参数，纯前端过滤当前页数据 */
const catFilter = ref('')

async function load() {
  /* 刷新保留旧数据，骨架只在首载出现；翻页/切 tab/搜索均经此入口，顺带重置勾选 */
  selIds.value = []
  try {
    const qs = { page: page.value, size: 50, q: q.value.trim() }
    if (status.value !== null) qs.status = status.value
    const d = await req('GET', '/api/admin/catalog/products?' + new URLSearchParams(qs))
    items.value = d.items || []
    total.value = d.total ?? 0
    pages.value = Math.max(1, Math.ceil(total.value / 50))
  } catch (e) { if (!loaded.value) items.value = []; toast('加载失败', 'error') }
  loaded.value = true
}
onMounted(() => { loadCategories(); load() })

function search() { page.value = 1; load() }
function tab(sv) { status.value = sv; page.value = 1; load() }

/* 当前页前端排序（价格/销量）：三态切换，空值恒沉底 */
const sort = reactive({ key: '', dir: 1 })
function sortBy(k) {
  if (sort.key !== k) { sort.key = k; sort.dir = 1 }
  else if (sort.dir === 1) { sort.dir = -1 }
  else { sort.key = ''; sort.dir = 1 }
}
const sortInd = (k) => (sort.key === k ? (sort.dir === 1 ? '▲' : '▼') : '')
const shownItems = computed(() => {
  const base = catFilter.value !== '' ? items.value.filter((p) => p.category_id === catFilter.value) : items.value
  if (!sort.key) return base
  const k = sort.key
  return [...base].sort((a, b) => {
    const av = a[k], bv = b[k]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (av === bv) return 0
    return (av > bv ? 1 : -1) * sort.dir
  })
})

/* ===== 批量上下架：全选作用于当前可见行（含分类过滤）；翻页/筛选后勾选重置 ===== */
const selIds = ref([])
const visIds = computed(() => shownItems.value.map((p) => p.id))
const allChecked = computed(() => visIds.value.length > 0 && visIds.value.every((id) => selIds.value.includes(id)))
function toggleAll() { selIds.value = allChecked.value ? [] : [...visIds.value] }

const batchDlg = ref(false)
const batchBusy = ref(false)
/* 循环逐个调 publish/unpublish 端点（无批量接口），进度分段 toast，结束汇总刷新 */
async function runBatch(action) {
  const ids = [...selIds.value]
  if (!ids.length || batchBusy.value) return
  batchBusy.value = true
  let ok = 0
  for (let i = 0; i < ids.length; i++) {
    try { await req('POST', `/api/admin/catalog/products/${ids[i]}/${action}`); ok++ } catch (_) {}
    if (i % 5 === 4 || i === ids.length - 1) toast(`已处理 ${i + 1}/${ids.length}`)
  }
  const fail = ids.length - ok
  toast(`批量${action === 'publish' ? '上架' : '归档'}完成：成功 ${ok}${fail ? '，失败 ' + fail : ''}`, fail ? 'error' : 'success')
  batchBusy.value = false
  batchDlg.value = false
  selIds.value = []
  load()
}

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

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
    <div style="display:flex;gap:10px">
      <input v-model="q" class="input" style="width:220px" placeholder="搜标题 / slug" @keydown.enter="search">
      <button class="btn btn-secondary" @click="search">搜索</button>
      <button class="btn btn-secondary" @click="catDlg = true">🏷 分类管理</button>
      <button class="btn btn-secondary" @click="bulk = true">📦 批量导入</button>
      <router-link to="/product-edit" class="btn btn-primary">＋ 新建商品</router-link>
    </div>
  </div>

  <div class="otab">
    <button v-for="[sv, label] in TABS" :key="String(sv)" :class="{ on: status === sv }" @click="tab(sv)">{{ label }}</button>
    <div style="margin-left:auto;align-self:center;display:flex;align-items:center;gap:6px">
      <select v-model="catFilter" class="input" style="width:auto;padding:6px 10px;font-size:12.5px" @change="selIds = []">
        <option :value="''">全部分类</option>
        <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
      <span v-if="catFilter !== ''" style="font-size:11px;color:var(--gray)">仅当前页</span>
    </div>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px" />

  <div v-else class="card tbl-wrap">
    <!-- 批量操作条：勾选任意行后出现，归档走危险确认 -->
    <div v-if="selIds.length" style="display:flex;gap:10px;align-items:center;padding:10px 12px;background:var(--rose-pale);font-size:13px;flex-wrap:wrap">
      已选 <b>{{ selIds.length }}</b> 款
      <button class="btn btn-primary btn-sm" :disabled="batchBusy" @click="runBatch('publish')">上架</button>
      <button class="btn btn-sm" style="background:var(--error);color:#fff" :disabled="batchBusy" @click="batchDlg = true">归档</button>
      <button class="btn btn-ghost btn-sm" style="margin-left:auto" :disabled="batchBusy" @click="selIds = []">取消</button>
    </div>
    <table v-if="shownItems.length" style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="width:28px"><input type="checkbox" :checked="allChecked" :disabled="!visIds.length" title="全选本页" @change="toggleAll"></th>
        <th>商品</th>
        <th class="sortable" title="点击排序（当前页）" @click="sortBy('price_min')">价格<span v-if="sortInd('price_min')" class="sort-ind">{{ sortInd('price_min') }}</span></th>
        <th>库存</th>
        <th class="sortable" title="点击排序（当前页）" @click="sortBy('sold_count')">销量<span v-if="sortInd('sold_count')" class="sort-ind">{{ sortInd('sold_count') }}</span></th>
        <th>评分</th><th>状态</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="p in shownItems" :key="p.id" style="border-top:1px solid var(--gray-light)">
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
            <span class="tag" :class="p.total_stock ? (p.low_stock_count ? 'tag-pending' : 'tag-done') : 'tag-error'">{{ p.total_stock ?? 0 }}</span>
            <div v-if="p.low_stock_count" style="font-size:11px;color:var(--error)">{{ p.low_stock_count }} 个低水位</div>
          </td>
          <td style="color:var(--gray)">{{ p.sold_count ?? 0 }}</td>
          <td style="color:var(--gray)">{{ ((p.rating_avg || 0) / 100).toFixed(1) }} <small v-if="p.rating_count">({{ p.rating_count }})</small></td>
          <td>
            <span class="tag" :class="SMeta[p.status]?.[1] || 'tag'">{{ SMeta[p.status]?.[0] || p.status }}</span>
            <span v-if="p.scheduled" class="tag tag-sched" style="margin-left:4px" title="到点自动在前台可见">定时</span>
          </td>
          <td style="text-align:right;white-space:nowrap">
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/product-edit', query: { id: p.id } }">编辑</router-link>
            <button class="btn btn-ghost btn-sm" style="margin-left:6px" title="复制商品（保存后生成新商品）" @click="router.push('/product-edit?copy=' + p.id)">⧉</button>
            <button class="btn btn-ghost btn-sm" style="margin-left:6px" @click="toggle(p)">{{ p.status === 1 ? '归档' : '上架' }}</button>
          </td>
        </tr>
      </tbody>
    </table>
    <EmptyState v-else icon="🔍" title="没有匹配商品" sub="试试其他关键词、状态或分类筛选" />
  </div>

  <Pagination v-if="loaded" :page="page" :pages="pages" :total="total" unit="款" @go="page = $event; load()" />
  <div v-if="sort.key" style="margin-top:6px;text-align:center;font-size:11.5px;color:var(--gray)">⇅ 本页内排序（仅当前页数据）</div>

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
  <!-- 批量归档确认（危险） -->
  <ConfirmDialog :open="batchDlg" title="批量归档" :body="`确认归档选中的 ${selIds.length} 款商品？归档后前台不再展示，可在「归档」tab 查看。`"
                 danger confirm-text="归档" :busy="batchBusy" @confirm="runBatch('unpublish')" @close="batchDlg = false" />
</template>

<style scoped>
td,th{padding:10px 12px}
.otab button{background:none;border:none;border-bottom:2.5px solid transparent;cursor:pointer}
.otab button.on{color:var(--plum);border-color:var(--plum)}
</style>
