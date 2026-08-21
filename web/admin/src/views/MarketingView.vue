<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const route = useRoute()
const tab = ref('discounts')
const discounts = ref([])
const rates = ref([])
const popups = ref([])
const loaded = ref(false)
const loadErr = ref(false)

/* ===== 折扣码分页（page 翻页 UI，size=20；响应含 total） ===== */
const DSC_SIZE = 20
const dscPage = ref(1)
const dscTotal = ref(0)
const dscPages = computed(() => Math.max(1, Math.ceil(dscTotal.value / DSC_SIZE)))
async function loadDiscounts() {
  const d = await req('GET', `/api/admin/ops/discounts?page=${dscPage.value}&size=${DSC_SIZE}`)
  discounts.value = d.items || []
  dscTotal.value = d.total ?? discounts.value.length
}
function dscGo(n) {
  if (n >= 1 && n <= dscPages.value) {
    dscPage.value = n
    loadDiscounts().catch((e) => toast('折扣码加载失败：' + (e.message || ''), 'error'))
  }
}

/* settings 是 k-v 列表 → 转对象（bundle 缺省回退 pricing.py 默认 15/20，避免 undefined 保存 422） */
const settings = reactive({ bundle_2_off: 15, bundle_3_off: 20 })
const BUNDLE_KEYS = { b2: 'bundle_2_off', b3: 'bundle_3_off' }

const showNew = ref(false)
/* DiscountCreateIn: type int 1-3（1=pct 2=fixed 3=ship）、value 分、starts_at 必填 */
const NEW_CODE = { code: '', type: 1, value: 20, min_subtotal: 0, max_discount: null, usage_limit: null, per_user_limit: 1, first_order_only: 0, days: 30 }
const newCode = reactive({ ...NEW_CODE })
/* 弹窗开关整体重置（对齐 newPopup 的做法，避免残留上次输入） */
function openNew() { Object.assign(newCode, NEW_CODE); showNew.value = true }
function closeNew() { Object.assign(newCode, NEW_CODE); showNew.value = false }

/* 弹窗（PopupCreateIn/PopupUpdateIn）：trigger_rules 为 JSON dict {delaySec,exitIntent,mobileOnly} */
const POPUP_SCENES = { welcome: '欢迎订阅', exit_intent: '离开挽留', newsletter: '邮件引导' }
const sceneLabel = (s) => POPUP_SCENES[s] || s
const popupDlg = ref(false)
const popupForm = reactive({ id: null, scene: 'welcome', title: '', content_md: '', coupon_code: '', delaySec: 7, exitIntent: false, mobileOnly: false, start_at: '', end_at: '', active: 0 })
/* datetime-local 值 YYYY-MM-DDTHH:mm ↔ 后端 naive ISO（YYYY-MM-DDTHH:mm:ss）直通，避免时区二次偏移 */
const dtIn = (iso) => (iso || '').slice(0, 16)
const dtOut = (v) => (v ? v + ':00' : null)

/* 深链支持：?tab=collections 等直达（审计日志行跳转使用） */
const TAB_KEYS = ['discounts', 'rates', 'bundles', 'popups', 'collections']
function initTabFromQuery() {
  const t = route.query.tab
  if (TAB_KEYS.includes(t)) {
    tab.value = t
    if (t === 'collections') { colLoaded.value = true; loadCollections() }
  }
}

async function load() {
  loaded.value = false
  loadErr.value = false
  let failed = 0
  try { await loadDiscounts() }
  catch (e) { failed++; toast('折扣码加载失败：' + (e.message || ''), 'error') }
  try { rates.value = (await req('GET', '/api/admin/trade/shipping-rates')).items || [] }
  catch (e) { failed++; toast('运费模板加载失败：' + (e.message || ''), 'error') }
  try { popups.value = (await req('GET', '/api/admin/ops/popups')).items || [] }
  catch (e) { failed++; toast('弹窗配置加载失败：' + (e.message || ''), 'error') }
  try {
    const rows = (await req('GET', '/api/admin/ops/settings')).items || []
    for (const r of rows) if (r.key in settings) settings[r.key] = r.value
  } catch (e) { failed++; toast('捆绑折扣参数加载失败：' + (e.message || ''), 'error') }
  if (failed) loadErr.value = true
  loaded.value = true
}
onMounted(() => { initTabFromQuery(); load() })

/* tab 切换：集合页懒加载（避免无谓的逐集合商品数探测请求） */
const colLoaded = ref(false)
function setTab(k) {
  tab.value = k
  if (k === 'collections' && !colLoaded.value) { colLoaded.value = true; loadCollections() }
}

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const TYPE_LABEL = { 1: (v) => `${v}% off`, 2: (v) => `${money(v)} off`, 3: () => '免邮' }
/* ends_at 为 naive UTC：按 UTC 日期比较判定「已过期」（天级，避免本地时区偏移误标） */
const todayUtc = () => new Date().toISOString().slice(0, 10)
const isExpired = (c) => !!(c.ends_at && c.ends_at.slice(0, 10) < todayUtc())

async function toggleCode(c) {
  try {
    await req('POST', `/api/admin/ops/discounts/${c.id}/toggle`)
    c.is_active = c.is_active ? 0 : 1
    toast(c.is_active ? '已启用 ✓' : '已停用 ✓', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
async function addCode() {
  if (!newCode.code) { toast('折扣码必填', 'error'); return }
  if (newCode.type === 1 && (newCode.value <= 0 || newCode.value > 100)) { toast('百分比折扣需在 1-100 之间', 'error'); return }
  try {
    await req('POST', '/api/admin/ops/discounts', {
      code: newCode.code.toUpperCase().trim(),
      type: newCode.type,
      /* 免邮码 value 恒为 0（后端校验 ge=0，且计价只看 free_shipping 标记） */
      value: newCode.type === 1 ? Math.round(newCode.value) : newCode.type === 2 ? Math.round(newCode.value * 100) : 0,
      min_subtotal: Math.round((newCode.min_subtotal || 0) * 100),
      max_discount: newCode.type === 1 && newCode.max_discount ? Math.round(newCode.max_discount * 100) : null,
      usage_limit: newCode.usage_limit ? Math.round(newCode.usage_limit) : null,
      per_user_limit: Math.round(newCode.per_user_limit || 1),
      first_order_only: newCode.first_order_only ? 1 : 0,
      starts_at: new Date().toISOString().slice(0, 19),
      ends_at: newCode.days > 0 ? new Date(Date.now() + newCode.days * 864e5).toISOString().slice(0, 19) : null,
    })
    showNew.value = false
    Object.assign(newCode, NEW_CODE)
    dscPage.value = 1
    await loadDiscounts()
    toast('折扣码已创建 ✓', 'success')
  } catch (e) { toast('创建失败：' + (JSON.stringify(e.data?.detail || e.message)).slice(0, 120), 'error') }
}

/* 一键复制折扣码（clipboard API 失败降级 execCommand，再失败提示手动复制） */
async function copyCode(c) {
  try {
    await navigator.clipboard.writeText(c.code)
    toast('已复制 ' + c.code + ' ✓', 'success')
  } catch (_) {
    try {
      const ta = document.createElement('textarea')
      ta.value = c.code
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      toast('已复制 ' + c.code + ' ✓', 'success')
    } catch (_) { toast('复制失败，请手动复制 ' + c.code, 'error') }
  }
}

/* 编辑折扣码（PUT DiscountUpdateIn 全可选：value/门槛/封顶/次数/有效期） */
const editDlg = ref(false)
const editCode = reactive({ id: null, code: '', type: 1, value: 20, min_subtotal: 0, max_discount: null, usage_limit: null, per_user_limit: 1, starts_at: '', ends_at: '' })
function editDiscount(c) {
  Object.assign(editCode, {
    id: c.id,
    code: c.code,
    type: c.type,
    value: c.type === 2 ? (c.value || 0) / 100 : (c.value || 0),
    min_subtotal: (c.min_subtotal || 0) / 100,
    max_discount: c.max_discount ? c.max_discount / 100 : null,
    usage_limit: c.usage_limit ?? null,
    per_user_limit: c.per_user_limit ?? 1,
    starts_at: dtIn(c.starts_at),
    ends_at: dtIn(c.ends_at),
  })
  editDlg.value = true
}
async function saveEdit() {
  if (editCode.type === 1 && (editCode.value <= 0 || editCode.value > 100)) { toast('百分比折扣需在 1-100 之间', 'error'); return }
  try {
    await req('PUT', '/api/admin/ops/discounts/' + editCode.id, {
      value: editCode.type === 1 ? Math.round(editCode.value) : editCode.type === 2 ? Math.round(editCode.value * 100) : 0,
      min_subtotal: Math.round((editCode.min_subtotal || 0) * 100),
      max_discount: editCode.type === 1 && editCode.max_discount ? Math.round(editCode.max_discount * 100) : null,
      usage_limit: editCode.usage_limit ? Math.round(editCode.usage_limit) : null,
      per_user_limit: Math.round(editCode.per_user_limit || 1),
      starts_at: dtOut(editCode.starts_at),
      ends_at: dtOut(editCode.ends_at),
    })
    editDlg.value = false
    await loadDiscounts()
    toast('折扣码已保存 ✓', 'success')
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}

/* ===== 弹窗管理（GET/POST /api/admin/ops/popups + PUT/{id} + /{id}/toggle，stats 保留不清零） ===== */
function newPopup() {
  Object.assign(popupForm, { id: null, scene: 'welcome', title: '', content_md: '', coupon_code: '', delaySec: 7, exitIntent: false, mobileOnly: false, start_at: '', end_at: '', active: 0 })
  popupDlg.value = true
}
function editPopup(p) {
  Object.assign(popupForm, {
    id: p.id,
    scene: p.scene,
    title: p.title || '',
    content_md: p.content_md || '',
    coupon_code: p.coupon_code || '',
    delaySec: p.trigger_rules?.delaySec ?? 7,
    exitIntent: !!p.trigger_rules?.exitIntent,
    mobileOnly: !!p.trigger_rules?.mobileOnly,
    start_at: dtIn(p.start_at),
    end_at: dtIn(p.end_at),
    active: p.active ? 1 : 0,
  })
  popupDlg.value = true
}
async function savePopup() {
  if (!popupForm.title.trim()) { toast('标题必填', 'error'); return }
  const body = {
    scene: popupForm.scene.trim().toLowerCase(),
    title: popupForm.title.trim(),
    content_md: popupForm.content_md || null,
    coupon_code: popupForm.coupon_code ? popupForm.coupon_code.trim().toUpperCase() : null,
    trigger_rules: { delaySec: Math.round(popupForm.delaySec || 0), exitIntent: !!popupForm.exitIntent, mobileOnly: !!popupForm.mobileOnly },
    start_at: dtOut(popupForm.start_at),
    end_at: dtOut(popupForm.end_at),
    active: popupForm.active ? 1 : 0,
  }
  try {
    if (popupForm.id) await req('PUT', '/api/admin/ops/popups/' + popupForm.id, body)
    else await req('POST', '/api/admin/ops/popups', body)
    popupDlg.value = false
    popups.value = (await req('GET', '/api/admin/ops/popups')).items || []
    toast(popupForm.id ? '弹窗已保存 ✓' : '弹窗已创建 ✓', 'success')
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}
async function togglePopup(p) {
  try {
    await req('POST', `/api/admin/ops/popups/${p.id}/toggle`)
    p.active = p.active ? 0 : 1
    toast(p.active ? '已启用 ✓' : '已停用 ✓', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
async function saveBundle(key) {
  try {
    await req('PUT', '/api/admin/ops/settings', { key: BUNDLE_KEYS[key], value: Number(settings[BUNDLE_KEYS[key]]) || 0 })
    toast('已保存（结算即时生效）✓', 'success')
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}

/* ===== 运费模板管理（后端：GET/POST + PUT price/free_over/eta/active） ===== */
async function toggleRate(r) {
  try {
    await req('PUT', `/api/admin/trade/shipping-rates/${r.id}`, { active: !r.active })
    r.active = !r.active
    toast(r.active ? '已启用 ✓' : '已停用 ✓', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}

const rateDlg = ref(false)
const rateForm = reactive({ id: null, dest_country: 'US', carrier: 'usps', method: 'standard', price: 499, free_over: null, eta_min_days: 3, eta_max_days: 7, max_weight_g: 500 })
function newRate() {
  Object.assign(rateForm, { id: null, dest_country: 'US', carrier: 'usps', method: 'standard', price: 499, free_over: null, eta_min_days: 3, eta_max_days: 7, max_weight_g: 500 })
  rateDlg.value = true
}
function editRate(r) {
  Object.assign(rateForm, {
    id: r.id, dest_country: r.dest_country, carrier: r.carrier, method: r.method,
    price: r.price, free_over: r.free_over, eta_min_days: r.eta_min_days, eta_max_days: r.eta_max_days,
  })
  rateDlg.value = true
}
async function saveRate() {
  if (rateForm.eta_max_days < rateForm.eta_min_days) { toast('最大时效不能小于最小时效', 'error'); return }
  try {
    if (rateForm.id) {
      await req('PUT', `/api/admin/trade/shipping-rates/${rateForm.id}`, {
        price: Math.round(rateForm.price), free_over: rateForm.free_over ? Math.round(rateForm.free_over) : null,
        eta_min_days: rateForm.eta_min_days | 0, eta_max_days: rateForm.eta_max_days | 0,
      })
      toast('运费模板已保存 ✓', 'success')
    } else {
      await req('POST', '/api/admin/trade/shipping-rates', {
        dest_country: rateForm.dest_country.trim().toUpperCase(), carrier: rateForm.carrier.trim().toLowerCase(),
        method: rateForm.method, price: Math.round(rateForm.price),
        free_over: rateForm.free_over ? Math.round(rateForm.free_over) : null,
        eta_min_days: rateForm.eta_min_days | 0, eta_max_days: rateForm.eta_max_days | 0,
        max_weight_g: rateForm.max_weight_g | 0 || 500,
      })
      toast('运费模板已创建 ✓', 'success')
    }
    rateDlg.value = false
    rates.value = (await req('GET', '/api/admin/trade/shipping-rates')).items || []
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}

/* ===== 集合页管理（GET/POST /api/admin/catalog/collections + PUT/DELETE /{id} + GET/PUT /{id}/products） ===== */
const collections = ref([])
const colErr = ref(false)
/* 商品数：逐集合 GET /collections/{id}/products 统计（失败显示 —） */
const colCounts = reactive({})
async function loadCollections() {
  colErr.value = false
  try {
    collections.value = (await req('GET', '/api/admin/catalog/collections')).items || []
  } catch (e) {
    colErr.value = true
    collections.value = []
    toast('集合列表加载失败：' + (e.message || ''), 'error')
    return
  }
  for (const c of collections.value) {
    colCounts[c.id] = null
    req('GET', `/api/admin/catalog/collections/${c.id}/products`)
      .then((d) => { colCounts[c.id] = (d.items || []).length })
      .catch(() => { colCounts[c.id] = null })
  }
}

/* 新建集合（CollectionCreateIn{slug,title,rule_json}；banner_image 可选字段契约补充中，创建后也可在「编辑」中维护） */
const colDlg = ref(false)
const colForm = reactive({ slug: '', title: '', banner: '', ruleStr: '{}' })
function newCollection() {
  Object.assign(colForm, { slug: '', title: '', banner: '', ruleStr: '{}' })
  colDlg.value = true
}
async function createCollection() {
  const slug = colForm.slug.trim().toLowerCase()
  if (!slug || !colForm.title.trim()) { toast('slug 与标题必填', 'error'); return }
  let rule = {}
  const s = colForm.ruleStr.trim()
  if (s) {
    try { rule = JSON.parse(s) } catch (_) { toast('rule_json 不是合法 JSON', 'error'); return }
    if (rule === null || typeof rule !== 'object' || Array.isArray(rule)) {
      toast('rule_json 需为 JSON 对象（如 {} 或 {"category":"new"}）', 'error'); return
    }
  }
  try {
    await req('POST', '/api/admin/catalog/collections', {
      slug,
      title: colForm.title.trim(),
      rule_json: rule,
      ...(colForm.banner.trim() ? { banner_image: colForm.banner.trim() } : {}),
    })
    toast('集合已创建 ✓', 'success')
    colDlg.value = false
    loadCollections()
  } catch (e) { toast('创建失败：' + (e.data?.detail || e.message), 'error') }
}

/* 编辑集合 meta（CollectionUpdateIn 全可选：title/banner_image/sort_order，本弹窗只传这三项） */
const colEditDlg = ref(false)
const colEdit = reactive({ id: null, title: '', banner: '', sort_order: 0 })
function editCollection(c) {
  Object.assign(colEdit, { id: c.id, title: c.title || '', banner: c.banner_image || '', sort_order: c.sort_order ?? 0 })
  colEditDlg.value = true
}
async function saveColEdit() {
  if (!colEdit.title.trim()) { toast('标题必填', 'error'); return }
  try {
    await req('PUT', `/api/admin/catalog/collections/${colEdit.id}`, {
      title: colEdit.title.trim(),
      /* 空串 → null：显式清空 banner */
      banner_image: colEdit.banner.trim() || null,
      sort_order: Math.round(Number(colEdit.sort_order) || 0),
    })
    toast('集合已保存 ✓', 'success')
    colEditDlg.value = false
    loadCollections()
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}

/* 配商品：打开先回显现状（GET /{id}/products），搜索勾选后 PUT 全量替换 */
const pickDlg = ref(false)
const pickCol = ref(null)
const pickQ = ref('')
const pickOptions = ref([])     /* 搜索结果（最多 50 条） */
const pickTotal = ref(0)        /* 搜索匹配总数（>50 时提示缩小范围） */
const picked = ref([])          /* 已选 [{product_id, title}]，顺序即 sort_order */
const pickOrigN = ref(0)        /* 打开时的现有件数（confirm 文案用） */
async function openPick(c) {
  pickCol.value = c
  pickDlg.value = true
  pickQ.value = ''
  picked.value = []
  pickOrigN.value = 0
  try {
    const d = await req('GET', `/api/admin/catalog/collections/${c.id}/products`)
    picked.value = (d.items || []).map((it) => ({ product_id: it.product_id, title: it.product?.title || ('商品 #' + it.product_id) }))
    pickOrigN.value = picked.value.length
  } catch (e) {
    toast('现有商品回显失败：' + (e.message || ''), 'error')
  }
  searchProducts()
}
async function searchProducts() {
  try {
    const qs = new URLSearchParams({ page: 1, size: 50 })
    if (pickQ.value.trim()) qs.set('q', pickQ.value.trim())
    const d = await req('GET', '/api/admin/catalog/products?' + qs)
    pickOptions.value = d.items || []
    pickTotal.value = d.total ?? pickOptions.value.length
  } catch (e) {
    pickOptions.value = []
    pickTotal.value = 0
    toast('商品搜索失败：' + (e.message || ''), 'error')
  }
}
const isPicked = (id) => picked.value.some((x) => x.product_id === id)
function togglePick(p) {
  const i = picked.value.findIndex((x) => x.product_id === p.id)
  if (i > -1) picked.value.splice(i, 1)
  else picked.value.push({ product_id: p.id, title: p.title })
}
async function savePick() {
  const c = pickCol.value
  if (!c) return
  const n = picked.value.length
  const msg = pickOrigN.value > 0
    ? `保存将替换现有 ${pickOrigN.value} 件商品为 ${n} 件（全量替换），确认继续？`
    : `保存将把 ${n} 件商品全量写入该集合（覆盖现有配置），确认继续？`
  if (!confirm(msg)) return
  try {
    await req('PUT', `/api/admin/catalog/collections/${c.id}/products`, {
      products: picked.value.map((x, i) => ({ product_id: x.product_id, sort_order: i })),
    })
    toast('集合商品已保存 ✓', 'success')
    pickDlg.value = false
    /* 刷新集合商品数（保存的即最新全量） */
    colCounts[c.id] = n
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
}

/* 启停（PUT /collections/{id} CollectionUpdateIn.is_active） */
async function toggleCollection(c) {
  try {
    await req('PUT', `/api/admin/catalog/collections/${c.id}`, { is_active: c.is_active ? 0 : 1 })
    c.is_active = c.is_active ? 0 : 1
    toast(c.is_active ? '已启用 ✓' : '已停用 ✓', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
async function delCollection(c) {
  if (!confirm(`删除集合「${c.title}」？关联的 ${colCounts[c.id] ?? '?'} 件商品配置将一并移除，不可恢复。`)) return
  try {
    await req('DELETE', `/api/admin/catalog/collections/${c.id}`)
    toast('已删除', 'success')
    loadCollections()
  } catch (e) { toast('删除失败：' + (e.data?.detail || e.message), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">营销工具</h1>
      <span style="font-size:12.5px;color:var(--gray)">折扣码 / 运费模板 / 捆绑折扣 / 弹窗 / 集合</span>
    </div>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button
      v-for="[k, label] in [['discounts', '折扣码'], ['rates', '运费模板'], ['bundles', '捆绑折扣'], ['popups', '弹窗'], ['collections', '集合页']]"
      :key="k"
      style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer"
      :style="{ color: tab === k ? 'var(--plum)' : 'var(--gray)', borderBottom: tab === k ? '2.5px solid var(--plum)' : '2.5px solid transparent' }"
      @click="setTab(k)"
    >{{ label }}</button>
  </div>

  <!-- 折扣码 -->
  <template v-if="tab === 'discounts'">
    <div class="card" style="padding:16px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:13.5px;color:var(--gray)">共 {{ dscTotal }} 个码 · 当前页启用 {{ discounts.filter((c) => c.is_active).length }}<span v-if="discounts.some((c) => isExpired(c))"> · 当前页 {{ discounts.filter((c) => isExpired(c)).length }} 个已过期</span></span>
      <button class="btn btn-primary btn-sm" @click="openNew">＋ 新建折扣码</button>
    </div>
    <div v-if="loadErr" style="width:100%;display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:var(--pale-error);border:1px solid var(--error);border-radius:10px;font-size:12.5px;color:var(--error)">
      <span>⚠️ 部分数据加载失败，展示的可能不是最新配置</span>
      <button class="btn btn-secondary btn-sm" @click="load">重试</button>
    </div>
    <div v-if="!loaded" class="card skeleton" style="min-height:220px"></div>
    <div v-else class="card tbl-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">码</th><th>规则</th><th>门槛/上限</th><th>已用</th><th>有效期</th><th>状态</th><th style="text-align:right">操作</th></tr></thead>
        <tbody>
          <tr v-for="c in discounts" :key="c.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:11px 10px;white-space:nowrap"><b>{{ c.code }}</b>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px;padding:2px 7px" title="复制折扣码" @click="copyCode(c)">⧉</button>
            </td>
            <td>{{ (TYPE_LABEL[c.type] || (() => '—'))(c.value) }}</td>
            <td style="color:var(--gray)">
              {{ c.min_subtotal ? '满 ' + money(c.min_subtotal) : '无门槛' }}
              <span v-if="c.max_discount">· 封顶 {{ money(c.max_discount) }}</span>
              <span v-if="c.per_user_limit > 1">· 限{{ c.per_user_limit }}次/人</span>
              <span v-if="c.first_order_only">· 仅首单</span>
            </td>
            <td style="color:var(--gray)">{{ c.used_count ?? 0 }}<span v-if="c.usage_limit">/{{ c.usage_limit }}</span></td>
            <td style="color:var(--gray);font-size:12px">{{ (c.starts_at || '').slice(0, 10) }} ~ {{ c.ends_at ? c.ends_at.slice(0, 10) : '∞' }}</td>
            <td style="white-space:nowrap">
              <span v-if="c.is_active && isExpired(c)" class="tag tag-error">已过期</span>
              <span v-else class="tag" :class="c.is_active ? 'tag-paid' : 'tag-pending'">{{ c.is_active ? '启用' : '停用' }}</span>
            </td>
            <td style="text-align:right;white-space:nowrap">
              <button class="btn btn-secondary btn-sm" @click="editDiscount(c)">编辑</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="toggleCode(c)">{{ c.is_active ? '停用' : '启用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="loaded && !discounts.length" icon="🏷️" title="暂无折扣码" sub="点击右上角「新建折扣码」创建第一个" />
      <Pagination embed :page="dscPage" :pages="dscPages" :total="dscTotal" unit="个" @go="dscGo" />
    </div>

    <div v-if="showNew" class="modal open" @click.self="closeNew">
      <div class="modal-box" style="max-width:520px">
        <button class="modal-x" @click="closeNew">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">➕ 新建折扣码</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field"><label>码</label><input v-model="newCode.code" class="input" placeholder="SUMMER30" style="text-transform:uppercase"></div>
          <div class="field"><label>类型</label>
            <select v-model.number="newCode.type" class="input">
              <option :value="1">百分比（%）</option><option :value="2">固定减免（$）</option><option :value="3">免邮</option>
            </select>
          </div>
          <div v-if="newCode.type !== 3" class="field"><label>{{ newCode.type === 1 ? '折扣 %' : '减免 $' }}</label>
            <input v-model.number="newCode.value" class="input" type="number"></div>
          <div class="field"><label>门槛 $（0=无）</label><input v-model.number="newCode.min_subtotal" class="input" type="number"></div>
          <div v-if="newCode.type === 1" class="field"><label>封顶 $（可选，%码适用）</label><input v-model.number="newCode.max_discount" class="input" type="number"></div>
          <div class="field"><label>有效天数（0=永久）</label><input v-model.number="newCode.days" class="input" type="number"></div>
          <div class="field"><label>总次数（空=不限）</label><input v-model.number="newCode.usage_limit" class="input" type="number" min="1"></div>
          <div class="field"><label>每人限用次数</label><input v-model.number="newCode.per_user_limit" class="input" type="number" min="1"></div>
        </div>
        <label style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer;margin-top:10px">
          <input v-model="newCode.first_order_only" type="checkbox" style="width:16px;height:16px"> 仅限首单使用
        </label>
        <button class="btn btn-primary btn-block" style="margin-top:14px" @click="addCode">创建</button>
      </div>
    </div>

    <!-- 编辑折扣码（value/门槛/封顶/次数/有效期；code 与启停走行内/独立入口） -->
    <div v-if="editDlg" class="modal open" @click.self="editDlg = false">
      <div class="modal-box" style="max-width:520px">
        <button class="modal-x" @click="editDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">✏️ 编辑折扣码 {{ editCode.code }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">类型不可更改；金额单位为美元，保存时换算为美分。</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div v-if="editCode.type !== 3" class="field"><label>{{ editCode.type === 1 ? '折扣 %' : '减免 $' }}</label>
            <input v-model.number="editCode.value" class="input" type="number"></div>
          <div class="field"><label>门槛 $（0=无）</label><input v-model.number="editCode.min_subtotal" class="input" type="number"></div>
          <div v-if="editCode.type === 1" class="field"><label>封顶 $（可选）</label><input v-model.number="editCode.max_discount" class="input" type="number"></div>
          <div class="field"><label>总次数（空=不限）</label><input v-model.number="editCode.usage_limit" class="input" type="number" min="1"></div>
          <div class="field"><label>每人限用次数</label><input v-model.number="editCode.per_user_limit" class="input" type="number" min="1"></div>
          <div class="field"><label>开始时间 (UTC)</label><input v-model="editCode.starts_at" class="input" type="datetime-local"></div>
          <div class="field"><label>结束时间 (UTC)（空=永久）</label><input v-model="editCode.ends_at" class="input" type="datetime-local"></div>
        </div>
        <button class="btn btn-primary btn-block" style="margin-top:14px" @click="saveEdit">保存</button>
      </div>
    </div>
  </template>

  <!-- 运费模板 -->
  <template v-else-if="tab === 'rates'">
    <div class="card" style="padding:16px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:13.5px;color:var(--gray)">共 {{ rates.length }} 条 · 启用 {{ rates.filter((r) => r.active).length }} · 结算按「国家→方式」取启用模板</span>
      <button class="btn btn-primary btn-sm" @click="newRate">＋ 新建模板</button>
    </div>
    <div v-if="!loaded" class="card skeleton" style="min-height:220px"></div>
    <div v-else class="card tbl-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">目的地</th><th>承运</th><th>方式</th><th>运费</th><th>免邮门槛</th><th>时效（天）</th><th>限重(g)</th><th>状态</th><th style="text-align:right">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in rates" :key="r.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:11px 10px"><b>{{ r.dest_country || '*' }}</b></td>
            <td>{{ r.carrier }}</td>
            <td>{{ r.method === 'express' ? '快递' : '标准' }}</td>
            <td><b>{{ money(r.price) }}</b></td>
            <td style="color:var(--gray)">{{ r.free_over ? money(r.free_over) : '—' }}</td>
            <td style="color:var(--gray)">{{ r.eta_min_days ?? '—' }}–{{ r.eta_max_days ?? '—' }}</td>
            <td style="color:var(--gray)">{{ r.max_weight_g ?? '—' }}</td>
            <td><span class="tag" :class="r.active ? 'tag-paid' : 'tag-pending'">{{ r.active ? '启用' : '停用' }}</span></td>
            <td style="text-align:right;white-space:nowrap">
              <button class="btn btn-secondary btn-sm" @click="editRate(r)">编辑</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="toggleRate(r)">{{ r.active ? '停用' : '启用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="loaded && !rates.length" icon="🚚" title="暂无运费模板" sub="结算将使用 settings 默认运费" />
    </div>

    <div v-if="rateDlg" class="modal open" @click.self="rateDlg = false">
      <div class="modal-box" style="max-width:520px">
        <button class="modal-x" @click="rateDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">{{ rateForm.id ? '编辑运费模板 #' + rateForm.id : '新建运费模板' }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">金额单位为美分（分），时效为天。</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div v-if="!rateForm.id" class="field"><label>目的地（国家码）</label>
            <select v-model="rateForm.dest_country" class="input">
              <option v-for="c in ['US', 'CA', 'GB', 'AU', 'DE', 'FR', 'JP']" :key="c">{{ c }}</option>
            </select>
          </div>
          <div v-if="!rateForm.id" class="field"><label>承运商</label>
            <select v-model="rateForm.carrier" class="input">
              <option>usps</option><option>ups</option><option>fedex</option><option>dhl</option>
            </select>
          </div>
          <div v-if="!rateForm.id" class="field"><label>方式</label>
            <select v-model="rateForm.method" class="input">
              <option value="standard">标准</option><option value="express">快递</option>
            </select>
          </div>
          <div class="field"><label>运费（分）</label><input v-model.number="rateForm.price" class="input" type="number"></div>
          <div class="field"><label>免邮门槛（分，可空）</label><input v-model.number="rateForm.free_over" class="input" type="number"></div>
          <div class="field"><label>最小时效（天）</label><input v-model.number="rateForm.eta_min_days" class="input" type="number"></div>
          <div class="field"><label>最大时效（天）</label><input v-model.number="rateForm.eta_max_days" class="input" type="number"></div>
          <div v-if="!rateForm.id" class="field"><label>限重（g）</label><input v-model.number="rateForm.max_weight_g" class="input" type="number"></div>
        </div>
        <button class="btn btn-primary btn-block" style="margin-top:14px" @click="saveRate">保存</button>
      </div>
    </div>
  </template>

  <!-- 捆绑折扣 -->
  <div v-else-if="tab === 'bundles'" class="card" style="padding:20px;max-width:460px">
    <h3 style="font-size:14.5px;margin-bottom:6px">🎁 捆绑折扣（结算即时生效）</h3>
    <p style="font-size:12.5px;color:var(--gray);margin-bottom:14px">两件 / 三件及以上的购物车整单折扣比例（%，0 = 关闭该档）。</p>
    <div class="field"><label>买 2 件折扣 %</label>
      <div style="display:flex;gap:8px">
        <input v-model.number="settings.bundle_2_off" class="input" type="number" min="0" max="50">
        <button class="btn btn-secondary" @click="saveBundle('b2')">保存</button>
      </div>
    </div>
    <div class="field"><label>买 3+ 件折扣 %</label>
      <div style="display:flex;gap:8px">
        <input v-model.number="settings.bundle_3_off" class="input" type="number" min="0" max="50">
        <button class="btn btn-secondary" @click="saveBundle('b3')">保存</button>
      </div>
    </div>
  </div>

  <!-- 弹窗（PopupConfig 完整 CRUD + 启停；前台按 scene 拉取启用中的最新一条） -->
  <div v-else-if="tab === 'popups'">
    <div class="card" style="padding:16px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:13.5px;color:var(--gray)">共 {{ popups.length }} 个 · 启用 {{ popups.filter((p) => p.active).length }} · 前台同场景取最新启用且在有效期内的一个</span>
      <button class="btn btn-primary btn-sm" @click="newPopup">＋ 新建弹窗</button>
    </div>
    <div v-if="!loaded" class="card skeleton" style="min-height:220px"></div>
    <div v-else class="card tbl-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">场景</th><th>标题 / 券码</th><th>触发规则</th><th>有效期</th><th>曝光/转化</th><th>状态</th><th style="text-align:right">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="p in popups" :key="p.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:11px 10px;white-space:nowrap"><b>{{ sceneLabel(p.scene) }}</b><span style="color:var(--gray);font-size:11px;margin-left:4px">{{ p.scene }}</span></td>
            <td style="min-width:180px">
              <b>{{ p.title }}</b>
              <div v-if="p.coupon_code" style="color:var(--plum);font-size:12px;margin-top:2px">🎫 {{ p.coupon_code }}</div>
            </td>
            <td style="color:var(--gray);font-size:12px">
              {{ p.trigger_rules?.delaySec ?? '—' }}s 延迟<span v-if="p.trigger_rules?.exitIntent"> · 离开触发</span><span v-if="p.trigger_rules?.mobileOnly"> · 仅移动端</span>
            </td>
            <td style="color:var(--gray);font-size:12px">{{ p.start_at ? p.start_at.slice(0, 10) : '—' }} ~ {{ p.end_at ? p.end_at.slice(0, 10) : '长期' }}</td>
            <td style="color:var(--gray);font-size:12px">{{ p.stats_shown ?? 0 }} / {{ p.stats_converted ?? 0 }}<span v-if="p.stats_shown">（{{ Math.round((p.stats_converted || 0) * 100 / p.stats_shown) }}%）</span></td>
            <td style="white-space:nowrap">
              <span v-if="p.active && p.end_at && p.end_at.slice(0, 10) < todayUtc()" class="tag tag-error">已到期</span>
              <span v-else class="tag" :class="p.active ? 'tag-paid' : 'tag-pending'">{{ p.active ? '启用' : '停用' }}</span>
            </td>
            <td style="text-align:right;white-space:nowrap">
              <button class="btn btn-secondary btn-sm" @click="editPopup(p)">编辑</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="togglePopup(p)">{{ p.active ? '停用' : '启用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="loaded && !popups.length" icon="🪟" title="暂无弹窗配置" sub="点击右上角「新建弹窗」创建" />
    </div>

    <!-- 弹窗编辑（scene/title/content_md/coupon_code/trigger_rules/有效期/active） -->
    <div v-if="popupDlg" class="modal open" @click.self="popupDlg = false">
      <div class="modal-box" style="max-width:560px">
        <button class="modal-x" @click="popupDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">{{ popupForm.id ? '✏️ 编辑弹窗 #' + popupForm.id : '🪟 新建弹窗' }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">前台 GET /api/promo/popup?scene= 按「启用中 + 有效期内 + 最新」取一个展示。</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field"><label>场景 scene</label>
            <input v-model="popupForm.scene" class="input" list="popup-scenes" placeholder="welcome">
            <datalist id="popup-scenes">
              <option v-for="(name, s) in POPUP_SCENES" :key="s" :value="s">{{ name }}</option>
            </datalist>
          </div>
          <div class="field"><label>券码（可选，会展示给用户）</label><input v-model="popupForm.coupon_code" class="input" placeholder="WELCOME20" style="text-transform:uppercase"></div>
          <div class="field" style="grid-column:1/-1"><label>标题 *</label><input v-model="popupForm.title" class="input" placeholder="Get 20% off your first set"></div>
          <div class="field" style="grid-column:1/-1"><label>内容（Markdown）</label><textarea v-model="popupForm.content_md" class="input" rows="3"></textarea></div>
          <div class="field"><label>延迟秒数</label><input v-model.number="popupForm.delaySec" class="input" type="number" min="0"></div>
          <div class="field"><label>有效期开始 (UTC)（空=立即）</label><input v-model="popupForm.start_at" class="input" type="datetime-local"></div>
          <div class="field"><label>有效期结束 (UTC)（空=长期）</label><input v-model="popupForm.end_at" class="input" type="datetime-local"></div>
        </div>
        <div style="display:flex;gap:18px;flex-wrap:wrap;margin-top:10px;font-size:13.5px">
          <label style="display:flex;gap:8px;align-items:center;cursor:pointer">
            <input v-model="popupForm.exitIntent" type="checkbox" style="width:15px;height:15px"> 鼠标离开页面时触发
          </label>
          <label style="display:flex;gap:8px;align-items:center;cursor:pointer">
            <input v-model="popupForm.mobileOnly" type="checkbox" style="width:15px;height:15px"> 仅移动端展示
          </label>
          <label style="display:flex;gap:8px;align-items:center;cursor:pointer">
            <input v-model.number="popupForm.active" type="checkbox" :true-value="1" :false-value="0" style="width:15px;height:15px"> 立即启用
          </label>
        </div>
        <button class="btn btn-primary btn-block" style="margin-top:14px" @click="savePopup">保存</button>
      </div>
    </div>
  </div>

  <!-- 集合页（GET/POST /api/admin/catalog/collections + PUT/DELETE /{id} + GET/PUT /{id}/products） -->
  <div v-else>
    <div class="card" style="padding:16px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:13.5px;color:var(--gray)">共 {{ collections.length }} 个集合 · 启用 {{ collections.filter((c) => c.is_active).length }} · 商品数为手动配置的固定商品</span>
      <button class="btn btn-primary btn-sm" @click="newCollection">＋ 新建集合</button>
    </div>
    <EmptyState v-if="colErr" icon="⚠️" title="集合列表加载失败" sub="服务端可能未启动或端点暂不可用">
      <template #action><button class="btn btn-secondary btn-sm" @click="loadCollections">重试</button></template>
    </EmptyState>
    <div v-else class="card tbl-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">集合</th><th>slug</th><th>规则</th><th>商品数</th><th>状态</th><th style="text-align:right">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="c in collections" :key="c.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:11px 10px">
              <b>{{ c.title }}</b>
              <div v-if="c.banner_image" style="font-size:11.5px;color:var(--gray);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:220px" :title="c.banner_image">🖼 {{ c.banner_image }}</div>
            </td>
            <td><code style="font-size:12px">{{ c.slug }}</code></td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--gray);font-size:12px" :title="JSON.stringify(c.rule_json || {})">{{ JSON.stringify(c.rule_json || {}) }}</td>
            <td>
              <b v-if="colCounts[c.id] != null">{{ colCounts[c.id] }}</b>
              <span v-else style="color:var(--gray)" title="商品数加载失败">—</span>
            </td>
            <td><span class="tag" :class="c.is_active ? 'tag-paid' : 'tag-pending'">{{ c.is_active ? '启用' : '停用' }}</span></td>
            <td style="text-align:right;white-space:nowrap">
              <button class="btn btn-secondary btn-sm" @click="openPick(c)">配商品</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="editCollection(c)">编辑</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="toggleCollection(c)">{{ c.is_active ? '停用' : '启用' }}</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px;color:var(--error)" @click="delCollection(c)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="colLoaded && !collections.length" icon="🗂️" title="暂无集合" sub="点击右上角「新建集合」创建第一个商品集合页" />
    </div>

    <!-- 新建集合弹窗（slug/title 必填；rule_json 需合法 JSON 对象） -->
    <div v-if="colDlg" class="modal open" @click.self="colDlg = false">
      <div class="modal-box" style="max-width:520px">
        <button class="modal-x" @click="colDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">🗂️ 新建集合</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">集合为固定商品列表页；rule_json 高级规则可选（留空 = {}）。</p>
        <div style="display:grid;gap:12px">
          <div class="field"><label>Slug（小写，唯一）</label>
            <input v-model="colForm.slug" class="input" placeholder="summer-picks" style="text-transform:lowercase"></div>
          <div class="field"><label>标题 *</label><input v-model="colForm.title" class="input" placeholder="夏日精选"></div>
          <div class="field"><label>Banner 图 URL（可选）</label>
            <input v-model="colForm.banner" class="input" placeholder="/static/banners/summer.jpg">
            <p style="font-size:11px;color:var(--gray);margin-top:4px">若创建时未生效，可在创建后的「编辑」中补充保存。</p>
          </div>
          <div class="field"><label>高级规则 rule_json（JSON 对象，可选）</label>
            <textarea v-model="colForm.ruleStr" class="input" rows="3" placeholder='{} 或 {"category":"new"}'></textarea>
          </div>
        </div>
        <button class="btn btn-primary btn-block" style="margin-top:14px" @click="createCollection">创建</button>
      </div>
    </div>

    <!-- 编辑集合弹窗（PUT /collections/{id}：title/banner_image/sort_order） -->
    <div v-if="colEditDlg" class="modal open" @click.self="colEditDlg = false">
      <div class="modal-box" style="max-width:520px">
        <button class="modal-x" @click="colEditDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">✏️ 编辑集合 #{{ colEdit.id }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">slug 与商品组成请在「配商品」/删除重建中维护。</p>
        <div style="display:grid;gap:12px">
          <div class="field"><label>标题 *</label><input v-model="colEdit.title" class="input"></div>
          <div class="field"><label>Banner 图 URL（清空 = 移除）</label><input v-model="colEdit.banner" class="input" placeholder="/static/banners/summer.jpg"></div>
          <div class="field"><label>排序权重（小者靠前）</label><input v-model.number="colEdit.sort_order" class="input" type="number"></div>
        </div>
        <button class="btn btn-primary btn-block" style="margin-top:14px" @click="saveColEdit">保存</button>
      </div>
    </div>

    <!-- 配商品弹窗（回显现状 → 搜索勾选 → PUT 全量替换） -->
    <div v-if="pickDlg" class="modal open" @click.self="pickDlg = false">
      <div class="modal-box" style="max-width:560px">
        <button class="modal-x" @click="pickDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:4px">🛒 配商品 · {{ pickCol?.title }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">
          已选 <b style="color:var(--plum)">{{ picked.length }}</b> 件（勾选顺序即展示排序）；保存将<b>全量替换</b>现有配置。
        </p>
        <div style="display:flex;gap:8px;margin-bottom:10px">
          <input v-model="pickQ" class="input" placeholder="搜商品标题 / slug" @keydown.enter="searchProducts">
          <button class="btn btn-secondary" style="flex:none" @click="searchProducts">搜索</button>
        </div>
        <div style="max-height:240px;overflow-y:auto;border:1px solid var(--gray-light);border-radius:10px;padding:6px 10px;margin-bottom:12px">
          <label v-for="p in pickOptions" :key="p.id" style="display:flex;gap:10px;align-items:center;padding:7px 2px;border-bottom:1px solid var(--gray-light);font-size:13px;cursor:pointer">
            <input type="checkbox" :checked="isPicked(p.id)" style="width:15px;height:15px;flex:none" @change="togglePick(p)">
            <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ p.title }}</span>
            <span style="color:var(--gray);font-size:11.5px;flex:none">{{ p.slug }}</span>
          </label>
          <div v-if="!pickOptions.length" style="text-align:center;color:var(--gray);font-size:12.5px;padding:16px 0">无搜索结果（输入关键词回车搜索）</div>
        </div>
        <!-- 命中超过 50 条：截断提示 + 引导缩小范围 -->
        <p v-if="pickTotal > pickOptions.length" style="font-size:11.5px;color:var(--warn);margin:-4px 0 10px">
          {{ pickQ.trim()
            ? `匹配 ${pickTotal} 件，仅显示前 ${pickOptions.length} 条——请输入更精确的关键词缩小范围`
            : `共 ${pickTotal} 件商品，仅显示前 ${pickOptions.length} 条——清空关键词直接浏览，或输入关键词筛选` }}
        </p>
        <!-- 已选清单（可移除，顺序即 sort_order） -->
        <div v-if="picked.length" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">
          <span v-for="(x, i) in picked" :key="x.product_id" class="tag tag-paid" style="cursor:pointer;font-size:11.5px" title="点击移除" @click="picked.splice(i, 1)">
            {{ i + 1 }}. {{ x.title }} ✕
          </span>
        </div>
        <button class="btn btn-primary btn-block" @click="savePick">保存（替换现有 {{ pickOrigN }} 件）</button>
      </div>
    </div>
  </div>
</template>
