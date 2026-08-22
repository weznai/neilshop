<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { dt } from '../composables/format'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const route = useRoute()
const router = useRouter()
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
/* 说明卡结算示例金额（美元两位小数，0 折扣 = 原价） */
const example = (sub, pct) => ((sub * (100 - (Number(pct) || 0))) / 100).toFixed(2)

const showNew = ref(false)
/* DiscountCreateIn: type int 1-3（1=pct 2=fixed 3=ship）、value 分、starts_at 必填；starts_at 空=立即生效 */
const NEW_CODE = { code: '', type: 1, value: 20, min_subtotal: 0, max_discount: null, usage_limit: null, per_user_limit: 1, first_order_only: 0, days: 30, starts_at: '' }
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
const TAB_KEYS = ['discounts', 'giftcards', 'rates', 'bundles', 'popups', 'collections']
function initTabFromQuery() {
  const t = route.query.tab
  if (TAB_KEYS.includes(t)) {
    tab.value = t
    if (t === 'collections') { colLoaded.value = true; loadCollections() }
    if (t === 'giftcards') loadGiftcards()
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

/* tab 切换：回写 URL 深链（可分享）+ 集合/礼品卡懒加载（首次进入才拉取） */
const colLoaded = ref(false)
function setTab(k) {
  tab.value = k
  router.replace({ query: { ...route.query, tab: k } })
  if (k === 'collections' && !colLoaded.value) { colLoaded.value = true; loadCollections() }
  if (k === 'giftcards' && !gcLoaded.value) loadGiftcards()
}

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const TYPE_LABEL = { 1: (v) => `${v}% off`, 2: (v) => `${money(v)} off`, 3: () => '免邮' }
/* ends_at 为 naive UTC：按 UTC 日期比较判定「已过期」（天级，避免本地时区偏移误标） */
const todayUtc = () => new Date().toISOString().slice(0, 10)
const isExpired = (c) => !!(c.ends_at && c.ends_at.slice(0, 10) < todayUtc())
/* starts_at 在未来 → 「未生效」（与 isExpired 对称，天级比较） */
const isNotStarted = (c) => !!(c.starts_at && c.starts_at.slice(0, 10) > todayUtc())

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
      /* 开始时间：填了按本地时间转 UTC ISO（datetime-local → Date → toISOString），空=当前时刻立即生效 */
      starts_at: newCode.starts_at ? new Date(newCode.starts_at).toISOString().slice(0, 19) : new Date().toISOString().slice(0, 19),
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
  if (!editCode.code.trim()) { toast('折扣码必填', 'error'); return }
  if (editCode.type === 1 && (editCode.value <= 0 || editCode.value > 100)) { toast('百分比折扣需在 1-100 之间', 'error'); return }
  try {
    await req('PUT', '/api/admin/ops/discounts/' + editCode.id, {
      /* code 放开编辑：后端会查重，冲突返回 409 detail（toast 展示） */
      code: editCode.code.trim().toUpperCase(),
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

/* ===== 核销明细（GET /discounts/{id}/usages：分页 embed，空态「暂无核销记录」） ===== */
const USE_SIZE = 10
const useDlg = ref(false)
const useCode = ref(null)
const usages = ref([])
const usePage = ref(1)
const useTotal = ref(0)
const usePages = computed(() => Math.max(1, Math.ceil(useTotal.value / USE_SIZE)))
async function loadUsages() {
  const c = useCode.value
  if (!c) return
  const d = await req('GET', `/api/admin/ops/discounts/${c.id}/usages?page=${usePage.value}&size=${USE_SIZE}`)
  usages.value = d.items || []
  useTotal.value = d.total ?? usages.value.length
}
function openUsages(c) {
  useCode.value = c
  usePage.value = 1
  useDlg.value = true
  loadUsages().catch(() => toast('核销记录加载失败', 'error'))
}
function useGo(n) {
  if (n >= 1 && n <= usePages.value) { usePage.value = n; loadUsages().catch(() => toast('核销记录加载失败', 'error')) }
}

/* 删除折扣码：危险确认；已被核销（409 code_in_use）不可删 */
const delDscDlg = ref(false)
const delDscBusy = ref(false)
const delDscTarget = ref(null)
const delDscBody = computed(() => `删除折扣码「${delDscTarget.value?.code || ''}」？删除后不可恢复。`)
function delDiscount(c) { delDscTarget.value = c; delDscDlg.value = true }
async function doDelDiscount() {
  const c = delDscTarget.value
  if (!c) return
  delDscBusy.value = true
  try {
    await req('DELETE', '/api/admin/ops/discounts/' + c.id)
    toast('已删除', 'success')
    delDscDlg.value = false
    await loadDiscounts()
  } catch (e) {
    if (e.status === 409) toast('已有核销记录，不可删除', 'error')
    else toast('删除失败：' + (e.data?.detail || e.message), 'error')
  }
  delDscBusy.value = false
}

/* ===== 礼品卡（GET /promo/giftcards?page&size&q&status：pages 前端由 total/size 计算） ===== */
const GC_SIZE = 20
const gc = ref([])
const gcLoaded = ref(false)
const gcErr = ref(false)
const gcQ = ref('')
const gcStatus = ref('')          /* '' 全部 / '1' 激活 / '2' 冻结 */
const gcPage = ref(1)
const gcTotal = ref(0)
const gcPages = computed(() => Math.max(1, Math.ceil(gcTotal.value / GC_SIZE)))
async function loadGiftcards() {
  gcErr.value = false
  try {
    const qs = new URLSearchParams({ page: gcPage.value, size: GC_SIZE })
    if (gcQ.value.trim()) qs.set('q', gcQ.value.trim())
    if (gcStatus.value) qs.set('status', gcStatus.value)
    const d = await req('GET', '/api/admin/promo/giftcards?' + qs)
    gc.value = d.items || []
    gcTotal.value = d.total ?? gc.value.length
    gcLoaded.value = true
  } catch (e) { gcErr.value = true; gc.value = []; toast('礼品卡加载失败：' + (e.message || ''), 'error') }
}
function gcGo(n) {
  if (n >= 1 && n <= gcPages.value) { gcPage.value = n; loadGiftcards() }
}
/* 搜索/状态筛选：重置回第 1 页再拉取 */
function gcSearch() { gcPage.value = 1; loadGiftcards() }

/* 余额进度条：复用库存条渐变（≤25% low / ≤60% mid / 其余 ok） */
const gcPct = (g) => (g.initial_cents ? Math.min(100, Math.round(((g.balance_cents || 0) * 100) / g.initial_cents)) : 0)
const gcBarCls = (g) => { const p = gcPct(g); return p <= 25 ? 'low' : p <= 60 ? 'mid' : 'ok' }

/* 手工发卡（POST：面额美元 ×100 取整；有效天数空=永久；卡号后端生成） */
const gcNewDlg = ref(false)
const GC_NEW = { amount: 50, days: null, note: '' }
const gcNew = reactive({ ...GC_NEW })
function openGcNew() { Object.assign(gcNew, GC_NEW); gcNewDlg.value = true }
async function createGiftcard() {
  if (!(gcNew.amount > 0)) { toast('面额需大于 0', 'error'); return }
  try {
    await req('POST', '/api/admin/promo/giftcards', {
      initial_cents: Math.round(gcNew.amount * 100),
      expires_days: gcNew.days > 0 ? Math.round(gcNew.days) : null,
      note: gcNew.note.trim() || null,
    })
    gcNewDlg.value = false
    gcPage.value = 1
    await loadGiftcards()
    toast('礼品卡已创建 ✓', 'success')
  } catch (e) { toast('创建失败：' + (e.data?.detail || e.message), 'error') }
}

/* 冻结↔解冻：按当前状态切换动作，ConfirmDialog busy 状态机防重复提交 */
const gcFrzDlg = ref(false)
const gcFrzBusy = ref(false)
const gcFrzTarget = ref(null)
const gcFrzFreezing = computed(() => gcFrzTarget.value?.status === 1)
const gcFrzBody = computed(() => (gcFrzFreezing.value
  ? `冻结礼品卡 ${gcFrzTarget.value?.code || ''}？冻结期间该卡无法用于结算。`
  : `解冻礼品卡 ${gcFrzTarget.value?.code || ''}？恢复后可正常使用。`))
function askGcFreeze(g) { gcFrzTarget.value = g; gcFrzDlg.value = true }
async function doGcFreeze() {
  const g = gcFrzTarget.value
  if (!g) return
  const wasActive = g.status === 1
  gcFrzBusy.value = true
  try {
    await req('PUT', `/api/admin/promo/giftcards/${g.id}/${wasActive ? 'freeze' : 'unfreeze'}`)
    g.status = wasActive ? 2 : 1
    toast(wasActive ? '已冻结 ✓' : '已解冻 ✓', 'success')
    gcFrzDlg.value = false
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
  gcFrzBusy.value = false
}

/* 流水明细（GET /{id}/ledger：分页 embed；delta 正绿负红） */
const LED_SIZE = 10
const ledgerDlg = ref(false)
const ledgerCard = ref(null)
const ledger = ref([])
const ledPage = ref(1)
const ledTotal = ref(0)
const ledPages = computed(() => Math.max(1, Math.ceil(ledTotal.value / LED_SIZE)))
async function loadLedger() {
  const g = ledgerCard.value
  if (!g) return
  const d = await req('GET', `/api/admin/promo/giftcards/${g.id}/ledger?page=${ledPage.value}&size=${LED_SIZE}`)
  ledger.value = d.items || []
  ledTotal.value = d.total ?? ledger.value.length
}
function openLedger(g) {
  ledgerCard.value = g
  ledPage.value = 1
  ledgerDlg.value = true
  loadLedger().catch(() => toast('流水加载失败', 'error'))
}
function ledGo(n) {
  if (n >= 1 && n <= ledPages.value) { ledPage.value = n; loadLedger().catch(() => toast('流水加载失败', 'error')) }
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
  /* 0-50 越界拦截（超 5 折不合理） */
  const v = Number(settings[BUNDLE_KEYS[key]])
  if (!Number.isFinite(v) || v < 0 || v > 50) { toast('折扣比例需在 0-50 之间', 'error'); return }
  try {
    await req('PUT', '/api/admin/ops/settings', { key: BUNDLE_KEYS[key], value: v || 0 })
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

/* 删除运费模板：危险确认；已被订单引用（409 rate_referenced）不可删 */
const delRateDlg = ref(false)
const delRateBusy = ref(false)
const delRateTarget = ref(null)
const delRateBody = computed(() => `删除运费模板「${delRateTarget.value?.dest_country || ''} · ${delRateTarget.value?.method === 'express' ? '快递' : '标准'}」？删除后不可恢复，已下单订单不受影响。`)
function delRate(r) { delRateTarget.value = r; delRateDlg.value = true }
async function doDelRate() {
  const r = delRateTarget.value
  if (!r) return
  delRateBusy.value = true
  try {
    await req('DELETE', `/api/admin/trade/shipping-rates/${r.id}`)
    toast('已删除', 'success')
    delRateDlg.value = false
    rates.value = (await req('GET', '/api/admin/trade/shipping-rates')).items || []
  } catch (e) {
    if (e.status === 409) toast('该模板已被订单引用，不可删除', 'error')
    else toast('删除失败：' + (e.data?.detail || e.message), 'error')
  }
  delRateBusy.value = false
}

/* ===== 集合页管理（GET/POST /api/admin/catalog/collections + PUT/DELETE /{id} + GET/PUT /{id}/products） ===== */
const collections = ref([])
const colErr = ref(false)
/* 商品数：列表响应自带 product_count（不再逐集合探测） */
async function loadCollections() {
  colErr.value = false
  try {
    collections.value = (await req('GET', '/api/admin/catalog/collections')).items || []
  } catch (e) {
    colErr.value = true
    collections.value = []
    toast('集合列表加载失败：' + (e.message || ''), 'error')
  }
}

/* 新建集合（CollectionCreateIn{slug,title,rule_json}；banner_image 创建后可在「编辑」中维护） */
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
/* 保存确认：先关商品选择弹窗再弹 ConfirmDialog（避免双层 modal），确认后执行原保存逻辑 */
const pickConfirm = ref(false)
const pickBusy = ref(false)
const pickConfirmBody = computed(() => (pickOrigN.value > 0
  ? `保存将替换现有 ${pickOrigN.value} 件商品为 ${picked.value.length} 件（全量替换），确认继续？`
  : `保存将把 ${picked.value.length} 件商品全量写入该集合（覆盖现有配置），确认继续？`))
function savePick() {
  if (!pickCol.value) return
  pickDlg.value = false
  pickConfirm.value = true
}
async function doSavePick() {
  const c = pickCol.value
  if (!c) return
  const n = picked.value.length
  pickBusy.value = true
  try {
    await req('PUT', `/api/admin/catalog/collections/${c.id}/products`, {
      products: picked.value.map((x, i) => ({ product_id: x.product_id, sort_order: i })),
    })
    toast('集合商品已保存 ✓', 'success')
    pickConfirm.value = false
    /* 行内回写商品数（保存的即最新全量） */
    c.product_count = n
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
  pickBusy.value = false
}

/* 启停（PUT /collections/{id} CollectionUpdateIn.is_active） */
async function toggleCollection(c) {
  try {
    await req('PUT', `/api/admin/catalog/collections/${c.id}`, { is_active: c.is_active ? 0 : 1 })
    c.is_active = c.is_active ? 0 : 1
    toast(c.is_active ? '已启用 ✓' : '已停用 ✓', 'success')
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
/* 删除集合：ConfirmDialog 危险确认（不可恢复） */
const delColDlg = ref(false)
const delColBusy = ref(false)
const delColTarget = ref(null)
const delColBody = computed(() => `删除集合「${delColTarget.value?.title || ''}」？关联的 ${delColTarget.value?.product_count ?? '?'} 件商品配置将一并移除，不可恢复。`)
function delCollection(c) { delColTarget.value = c; delColDlg.value = true }
async function doDelCollection() {
  const c = delColTarget.value
  if (!c) return
  delColBusy.value = true
  try {
    await req('DELETE', `/api/admin/catalog/collections/${c.id}`)
    toast('已删除', 'success')
    delColDlg.value = false
    loadCollections()
  } catch (e) { toast('删除失败：' + (e.data?.detail || e.message), 'error') }
  delColBusy.value = false
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">营销工具</h1>
      <span class="page-sub">折扣码 / 礼品卡 / 运费模板 / 捆绑折扣 / 弹窗 / 集合</span>
    </div>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button
      v-for="[k, label] in [['discounts', '折扣码'], ['giftcards', '礼品卡'], ['rates', '运费模板'], ['bundles', '捆绑折扣'], ['popups', '弹窗'], ['collections', '集合页']]"
      :key="k"
      style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer"
      :style="{ color: tab === k ? 'var(--plum)' : 'var(--gray)', borderBottom: tab === k ? '2.5px solid var(--plum)' : '2.5px solid transparent' }"
      @click="setTab(k)"
    >{{ label }}</button>
  </div>

  <!-- 加载失败横幅：所有 tab 共用（初始加载/重试失败时置位，重试走 load） -->
  <div v-if="loadErr" style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 14px;margin-bottom:14px;background:var(--pale-error);border:1px solid var(--error);border-radius:10px;font-size:12.5px;color:var(--error)">
    <span>⚠️ 部分数据加载失败，展示的可能不是最新配置</span>
    <button class="btn btn-secondary btn-sm" @click="load">重试</button>
  </div>

  <!-- 折扣码 -->
  <template v-if="tab === 'discounts'">
    <div v-if="!loaded" class="card skeleton" style="min-height:220px"></div>
    <div v-else class="card tbl-wrap">
      <div class="dhead" style="padding:14px 16px 0">
        <h3 class="dtitle">折扣码</h3>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
          <span style="font-size:12.5px;color:var(--gray)">共 {{ dscTotal }} 个 · 当前页启用 {{ discounts.filter((c) => c.is_active).length }}<span v-if="discounts.some((c) => isExpired(c))"> · 当前页 {{ discounts.filter((c) => isExpired(c)).length }} 个已过期</span></span>
          <button class="btn btn-primary btn-sm" @click="openNew">＋ 新建折扣码</button>
        </div>
      </div>
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
              <span v-else-if="c.is_active && isNotStarted(c)" class="tag tag-done">未生效</span>
              <span v-else class="tag" :class="c.is_active ? 'tag-paid' : 'tag-pending'">{{ c.is_active ? '启用' : '停用' }}</span>
            </td>
            <td style="text-align:right;white-space:nowrap">
              <button class="btn btn-secondary btn-sm" @click="editDiscount(c)">编辑</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="toggleCode(c)">{{ c.is_active ? '停用' : '启用' }}</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="openUsages(c)">明细</button>
              <button class="btn btn-ghost btn-sm" style="margin-left:4px;color:var(--error)" @click="delDiscount(c)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!discounts.length" icon="🏷️" title="暂无折扣码" sub="点击右上角「新建折扣码」创建第一个" />
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
          <div class="field"><label>开始时间（空=立即生效）</label><input v-model="newCode.starts_at" class="input" type="datetime-local"></div>
          <div class="field"><label>有效天数（0=永久）</label><input v-model.number="newCode.days" class="input" type="number"></div>
          <div class="field"><label>总次数（空=不限）</label><input v-model.number="newCode.usage_limit" class="input" type="number" min="1"></div>
          <div class="field"><label>每人限用次数</label><input v-model.number="newCode.per_user_limit" class="input" type="number" min="1"></div>
        </div>
        <label style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer;margin-top:10px">
          <input v-model="newCode.first_order_only" type="checkbox" style="width:16px;height:16px"> 仅限首单使用
        </label>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px">
          <button class="btn btn-secondary btn-sm" @click="closeNew">取消</button>
          <button class="btn btn-primary btn-sm" @click="addCode">创建</button>
        </div>
      </div>
    </div>

    <!-- 编辑折扣码（code/value/门槛/封顶/次数/有效期；启停走行内按钮） -->
    <div v-if="editDlg" class="modal open" @click.self="editDlg = false">
      <div class="modal-box" style="max-width:520px">
        <button class="modal-x" @click="editDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">✏️ 编辑折扣码 {{ editCode.code }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">类型不可更改；金额单位为美元，保存时换算为美分。</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field" style="grid-column:1/-1"><label>码（修改后后端查重，重复将保存失败）</label>
            <input v-model="editCode.code" class="input" style="text-transform:uppercase"></div>
          <div v-if="editCode.type !== 3" class="field"><label>{{ editCode.type === 1 ? '折扣 %' : '减免 $' }}</label>
            <input v-model.number="editCode.value" class="input" type="number"></div>
          <div class="field"><label>门槛 $（0=无）</label><input v-model.number="editCode.min_subtotal" class="input" type="number"></div>
          <div v-if="editCode.type === 1" class="field"><label>封顶 $（可选）</label><input v-model.number="editCode.max_discount" class="input" type="number"></div>
          <div class="field"><label>总次数（空=不限）</label><input v-model.number="editCode.usage_limit" class="input" type="number" min="1"></div>
          <div class="field"><label>每人限用次数</label><input v-model.number="editCode.per_user_limit" class="input" type="number" min="1"></div>
          <div class="field"><label>开始时间 (UTC)</label><input v-model="editCode.starts_at" class="input" type="datetime-local"></div>
          <div class="field"><label>结束时间 (UTC)（空=永久）</label><input v-model="editCode.ends_at" class="input" type="datetime-local"></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px">
          <button class="btn btn-secondary btn-sm" @click="editDlg = false">取消</button>
          <button class="btn btn-primary btn-sm" @click="saveEdit">保存</button>
        </div>
      </div>
    </div>

    <!-- 核销明细（GET /discounts/{id}/usages：订单/邮箱/优惠金额/时间，分页 embed） -->
    <div v-if="useDlg" class="modal open" @click.self="useDlg = false">
      <div class="modal-box" style="max-width:560px">
        <button class="modal-x" @click="useDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">📋 核销明细 · {{ useCode?.code }}</h3>
        <table style="width:100%;border-collapse:collapse;font-size:12.5px">
          <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:8px">订单号</th><th>邮箱</th><th>优惠金额</th><th>时间</th></tr></thead>
          <tbody>
            <tr v-for="u in usages" :key="u.id" style="border-top:1px solid var(--gray-light)">
              <td style="padding:8px 6px"><code style="font-size:12px">{{ u.order_no || '—' }}</code></td>
              <td style="color:var(--gray)">{{ u.email || '—' }}</td>
              <td><b style="color:var(--plum)">−{{ money(u.discount_amount_cents) }}</b></td>
              <td style="color:var(--gray)">{{ dt(u.created_at) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="!usages.length" style="text-align:center;color:var(--gray);font-size:12.5px;padding:18px 0">暂无核销记录</div>
        <Pagination embed :page="usePage" :pages="usePages" :total="useTotal" unit="条" @go="useGo" />
      </div>
    </div>

    <!-- 删除折扣码确认（409 code_in_use 不可删） -->
    <ConfirmDialog :open="delDscDlg" title="删除折扣码" :body="delDscBody" danger confirm-text="删除" :busy="delDscBusy" @confirm="doDelDiscount" @close="delDscDlg = false" />
  </template>

  <!-- 礼品卡（/promo/giftcards：搜索/状态筛选/分页；冻结↔解冻；流水） -->
  <template v-else-if="tab === 'giftcards'">
    <EmptyState v-if="gcErr" icon="⚠️" title="礼品卡列表加载失败" sub="服务端可能未启动或端点暂不可用">
      <template #action><button class="btn btn-secondary btn-sm" @click="loadGiftcards">重试</button></template>
    </EmptyState>
    <template v-else>
      <div v-if="!gcLoaded" class="card skeleton" style="min-height:220px"></div>
      <div v-else class="card tbl-wrap">
        <div class="dhead" style="padding:14px 16px 0">
          <h3 class="dtitle">礼品卡</h3>
          <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
            <span style="font-size:12.5px;color:var(--gray)">共 {{ gcTotal }} 张 · 当前页激活 {{ gc.filter((g) => g.status === 1).length }} / 冻结 {{ gc.filter((g) => g.status === 2).length }}</span>
            <button class="btn btn-primary btn-sm" @click="openGcNew">＋ 手工发卡</button>
          </div>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:12px 16px 0">
          <input v-model="gcQ" class="input" style="width:200px" placeholder="搜卡号 / 邮箱" @keydown.enter="gcSearch">
          <button class="btn btn-secondary btn-sm" @click="gcSearch">搜索</button>
          <select v-model="gcStatus" class="input" style="width:auto;padding:6px 10px" @change="gcSearch">
            <option value="">全部状态</option><option value="1">激活</option><option value="2">冻结</option>
          </select>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="text-align:left;color:var(--gray)">
            <th style="padding:10px">卡号</th><th>余额</th><th>面值</th><th>状态</th><th>购买人</th><th>收件人</th><th>过期时间</th><th style="text-align:right">操作</th>
          </tr></thead>
          <tbody>
            <tr v-for="g in gc" :key="g.id" style="border-top:1px solid var(--gray-light)">
              <td style="padding:11px 10px"><code style="font-size:12px">{{ g.code }}</code></td>
              <td style="white-space:nowrap">
                <div style="display:flex;align-items:center;gap:8px" :title="`余额 ${money(g.balance_cents)} / 面值 ${money(g.initial_cents)}`">
                  <div class="stock-track" style="width:64px">
                    <div class="stock-fill" :class="gcBarCls(g)" :style="{ width: gcPct(g) + '%' }"></div>
                  </div>
                  <b>{{ money(g.balance_cents) }}</b>
                </div>
              </td>
              <td>{{ money(g.initial_cents) }}</td>
              <td><span class="tag" :class="g.status === 1 ? 'tag-paid' : 'tag-error'">{{ g.status === 1 ? '激活' : '冻结' }}</span></td>
              <td style="color:var(--gray);font-size:12px">{{ g.purchaser_email || '—' }}</td>
              <td style="color:var(--gray);font-size:12px">{{ g.recipient_email || '—' }}</td>
              <td style="color:var(--gray);font-size:12px">{{ g.expired_at ? dt(g.expired_at) : '永久' }}</td>
              <td style="text-align:right;white-space:nowrap">
                <button class="btn btn-ghost btn-sm" style="margin-left:4px" @click="askGcFreeze(g)">{{ g.status === 1 ? '冻结' : '解冻' }}</button>
                <button class="btn btn-secondary btn-sm" @click="openLedger(g)">流水</button>
              </td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-if="!gc.length" icon="🎁" title="暂无礼品卡" sub="点击右上角「手工发卡」创建第一张" />
        <Pagination embed :page="gcPage" :pages="gcPages" :total="gcTotal" unit="张" @go="gcGo" />
      </div>
    </template>

    <!-- 手工发卡（面额美元 ×100 取整；天数空=永久） -->
    <div v-if="gcNewDlg" class="modal open" @click.self="gcNewDlg = false">
      <div class="modal-box" style="max-width:440px">
        <button class="modal-x" @click="gcNewDlg = false">×</button>
        <div class="dhead" style="margin-bottom:12px">
          <h3 class="dtitle">手工发卡</h3>
          <span style="font-size:12px;color:var(--gray)">卡号由后端生成，流水可查</span>
        </div>
        <div style="display:grid;gap:12px">
          <div class="field"><label>面额（美元）*</label><input v-model.number="gcNew.amount" class="input" type="number" min="0.01" step="0.01"></div>
          <div class="field"><label>有效天数（空 = 永久）</label><input v-model.number="gcNew.days" class="input" type="number" min="1"></div>
          <div class="field"><label>备注（可选）</label><input v-model="gcNew.note" class="input" placeholder="如：客服补偿"></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px">
          <button class="btn btn-secondary btn-sm" @click="gcNewDlg = false">取消</button>
          <button class="btn btn-primary btn-sm" @click="createGiftcard">创建</button>
        </div>
      </div>
    </div>

    <!-- 流水明细（时间/变动/余额/关联订单；delta 正绿负红；分页 embed） -->
    <div v-if="ledgerDlg" class="modal open" @click.self="ledgerDlg = false">
      <div class="modal-box" style="max-width:560px">
        <button class="modal-x" @click="ledgerDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">🧾 流水 · {{ ledgerCard?.code }}</h3>
        <table style="width:100%;border-collapse:collapse;font-size:12.5px">
          <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:8px">时间</th><th>变动</th><th>余额</th><th>关联订单</th></tr></thead>
          <tbody>
            <tr v-for="l in ledger" :key="l.id" style="border-top:1px solid var(--gray-light)">
              <td style="padding:8px 6px;color:var(--gray);white-space:nowrap">{{ dt(l.created_at) }}</td>
              <td :style="{ color: (l.delta_cents || 0) >= 0 ? '#2FA463' : 'var(--error)', fontWeight: 600 }">{{ (l.delta_cents || 0) >= 0 ? '+' : '' }}{{ money(l.delta_cents) }}</td>
              <td>{{ l.balance_after_cents != null ? money(l.balance_after_cents) : '—' }}</td>
              <td><code style="font-size:12px">{{ l.order_no || '—' }}</code></td>
            </tr>
          </tbody>
        </table>
        <div v-if="!ledger.length" style="text-align:center;color:var(--gray);font-size:12.5px;padding:18px 0">暂无流水记录</div>
        <Pagination embed :page="ledPage" :pages="ledPages" :total="ledTotal" unit="条" @go="ledGo" />
      </div>
    </div>

    <!-- 冻结/解冻确认（按当前状态切换动作与文案；冻结为危险态） -->
    <ConfirmDialog :open="gcFrzDlg" :title="gcFrzFreezing ? '冻结礼品卡' : '解冻礼品卡'" :body="gcFrzBody" :danger="gcFrzFreezing" :confirm-text="gcFrzFreezing ? '冻结' : '解冻'" :busy="gcFrzBusy" @confirm="doGcFreeze" @close="gcFrzDlg = false" />
  </template>

  <!-- 运费模板 -->
  <template v-else-if="tab === 'rates'">
    <div v-if="!loaded" class="card skeleton" style="min-height:220px"></div>
    <div v-else class="card tbl-wrap">
      <div class="dhead" style="padding:14px 16px 0">
        <h3 class="dtitle">运费模板</h3>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
          <span style="font-size:12.5px;color:var(--gray)">共 {{ rates.length }} 条 · 启用 {{ rates.filter((r) => r.active).length }} · 结算按「国家→方式」取启用模板</span>
          <button class="btn btn-primary btn-sm" @click="newRate">＋ 新建模板</button>
        </div>
      </div>
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
              <button class="btn btn-ghost btn-sm" style="margin-left:4px;color:var(--error)" @click="delRate(r)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!rates.length" icon="🚚" title="暂无运费模板" sub="结算将使用 settings 默认运费" />
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
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px">
          <button class="btn btn-secondary btn-sm" @click="rateDlg = false">取消</button>
          <button class="btn btn-primary btn-sm" @click="saveRate">保存</button>
        </div>
      </div>
    </div>

    <!-- 删除运费模板确认（409 rate_referenced 不可删） -->
    <ConfirmDialog :open="delRateDlg" title="删除运费模板" :body="delRateBody" danger confirm-text="删除" :busy="delRateBusy" @confirm="doDelRate" @close="delRateDlg = false" />
  </template>

  <!-- 捆绑折扣：全宽双卡（左编辑表单 / 右当前生效规则与结算示例），≤900px 单列 -->
  <template v-else-if="tab === 'bundles'">
    <div class="bundle-grid">
      <div class="card" style="padding:20px">
        <div class="dhead" style="margin-bottom:10px">
          <h3 class="dtitle">🎁 捆绑折扣</h3>
          <span class="item-cnt">结算即时生效</span>
        </div>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:14px">两件 / 三件及以上的购物车整单折扣比例（%，0 = 关闭该档）。</p>
        <div class="field"><label>买 2 件折扣 %（0-50）</label>
          <div style="display:flex;gap:8px">
            <input v-model.number="settings.bundle_2_off" class="input" type="number" min="0" max="50">
            <button class="btn btn-secondary" @click="saveBundle('b2')">保存</button>
          </div>
        </div>
        <div class="field"><label>买 3+ 件折扣 %（0-50）</label>
          <div style="display:flex;gap:8px">
            <input v-model.number="settings.bundle_3_off" class="input" type="number" min="0" max="50">
            <button class="btn btn-secondary" @click="saveBundle('b3')">保存</button>
          </div>
        </div>
      </div>
      <div class="card" style="padding:20px">
        <div class="dhead" style="margin-bottom:10px"><h3 class="dtitle">当前生效规则与结算示例</h3></div>
        <div class="kv-row"><span>买 2 件整单折扣</span><b>{{ Number(settings.bundle_2_off) ? settings.bundle_2_off + '%' : '已关闭' }}</b></div>
        <div class="kv-row"><span>买 3+ 件整单折扣</span><b>{{ Number(settings.bundle_3_off) ? settings.bundle_3_off + '%' : '已关闭' }}</b></div>
        <div class="kv-row"><span>生效范围</span><b>全店购物车结算</b></div>
        <p style="font-size:12.5px;color:var(--gray);margin-top:12px;line-height:1.8">
          结算示例：2 件小计 $100.00 → 享 −{{ settings.bundle_2_off }}%，应付 <b style="color:var(--plum)">${{ example(100, settings.bundle_2_off) }}</b>；
          3 件小计 $150.00 → 享 −{{ settings.bundle_3_off }}%，应付 <b style="color:var(--plum)">${{ example(150, settings.bundle_3_off) }}</b>。
          实际金额以后端结算为准。
        </p>
      </div>
    </div>
  </template>

  <!-- 弹窗（PopupConfig 完整 CRUD + 启停；前台按 scene 拉取启用中的最新一条） -->
  <div v-else-if="tab === 'popups'">
    <div v-if="!loaded" class="card skeleton" style="min-height:220px"></div>
    <div v-else class="card tbl-wrap">
      <div class="dhead" style="padding:14px 16px 0">
        <h3 class="dtitle">弹窗</h3>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
          <span style="font-size:12.5px;color:var(--gray)">共 {{ popups.length }} 个 · 启用 {{ popups.filter((p) => p.active).length }} · 前台同场景取最新启用且在有效期内的一个</span>
          <button class="btn btn-primary btn-sm" @click="newPopup">＋ 新建弹窗</button>
        </div>
      </div>
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
      <EmptyState v-if="!popups.length" icon="🪟" title="暂无弹窗配置" sub="点击右上角「新建弹窗」创建" />
    </div>

    <!-- 弹窗编辑（scene/title/content_md/coupon_code/trigger_rules/有效期/active） -->
    <div v-if="popupDlg" class="modal open" @click.self="popupDlg = false">
      <div class="modal-box" style="max-width:560px">
        <button class="modal-x" @click="popupDlg = false">×</button>
        <h3 style="font-family:var(--font-title);margin-bottom:6px">{{ popupForm.id ? '✏️ 编辑弹窗 #' + popupForm.id : '🪟 新建弹窗' }}</h3>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">按场景自动弹出：前台自动拉取「启用中 + 有效期内」的最新一条展示。</p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field"><label>场景 scene</label>
            <input v-model="popupForm.scene" class="input" list="popup-scenes" placeholder="welcome">
            <datalist id="popup-scenes">
              <option v-for="(name, s) in POPUP_SCENES" :key="s" :value="s">{{ name }}</option>
            </datalist>
          </div>
          <div class="field"><label>券码（可选，下拉选择或手动输入）</label>
            <input v-model="popupForm.coupon_code" class="input" list="popup-coupon-codes" placeholder="WELCOME20" style="text-transform:uppercase">
            <datalist id="popup-coupon-codes">
              <option v-for="c in discounts" :key="c.id" :value="c.code" />
            </datalist>
          </div>
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
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px">
          <button class="btn btn-secondary btn-sm" @click="popupDlg = false">取消</button>
          <button class="btn btn-primary btn-sm" @click="savePopup">保存</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 集合页（GET/POST /api/admin/catalog/collections + PUT/DELETE /{id} + GET/PUT /{id}/products） -->
  <div v-else>
    <EmptyState v-if="colErr" icon="⚠️" title="集合列表加载失败" sub="服务端可能未启动或端点暂不可用">
      <template #action><button class="btn btn-secondary btn-sm" @click="loadCollections">重试</button></template>
    </EmptyState>
    <template v-else>
      <div v-if="!loaded" class="card skeleton" style="min-height:220px"></div>
      <div v-else class="card tbl-wrap">
        <div class="dhead" style="padding:14px 16px 0">
          <h3 class="dtitle">集合页</h3>
          <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
            <span style="font-size:12.5px;color:var(--gray)">共 {{ collections.length }} 个集合 · 启用 {{ collections.filter((c) => c.is_active).length }} · 商品数为手动配置的固定商品</span>
            <button class="btn btn-primary btn-sm" @click="newCollection">＋ 新建集合</button>
          </div>
        </div>
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
              <td><b>{{ c.product_count ?? '—' }}</b></td>
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
    </template>

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
            <p style="font-size:11px;color:var(--gray);margin-top:4px">创建后可在编辑中补充图片。</p>
          </div>
          <div class="field"><label>高级规则 rule_json（JSON 对象，可选）</label>
            <textarea v-model="colForm.ruleStr" class="input" rows="3" placeholder='{} 或 {"category":"new"}'></textarea>
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px">
          <button class="btn btn-secondary btn-sm" @click="colDlg = false">取消</button>
          <button class="btn btn-primary btn-sm" @click="createCollection">创建</button>
        </div>
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
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px">
          <button class="btn btn-secondary btn-sm" @click="colEditDlg = false">取消</button>
          <button class="btn btn-primary btn-sm" @click="saveColEdit">保存</button>
        </div>
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
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
          <button class="btn btn-secondary btn-sm" @click="pickDlg = false">取消</button>
          <button class="btn btn-primary btn-sm" @click="savePick">保存（替换现有 {{ pickOrigN }} 件）</button>
        </div>
      </div>
    </div>

    <!-- 配商品保存确认（先关选择弹窗再确认） -->
    <ConfirmDialog :open="pickConfirm" title="保存集合商品" :body="pickConfirmBody" confirm-text="保存" :busy="pickBusy" @confirm="doSavePick" @close="pickConfirm = false" />
    <!-- 删除集合确认（危险操作） -->
    <ConfirmDialog :open="delColDlg" title="删除集合" :body="delColBody" danger confirm-text="删除" :busy="delColBusy" @confirm="doDelCollection" @close="delColDlg = false" />
  </div>
</template>

<style scoped>
/* 捆绑折扣双卡：宽屏左右并排，≤900px 单列堆叠 */
.bundle-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start}
@media(max-width:900px){.bundle-grid{grid-template-columns:1fr}}
</style>
