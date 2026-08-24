<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req, intentNoChannel } from '../api/client'
import { i18n, tt } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'
import { createOrderIntent } from '../composables/useOrderPay'

const cart = useCartStore()
const ui = useUiStore()
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()


const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const US_STATES = ['AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY']
/* 地址簿历史数据可能存州名全称：预填时映射为两位缩写（fillAddr），使表单可通过校验 */
const US_STATE_ABBR = {
  Alabama: 'AL', Alaska: 'AK', Arizona: 'AZ', Arkansas: 'AR', California: 'CA', Colorado: 'CO',
  Connecticut: 'CT', Delaware: 'DE', Florida: 'FL', Georgia: 'GA', Hawaii: 'HI', Idaho: 'ID',
  Illinois: 'IL', Indiana: 'IN', Iowa: 'IA', Kansas: 'KS', Kentucky: 'KY', Louisiana: 'LA',
  Maine: 'ME', Maryland: 'MD', Massachusetts: 'MA', Michigan: 'MI', Minnesota: 'MN',
  Mississippi: 'MS', Missouri: 'MO', Montana: 'MT', Nebraska: 'NE', Nevada: 'NV',
  'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
  'North Carolina': 'NC', 'North Dakota': 'ND', Ohio: 'OH', Oklahoma: 'OK', Oregon: 'OR',
  Pennsylvania: 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD',
  Tennessee: 'TN', Texas: 'TX', Utah: 'UT', Vermont: 'VT', Virginia: 'VA', Washington: 'WA',
  'West Virginia': 'WV', Wisconsin: 'WI', Wyoming: 'WY',
}
const COUNTRIES = ['US', 'CA', 'GB', 'AU', 'DE', 'FR']

/* 折扣码失败原因走 i18n promo.*（对齐后端 promo REASON_TEXT：preview 返回裸 reason 码），
   t() 缺键返回键本身 → 回退展示原始 reason 码 */
const reasonText = (r) => {
  const v = i18n.t('promo.' + r)
  return v === 'promo.' + r ? r : v
}

const form = ref({ email: '', fname: '', lname: '', addr1: '', addr2: '', city: '', state: '', zip: '', phone: '', note: '' })
const country = ref('US')
const errors = ref({})

/* 地址簿（登录用户）：GET /api/account/addresses，默认地址预选回填；0 = 手填新地址 */
const savedAddrs = ref([])
const selAddr = ref(0)
/* 选中地址簿地址但隐藏字段校验失败时，列出无效字段并引导切换新地址（字段无输入框可标红） */
const addrErrFields = ref(null)
const ADDR_FIELD_LABELS = { fname: 'co.fname', addr1: 'co.addr', city: 'co.city', state: 'co.state', zip: 'co.zip', country: 'co.country' }

function fillAddr(a) {
  const f = form.value
  /* 地址簿只存 full_name：首词作名、其余作姓（place 时再拼回，无损） */
  const parts = (a.full_name || '').trim().split(/\s+/)
  f.fname = parts.shift() || ''
  f.lname = parts.join(' ')
  f.addr1 = a.line1 || ''
  f.addr2 = a.line2 || ''
  f.city = a.city || ''
  f.state = (a.state && US_STATE_ABBR[a.state.trim()]) || a.state || ''
  f.zip = a.zip || ''
  f.phone = a.phone || ''
  const c = (a.country || 'US').toUpperCase()
  if (c && !COUNTRIES.includes(c)) COUNTRIES.push(c)
  country.value = c
}

function pickAddr(a) {
  selAddr.value = a.id
  fillAddr(a)
  errors.value = {}
  addrErrFields.value = null
}

function pickNewAddr() {
  selAddr.value = 0
  const f = form.value
  f.fname = ''; f.lname = ''; f.addr1 = ''; f.addr2 = ''
  f.city = ''; f.state = ''; f.zip = ''; f.phone = ''
  addrErrFields.value = null
}

/* 地址簿地址校验不过 → 切换新地址表单并用该地址数据预填，供用户直接修正 */
function fixAddr() {
  const a = savedAddrs.value.find((x) => x.id === selAddr.value)
  selAddr.value = 0
  if (a) fillAddr(a)
  errors.value = {}
  addrErrFields.value = null
}

async function loadAddrs() {
  if (!auth.isLoggedIn) return
  try {
    const list = await req('GET', '/api/account/addresses')
    savedAddrs.value = Array.isArray(list) ? list : []
    const def = savedAddrs.value.find((a) => a.is_default) || savedAddrs.value[0]
    if (def) pickAddr(def)
  } catch (_) { /* 地址簿拉取失败 → 回落手填表单 */ }
}

/* 配送方式（后端 /api/checkout/shipping-methods：运费模板聚合） */
const shipMethods = ref([])
const FALLBACK_METHODS = [
  { method: 'standard', carrier: 'usps', price: 499, free_over: 3500, eta_min_days: 3, eta_max_days: 6 },
  { method: 'express', carrier: 'ups', price: 1499, free_over: null, eta_min_days: 1, eta_max_days: 3 },
]
const shipMethod = ref('standard')

/* 支付方式（后端 /api/payments/methods provider 列表） */
const payProviders = ref([])
const payDefault = ref('mock')
const paySel = ref('mock')

/* 折扣码 / 礼品卡 / 积分 */
const code = ref('')
const appliedCode = ref(null)
const gcInput = ref('')
const appliedGc = ref(null)
const pointsInput = ref('')
const placing = ref(false)

/* 礼物选项（PlaceRequest.gift_flag / gift_message） */
const gift = ref(false)
const giftMsg = ref('')
const saveAddr = ref(true)

const pv = ref(null)
const pvBusy = ref(false)
const pvError = ref('')

/* 摘要行项图兜底：回落 placehold + dataset 守卫防循环 */
const IMG_FALLBACK = 'https://placehold.co/120x120/E8B4B8/552338?text=GLOWMAG'
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = IMG_FALLBACK
}

let pvTimer = null
let pvSeq = 0
function schedulePreview() {
  clearTimeout(pvTimer)
  pvTimer = setTimeout(runPreview, 500)
}
onUnmounted(() => clearTimeout(pvTimer))

const pointsUsable = computed(() => (auth.points && auth.points.usable) || 0)
const pointsApplied = computed(() => {
  if (!auth.isLoggedIn) return 0
  const n = Math.floor(Number(pointsInput.value) || 0)
  return n > 0 ? n : 0
})

async function runPreview() {
  if (!cart.items.length) { pv.value = null; return }
  const seq = ++pvSeq
  pvBusy.value = true
  pvError.value = ''
  try {
    const d = await req('POST', '/api/checkout/preview', {
      country: country.value,
      state: (form.value.state || '').trim().toUpperCase() || null,
      shipping_method: shipMethod.value,
      code: appliedCode.value || undefined,
      gift_card_code: appliedGc.value || undefined,
      points: pointsApplied.value || undefined,
      email: form.value.email || (auth.user && auth.user.email) || undefined,
    })
    if (seq !== pvSeq) return
    pv.value = d
  } catch (e) {
    if (seq !== pvSeq) return
    pv.value = null
    const m = (e.data && e.data.detail) || ''
    if (/^insufficient_points/.test(m)) pvError.value = i18n.t('co.errPoints')
    else if (/login_required_for_points/.test(m)) pvError.value = i18n.t('co.errLoginPts')
    else if (/^insufficient_stock/.test(m)) pvError.value = i18n.t('co.errStock')
    else if (/^variant_(inactive|not_found)/.test(m)) pvError.value = tt('Some items are no longer available — please remove them first', '部分商品已下架，请先移除后再下单')
  } finally {
    if (seq === pvSeq) pvBusy.value = false
  }
}

function giftCardText(code) {
  return i18n.t(code === 'gift_card_expired' ? 'co.gcExpired' : 'co.gcBad')
}

async function applyCode() {
  const c = (code.value || '').trim().toUpperCase()
  if (!c) { ui.toast(reasonText('no_code'), 'error'); return }
  appliedCode.value = c
  await runPreview()
  if (pv.value && pv.value.code_valid) {
    try { localStorage.setItem('gm_applied_code', c) } catch (_) { /* 隐私模式 */ }
    ui.toast(pv.value.free_shipping
      ? i18n.t('promo.appliedShip', c)
      : i18n.t('promo.appliedSave', c, money(pv.value.code_discount).slice(1)), 'success')
  } else if (pv.value) {
    try { localStorage.removeItem('gm_applied_code') } catch (_) { /* 隐私模式 */ }
    ui.toast(reasonText(pv.value.code_reason), 'error')
  } else if (!pvError.value) {
    ui.toast(i18n.t('promo.verifyFail'), 'error')
  }
}
function removeCode() {
  appliedCode.value = null
  code.value = ''
  try { localStorage.removeItem('gm_applied_code') } catch (_) { /* 隐私模式 */ }
  /* 同步移除 URL ?code=（保留其它 query），避免刷新/分享时旧码复活 */
  if (route.query.code != null) router.replace({ query: { ...route.query, code: undefined } })
  runPreview()
}

async function applyGiftCard() {
  const c = (gcInput.value || '').trim().toUpperCase()
  if (!c) { ui.toast(i18n.t('co.gcEnter'), 'error'); return }
  appliedGc.value = c
  await runPreview()
  if (pv.value && pv.value.gift_card_error) {
    ui.toast(giftCardText(pv.value.gift_card_error), 'error')
  } else if (pv.value && pv.value.gift_card) {
    ui.toast(i18n.t('co.gcApplied', money(pv.value.gift_card.balance)), 'success')
  } else if (pv.value) {
    ui.toast(i18n.t('co.gcCheckFail'), 'error')
  } else if (!pvError.value) {
    ui.toast(i18n.t('promo.verifyFail'), 'error')
  }
}
function removeGiftCard() { appliedGc.value = null; gcInput.value = ''; runPreview() }

function useMaxPoints() {
  /* 后端口径：积分上限 = subtotal - discount_total（积分先于礼品卡抵扣，不预减 GC） */
  const coverable = pv.value
    ? Math.max(0, pv.value.subtotal - pv.value.discount_total)
    : cart.subtotalC
  pointsInput.value = String(Math.max(0, Math.min(pointsUsable.value, coverable)))
  schedulePreview()
}
function clampPoints() {
  const n = Math.floor(Number(pointsInput.value) || 0)
  pointsInput.value = n > 0 ? String(Math.min(n, pointsUsable.value)) : ''
}

async function loadShipMethods() {
  try {
    const d = await req('GET', '/api/checkout/shipping-methods?country=' + country.value)
    shipMethods.value = (d.items && d.items.length) ? d.items : FALLBACK_METHODS
    if (d.free_shipping_threshold) shipThreshold.value = Number(d.free_shipping_threshold) || 3500
  } catch (_) { shipMethods.value = FALLBACK_METHODS }
  /* 国家切换后原方式可能不存在（如该国无 express 模板）→ 回落首个可选 */
  if (shipMethods.value.length && !shipMethods.value.some((m) => m.method === shipMethod.value)) {
    shipMethod.value = shipMethods.value[0].method
  }
}
/* 支付方式加载失败：不再静默回落 mock（避免下单后支付死路），置 methodsErr 供 UI 重试 */
const methodsErr = ref(false)
async function loadPayMethods() {
  try {
    const d = await req('GET', '/api/payments/methods')
    payProviders.value = d.providers || []
    payDefault.value = d.default || 'mock'
    if (!paySel.value || !payProviders.value.some((p) => p.id === paySel.value)) {
      paySel.value = payDefault.value
    }
    methodsErr.value = false
  } catch (_) {
    payProviders.value = []
    methodsErr.value = true
  }
}

const methodLabel = (m) => i18n.t(m.method === 'express' ? 'co.express' : 'co.standard')
/* 免邮门槛：settings 下发（shipping-methods 响应），运营改配置后三处展示统一生效 */
const shipThreshold = ref(3500)
const selMethod = computed(() => shipMethods.value.find((m) => m.method === shipMethod.value))
const freeShipThreshold = computed(() => {
  const m = selMethod.value
  return (m && m.free_over != null) ? m.free_over : shipThreshold.value
})

/* 免邮提示（FREESHIP 码 / 满额）：基于 preview 分项推算 */
const shipHint = computed(() => {
  if (!pv.value) return ''
  if (pv.value.free_shipping) return i18n.t('co.shipPromo')
  if (pv.value.shipping_fee === 0) return i18n.t('co.shipUnlocked')
  if (shipMethod.value !== 'standard') return ''
  const after = Math.max(0, pv.value.subtotal - pv.value.discount_total - pv.value.points_discount - pv.value.giftcard_discount)
  const away = freeShipThreshold.value - after
  return away > 0 ? i18n.t('co.shipAway', money(away)) : ''
})

function validate() {
  const f = form.value
  const e = {}
  if (!EMAIL_RE.test((f.email || '').trim())) e.email = true
  if (!f.fname.trim()) e.fname = true
  if (!f.addr1.trim()) e.addr1 = true
  if (!f.city.trim()) e.city = true
  if (country.value === 'US' && !US_STATES.includes((f.state || '').trim().toUpperCase())) e.state = true
  /* 非 US 州/省软必填：DHL 等跨境承运配送单需要省/州信息 */
  if (country.value !== 'US' && !(f.state || '').trim()) e.state = true
  if (!(f.zip || '').trim()) e.zip = true
  else if (country.value === 'US' && !/^\d{5}(-\d{4})?$/.test(f.zip.trim())) e.zip = true
  errors.value = e
  const ok = Object.keys(e).length === 0
  if (!ok) {
    nextTick(() => {
      const el = document.querySelector('.field.error')
      if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }
  return ok
}

function mapPlaceError(e) {
  const m = (e.data && e.data.detail) || e.message || ''
  if (m.startsWith('invalid_code:')) return reasonText(m.slice('invalid_code:'.length))
  if (m.startsWith('insufficient_stock')) { cart.refresh().catch(() => {}); return i18n.t('co.errStockRefresh') }
  if (m === 'insufficient_points') return i18n.t('co.errPoints')
  if (m === 'login_required_for_points') return i18n.t('co.errLoginPts')
  if (m === 'empty_cart') return i18n.t('co.emptyCart')
  if (m === 'gift_card_not_available') return giftCardText(m)
  if (m === 'gift_card_expired') return giftCardText(m)
  if (m === 'gift_card_insufficient') return tt('Gift card balance changed — please re-apply', '礼品卡余额已变动，请重新应用')
  if (m.startsWith('variant_inactive') || m.startsWith('variant_not_found')) {
    cart.refresh().catch(() => {})
    return tt('Some items are no longer available — please remove them first', '部分商品已下架，请先移除后再下单')
  }
  if (m === 'account_blocked') return tt('This account cannot place orders. Contact support.', '该账户暂无法下单，请联系客服')
  console.warn('[checkout] unmapped place error:', m || e)
  return tt('Order failed — please check your details and try again', '下单失败，请检查填写信息后重试')
}

function utmOf() {
  const q = route.query
  const out = {}
  for (const k of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']) {
    if (q[k]) out[k] = String(q[k])
  }
  if (Object.keys(out).length) return out
  /* 路由无 utm（用户中途落地丢失 query）→ 回落 gm_utm 存储（router afterEach 捕获，7 天有效） */
  try {
    const d = JSON.parse(localStorage.getItem('gm_utm') || 'null')
    if (d && d.values) {
      if (d.ts && Date.now() - d.ts < 7 * 86400000) return d.values
      localStorage.removeItem('gm_utm')
    }
  } catch (_) { /* 隐私模式/存储损坏即弃 */ }
  return null
}

async function saveAddrBook() {
  const f = form.value
  try {
    await req('POST', '/api/account/addresses', {
      full_name: (f.fname + ' ' + f.lname).trim(),
      line1: f.addr1.trim(),
      line2: f.addr2.trim() || null,
      city: f.city.trim(),
      state: (f.state || '').trim().toUpperCase() || null,
      zip: (f.zip || '').trim(),
      country: country.value,
      phone: f.phone || null,
      is_default: false,
    })
  } catch (_) { /* 保存失败静默：不影响下单 */ }
}

/* 结算草稿（sessionStorage）：hosted 支付跳转/回跳或误刷新后恢复表单状态；place 成功即清 */
const DRAFT_KEY = 'gm_checkout_draft'
function saveDraft() {
  try {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({
      form: form.value, country: country.value, shipMethod: shipMethod.value,
      paySel: paySel.value, gift: gift.value, giftMsg: giftMsg.value,
      pointsInput: pointsInput.value, appliedGc: appliedGc.value,
      appliedCode: appliedCode.value, code: code.value,
    }))
  } catch (_) { /* 隐私模式 */ }
}
function restoreDraft() {
  try {
    const d = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || 'null')
    if (!d) return
    if (d.form) form.value = { ...form.value, ...d.form }
    if (d.country) country.value = d.country
    if (d.shipMethod) shipMethod.value = d.shipMethod
    if (d.paySel) paySel.value = d.paySel
    if (d.gift != null) gift.value = !!d.gift
    if (d.giftMsg) giftMsg.value = d.giftMsg
    if (d.pointsInput) pointsInput.value = d.pointsInput
    if (d.appliedGc) appliedGc.value = d.appliedGc
    if (d.appliedCode) appliedCode.value = d.appliedCode
    if (d.code) code.value = d.code
  } catch (_) { /* 草稿损坏即弃 */ }
}
function clearDraft() { try { sessionStorage.removeItem(DRAFT_KEY) } catch (_) { /* 隐私模式 */ } }

async function place() {
  if (placing.value) return
  if (noPayChannel.value) {
    ui.toast(tt('Payment is temporarily unavailable — please try again later', '支付通道暂不可用，请稍后再试'), 'error')
    return
  }
  if (!validate()) {
    /* 地址簿地址选中时表单字段隐藏：校验失败改为内联错误列出无效字段（fixAddr 引导修正） */
    const hidden = ['fname', 'addr1', 'city', 'state', 'zip', 'country']
    const bad = selAddr.value > 0 ? hidden.filter((k) => errors.value[k]) : []
    addrErrFields.value = bad.length ? bad : null
    ui.toast(i18n.t('co.incomplete'), 'error')
    return
  }
  addrErrFields.value = null
  /* 折扣码无效时拦截（后端 place 也会 409，前端先给中文原因） */
  if (appliedCode.value && pv.value && !pv.value.code_valid) {
    ui.toast(reasonText(pv.value.code_reason), 'error'); return
  }
  placing.value = true
  try {
    try { await cart.refresh() } catch (_) { /* 拉取失败：退回本地 items 判空 */ }
    if (!cart.items.length) throw Object.assign(new Error('empty'), { data: { detail: 'empty_cart' } })
    /* 失效/缺货/超库存校验基于 refresh 后的最新 cart.items（本地缓存可能滞后） */
    if (cart.items.some((i) => i.inactive)) {
      ui.toast(tt('Some items are no longer available — please remove them first', '部分商品已下架，请先移除后再下单'), 'error')
      return
    }
    if (cart.items.some((i) => (i.stock || 0) <= 0)) {
      ui.toast(tt('Some items are out of stock — please remove them first', '部分商品缺货，请先移除后再下单'), 'error')
      return
    }
    const overRow = cart.items.find((i) => i.stock > 0 && i.qty > i.stock)
    if (overRow) {
      ui.toast(tt(`Only ${overRow.stock} left of "${overRow.title}" — please adjust the quantity`, `「${overRow.title}」库存仅剩 ${overRow.stock} 件，请调整数量`), 'error')
      return
    }
    const f = form.value
    const body = {
      email: f.email.trim(),
      address: {
        full_name: (f.fname + ' ' + f.lname).trim(),
        line1: f.addr1.trim(), line2: f.addr2.trim() || null,
        city: f.city.trim(), state: (f.state || '').trim().toUpperCase() || null, zip: (f.zip || '').trim(),
        country: country.value, phone: f.phone || null,
      },
      shipping_method: shipMethod.value,
    }
    /* 折扣码/礼品卡无条件携带（preview 网络失败时不再静默丢折扣；
       无效码/失效卡由后端 place 409 拦截并回给明确原因） */
    if (appliedCode.value) body.code = appliedCode.value
    if (pointsApplied.value > 0 && auth.isLoggedIn) body.points = pointsApplied.value
    if (appliedGc.value) body.gift_card_code = appliedGc.value
    if (f.note.trim()) body.note = f.note.trim().slice(0, 255)
    if (gift.value) {
      body.gift_flag = 1
      if (giftMsg.value.trim()) body.gift_message = giftMsg.value.trim().slice(0, 255)
    }
    const utm = utmOf()
    if (utm) body.utm = utm
    const d = await req('POST', '/api/checkout/place', body)
    /* 下单成功即清折扣码残留（与 SuccessView 同一 key/方式）与结算草稿，避免弃单后旧码被自动带上 */
    try { localStorage.removeItem('gm_applied_code') } catch (_) { /* 隐私模式 */ }
    clearDraft()
    if (auth.isLoggedIn && selAddr.value === 0 && saveAddr.value) saveAddrBook()
    /* 记住支付方式选择：SuccessView 二次支付沿用同一 provider */
    try { localStorage.setItem('gm_pay_provider', paySel.value || '') } catch (_) { /* 隐私模式 */ }
    /* 支付意向 + mock 支付（演示通道；真实 provider 由 webhook 回调，不 mock）；
       createOrderIntent 内与 methods 对账并在 provider_unavailable 时去参重试 */
    const useMock = paySel.value === 'mock'
    try {
      const intent = await createOrderIntent(d.order_no, f.email.trim(), paySel.value)
      /* 真实通道仅返回 client_secret 而无 redirect_url：本页无法完成支付 →
         待支付订单转 /success 托管（有"立即支付"入口），不再滞留在已清空的购物车页 */
      if (intentNoChannel(intent)) {
        ui.toast(i18n.t('pay.unsupported_channel'), 'error')
        router.push({ path: '/success', query: { no: d.order_no, email: f.email.trim() } })
        return
      }
      /* hosted checkout：非 mock 通道返回 redirect_url 时跳转 provider 收银台；
         跳转后 3s 未离页则兜底恢复按钮并提示（/success 页有待支付按钮可手动重试） */
      if (!useMock && intent && intent.redirect_url) {
        window.location.href = intent.redirect_url
        await new Promise((r) => setTimeout(r, 3000))
        placing.value = false
        ui.toast(tt('Redirecting to payment… if nothing happened, please retry', '正在跳转支付…若未打开请重试'), 'error')
        router.push({ path: '/success', query: { no: d.order_no, email: f.email.trim() } })
        return
      }
      if (useMock) await req('POST', '/api/payments/mock-pay', { order_no: d.order_no, email: f.email.trim(), succeed: true })
    } catch (e) {
      const m = (e.data && e.data.detail) || e.message || ''
      ui.toast((m ? m + ' · ' : '') + tt('Payment not completed — you can pay from your order', '支付未完成，可到订单中手动支付'), 'error')
    }
    router.push({ path: '/success', query: { no: d.order_no, email: f.email.trim() } })
  } catch (e) {
    ui.toast(mapPlaceError(e), 'error')
  } finally { placing.value = false }
}

/* 任一计价因子变化 → 重算 preview（税率随州、运费随方式/国家、码/积分/礼品卡随输入） */
watch(() => form.value.email, schedulePreview)
watch(() => form.value.state, schedulePreview)
watch(() => cart.items.map((i) => i.vid + ':' + i.qty).join('|'), schedulePreview)
watch([country, shipMethod, appliedCode, appliedGc, pointsApplied, () => auth.isLoggedIn], schedulePreview)
watch([form, country, shipMethod, paySel, gift, giftMsg, pointsInput, appliedGc, appliedCode, code], saveDraft, { deep: true })
watch(country, loadShipMethods)

/* hosted 支付取消回跳（?canceled=1）：订单已生成待付，购物车已清 → 给保留订单出口 */
const canceled = computed(() => String(route.query.canceled || '') === '1')

onMounted(async () => {
  cart.refresh().catch(() => {})
  restoreDraft()
  if (auth.user) form.value.email = auth.user.email || ''
  if (auth.isLoggedIn) auth.fetchPoints().catch(() => {})
  loadAddrs()
  /* 购物车页带入的折扣码（?code= 优先，localStorage gm_applied_code 兜底） */
  let savedCode = ''
  try { savedCode = (localStorage.getItem('gm_applied_code') || '').trim().toUpperCase() } catch (_) { /* 隐私模式 */ }
  const q = String(route.query.code || '').trim().toUpperCase() || savedCode
  if (q) { code.value = q; appliedCode.value = q }
  loadShipMethods()
  loadPayMethods()
  runPreview()
})

const itemsView = computed(() => {
  if (pv.value && pv.value.items) {
    return pv.value.items.map((l) => ({
      id: l.variant_id, img: l.image, qty: l.qty, stock: l.stock, inactive: false,
      title: (l.title || '').split(' · ')[0], variant: (l.title || '').split(' · ')[1] || '',
      lineC: l.line_subtotal,
    }))
  }
  return cart.items.map((i) => ({ id: i.vid, img: i.img, qty: i.qty, stock: i.stock, inactive: !!i.inactive, title: i.title, variant: i.variant, lineC: (i.priceC || Math.round(i.price * 100)) * i.qty }))
})
/* 无可用支付通道（非 dev 且未配置真实 provider，或 methods 拉取失败且无选项）：禁止下单，避免订单悬挂等超时关单 */
const noPayChannel = computed(() => payDefault.value === 'none' || (methodsErr.value && !payProviders.value.length))
/* 一键移除失效（下架/删除）商品行：解除 preview/place 409 死锁 */
async function removeInactive() {
  const dead = cart.items.filter((i) => i.inactive).map((i) => i.vid)
  for (const vid of dead) await cart.remove(vid, ui)
}
const totalC = computed(() => (pv.value && pv.value.grand_total != null
  ? pv.value.grand_total
  : cart.subtotalC + (selMethod.value ? selMethod.value.price : 499)))
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head"><h2 class="section-title">{{ i18n.t('cart.checkout') }}</h2></div>

      <div v-if="canceled && cart.items.length" class="ship-bar" style="margin-bottom:18px">
        {{ tt('Previous payment was canceled — that order is saved; you can pay it anytime from your order page.', '上次支付已取消，订单已保留，可随时在订单页完成支付。') }}
      </div>

      <div v-if="canceled && !cart.items.length" class="card" style="text-align:center;padding:42px 24px;margin-bottom:18px">
        <div style="font-size:40px;margin-bottom:10px">💳</div>
        <b style="display:block;font-size:17px;margin-bottom:6px">{{ tt('Payment canceled — your order is saved', '支付已取消，你的订单已保留') }}</b>
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:16px">
          {{ tt('Complete the payment anytime from your order page.', '可随时在订单页继续完成支付。') }}
        </p>
        <router-link class="btn btn-primary" :to="auth.isLoggedIn ? '/account/orders' : '/track'">
          {{ auth.isLoggedIn ? tt('View my orders', '我的订单') : tt('Track your order', '查询订单') }}
        </router-link>
      </div>

      <div v-if="!cart.items.length" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">🛒</div>
        <p style="margin-bottom:18px">{{ i18n.t('co.empty') }}</p>
        <router-link class="btn btn-primary" to="/store">{{ i18n.t('cart.shop') }}</router-link>
      </div>

      <div v-else class="grid-m-1" style="display:grid;grid-template-columns:1.5fr 1fr;gap:32px;align-items:start">
        <div style="display:grid;gap:18px">
          <!-- 联系 & 地址 -->
          <div class="card" style="padding:22px">
            <h3 class="co-step"><i class="step-b">1</i>{{ i18n.t('co.step1') }}</h3>
            <div class="field" :class="{ error: errors.email }">
              <label>{{ i18n.t('co.email') }} *</label>
              <input v-model="form.email" class="input" :class="{ error: errors.email }" type="email" placeholder="you@example.com" autocomplete="email">
              <div class="field-msg">{{ i18n.t('co.emailErr') }}</div>
            </div>
            <!-- 地址簿：登录且有保存地址时展示（设计文档 前端完整设计文档 §checkout：登录用户地址簿选择/新增） -->
            <template v-if="savedAddrs.length">
              <label v-for="a in savedAddrs" :key="a.id" class="pay-row addr-sel" :class="{ on: selAddr === a.id }" style="cursor:pointer;align-items:flex-start">
                <input v-model="selAddr" type="radio" :value="a.id" style="display:none" @change="pickAddr(a)">
                <span style="flex:1;min-width:0">
                  <b>{{ a.full_name }}</b>
                  <span v-if="a.is_default" class="tag tag-paid" style="margin-left:6px">{{ i18n.t('co.defaultTag') }}</span>
                  <div style="color:var(--gray);font-size:12.5px;margin-top:3px">
                    {{ a.line1 }}{{ a.line2 ? ' ' + a.line2 : '' }}, {{ a.city }}{{ a.state ? ', ' + a.state : '' }} {{ a.zip }} · {{ a.country }}
                    <template v-if="a.phone"> · {{ a.phone }}</template>
                  </div>
                </span>
              </label>
              <label class="pay-row addr-sel" :class="{ on: selAddr === 0 }" style="cursor:pointer">
                <input v-model="selAddr" type="radio" :value="0" style="display:none" @change="pickNewAddr">
                <b style="color:var(--plum)">＋ {{ i18n.t('co.addrNew') }}</b>
              </label>
              <div v-if="addrErrFields" style="font-size:12.5px;color:var(--error);margin:6px 0 0;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                <span>{{ i18n.t('co.addrErr', addrErrFields.map((k) => i18n.t(ADDR_FIELD_LABELS[k] || k)).join(', ')) }}</span>
                <button class="btn btn-secondary btn-sm" type="button" @click="fixAddr">{{ i18n.t('co.addrErrNew') }}</button>
              </div>
            </template>
            <template v-if="selAddr === 0">
            <div class="co-2col">
              <div class="field" :class="{ error: errors.fname }"><label>{{ i18n.t('co.fname') }} *</label><input v-model="form.fname" class="input" :class="{ error: errors.fname }" autocomplete="given-name"></div>
              <div class="field"><label>{{ i18n.t('co.lname') }}</label><input v-model="form.lname" class="input" autocomplete="family-name"></div>
            </div>
            <div class="field" :class="{ error: errors.addr1 }"><label>{{ i18n.t('co.addr') }} *</label><input v-model="form.addr1" class="input" :class="{ error: errors.addr1 }" autocomplete="address-line1" :placeholder="i18n.t('co.addrPh')"></div>
            <div class="field"><label>{{ i18n.t('co.addr2') }}</label><input v-model="form.addr2" class="input" autocomplete="address-line2"></div>
            <div class="co-3col">
              <div class="field" :class="{ error: errors.city }"><label>{{ i18n.t('co.city') }} *</label><input v-model="form.city" class="input" :class="{ error: errors.city }" autocomplete="address-level2"></div>
              <div class="field" :class="{ error: errors.state }">
                <label>{{ country === 'US' ? i18n.t('co.state') : i18n.t('co.stateProv') }} *</label>
                <select v-if="country === 'US'" v-model="form.state" class="input" :class="{ error: errors.state }">
                  <option value="">—</option>
                  <option v-for="s in US_STATES" :key="s" :value="s">{{ s }}</option>
                </select>
                <input v-else v-model="form.state" class="input" :class="{ error: errors.state }" placeholder="ON">
                <div v-if="country === 'US'" class="field-msg">{{ tt('Select a state', '请选择州') }}</div>
                <div v-else class="field-msg">{{ tt('Province / state required for international shipping', '国际配送需要省/州信息') }}</div>
              </div>
              <div class="field" :class="{ error: errors.zip }"><label>{{ i18n.t('co.zip') }} *</label><input v-model="form.zip" class="input" :class="{ error: errors.zip }" autocomplete="postal-code"></div>
            </div>
            <div class="co-2col">
              <div class="field">
                <label>{{ i18n.t('co.country') }}</label>
                <select v-model="country" class="input" @change="form.state = ''">
                  <option v-for="c in COUNTRIES" :key="c" :value="c">{{ c }}</option>
                </select>
              </div>
              <div class="field"><label>{{ i18n.t('co.phone') }}</label><input v-model="form.phone" class="input" type="tel" autocomplete="tel"></div>
            </div>
            <label v-if="auth.isLoggedIn" style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer;margin:-6px 0 0">
              <input v-model="saveAddr" type="checkbox" style="width:16px;height:16px">
              {{ tt('Save this address to my address book', '保存到我的地址簿') }}
            </label>
            </template>
          </div>

          <!-- 配送 -->
          <div class="card" style="padding:22px">
            <h3 class="co-step"><i class="step-b">2</i>{{ i18n.t('co.step2') }}</h3>
            <label v-for="m in shipMethods" :key="m.method" class="pay-row" :class="{ on: shipMethod === m.method }" style="cursor:pointer">
              <input v-model="shipMethod" type="radio" :value="m.method" style="display:none">
              <b>{{ methodLabel(m) }}</b>
              <span style="color:var(--gray);font-size:13px">
                {{ (m.carrier || '').toUpperCase() }} · {{ m.eta_min_days }}–{{ m.eta_max_days }} {{ i18n.t('co.days') }}
                <template v-if="m.free_over"> · {{ i18n.t('co.freeOver', money(m.free_over)) }}</template>
              </span>
              <b style="margin-left:auto;font-variant-numeric:tabular-nums">{{ money(m.price) }}</b>
            </label>
            <p v-if="!shipMethods.length" style="font-size:13px;color:var(--gray)">{{ i18n.t('co.loadingShip') }}</p>
          </div>

          <!-- 支付 -->
          <div class="card" style="padding:22px">
            <h3 class="co-step"><i class="step-b">3</i>{{ i18n.t('co.step3') }}</h3>
            <label v-for="p in payProviders" :key="p.id" class="pay-row" :class="{ on: paySel === p.id }" style="cursor:pointer">
              <input v-model="paySel" type="radio" :value="p.id" style="display:none">
              <b>{{ p.id === 'mock' ? '💳' : '🅿️' }} {{ p.name }}</b>
              <span v-if="p.id === payDefault" class="tag tag-paid" style="margin-left:8px">{{ i18n.t('co.defaultTag') }}</span>
              <span v-if="p.klarna" class="pay-pill" style="margin-left:8px">KLARNA</span>
            </label>
            <div v-if="methodsErr" style="font-size:12.5px;color:var(--error);margin-top:8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <span>{{ i18n.t('co.payLoadErr') }}</span>
              <button class="btn btn-secondary btn-sm" type="button" @click="loadPayMethods">{{ i18n.t('co.payRetry') }}</button>
            </div>
            <p v-if="noPayChannel" style="font-size:12.5px;color:var(--error);margin-top:8px">
              {{ tt('Online payment is temporarily unavailable. Your order can still be placed later — please try again soon.', '在线支付通道暂不可用，请稍后再来下单。') }}
            </p>
            <p style="font-size:12px;color:var(--gray);margin-top:12px">
              🔒 {{ i18n.t('co.payNote') }}
            </p>
          </div>

          <!-- 备注 / 礼物 / 积分 / 礼品卡 -->
          <div class="card" style="padding:22px;display:grid;gap:14px">
            <div class="field" style="margin:0">
              <label>{{ i18n.t('co.note') }} ({{ form.note.length }}/255)</label>
              <textarea v-model="form.note" class="input" rows="2" maxlength="255" :placeholder="i18n.t('co.notePh')"></textarea>
            </div>

            <label style="display:flex;gap:10px;align-items:center;font-size:13.5px;cursor:pointer">
              <input v-model="gift" type="checkbox" style="width:16px;height:16px">
              🎁 {{ i18n.t('co.gift') }}
            </label>
            <div v-if="gift" class="field" style="margin:0">
              <label>{{ i18n.t('co.giftMsg') }} ({{ giftMsg.length }}/255)</label>
              <textarea v-model="giftMsg" class="input" rows="2" maxlength="255" :placeholder="i18n.t('co.giftPh')"></textarea>
            </div>

            <div v-if="auth.isLoggedIn" style="border-top:1px solid var(--gray-light);padding-top:14px">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:13.5px;margin-bottom:8px">
                <b>⭐ {{ i18n.t('co.pointsTitle') }}</b>
                <span style="color:var(--gray);font-size:12px">{{ i18n.t('co.ptsAvail', pointsUsable.toLocaleString()) }}</span>
              </div>
              <div style="display:flex;gap:8px;align-items:center">
                <input v-model="pointsInput" class="input" type="number" min="0" :max="pointsUsable" placeholder="0" style="width:130px" @blur="clampPoints">
                <span style="font-size:12.5px;color:var(--gray)">pts</span>
                <button class="btn btn-secondary btn-sm" type="button" @click="useMaxPoints">{{ i18n.t('co.max') }}</button>
                <b v-if="pv && pv.points_discount" style="margin-left:auto;color:var(--success)">−{{ money(pv.points_discount) }}</b>
              </div>
              <p style="font-size:11.5px;color:var(--gray);margin-top:6px">
                {{ i18n.t('co.ptsRule') }}
              </p>
            </div>
            <div v-else style="border-top:1px solid var(--gray-light);padding-top:14px;font-size:13.5px;color:var(--gray)">
              ⭐ <router-link to="/login?next=/checkout" style="color:var(--plum);text-decoration:underline">{{ i18n.t('co.login') }}</router-link>
              {{ i18n.t('co.loginHint') }}
            </div>

            <div style="border-top:1px solid var(--gray-light);padding-top:14px">
              <label style="font-size:13.5px;font-weight:700;display:block;margin-bottom:8px">💳 {{ i18n.t('co.giftcard') }}</label>
              <div v-if="appliedGc && pv && pv.gift_card && !pv.gift_card_error" style="display:flex;align-items:center;justify-content:space-between;gap:8px;background:var(--pale-success);border-radius:10px;padding:10px 12px;font-size:13px">
                <span><b>{{ appliedGc }}</b> · {{ i18n.t('co.balance', money(pv.gift_card.balance)) }}
                  <b v-if="pv.giftcard_discount" style="color:var(--success)"> −{{ money(pv.giftcard_discount) }}</b></span>
                <button type="button" class="gc-x" @click="removeGiftCard">×</button>
              </div>
              <div v-else style="display:flex;gap:8px">
                <input v-model="gcInput" class="input" :placeholder="i18n.t('co.gcPh')" style="text-transform:uppercase" @keyup.enter="applyGiftCard">
                <button class="btn btn-secondary" type="button" @click="applyGiftCard">{{ i18n.t('promo.apply') }}</button>
              </div>
              <p v-if="pv && pv.gift_card_error" style="font-size:12px;color:var(--error);margin-top:6px">{{ giftCardText(pv.gift_card_error) }}</p>
            </div>
          </div>
        </div>

        <!-- 摘要 -->
        <div class="card co-summary">
          <h3 style="font-size:16px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center">
            {{ i18n.t('co.summary') }}
            <span v-if="pvBusy" style="font-size:11px;color:var(--gray)">⟳ {{ i18n.t('co.updating') }}</span>
          </h3>
          <div class="sum-mask" :class="{ 'sum-fade': itemsView.length > 4 }">
            <div style="display:grid;gap:12px;max-height:240px;overflow-y:auto">
              <div v-for="i in itemsView" :key="i.id" style="display:flex;gap:10px;align-items:center">
                <div style="position:relative">
                  <img :src="i.img" :alt="i.title" style="width:48px;height:48px;border-radius:8px;object-fit:cover" loading="lazy" @error="imgFallback">
                  <span style="position:absolute;top:-6px;right:-6px;background:var(--ink);color:#fff;font-size:10px;font-weight:700;min-width:16px;height:16px;border-radius:8px;display:flex;align-items:center;justify-content:center">{{ i.qty }}</span>
                </div>
                <div style="flex:1;min-width:0;font-size:13px">
                  <b>{{ i.title }}</b><span v-if="i.inactive" style="color:var(--error);font-size:11px;font-weight:700;margin-left:6px">{{ tt('Unavailable', '已下架') }}</span>
                  <span v-else-if="(i.stock || 0) <= 0" style="color:var(--error);font-size:11px;font-weight:700;margin-left:6px">{{ tt('Out of stock', '缺货') }}</span>
                  <span v-else-if="i.qty > i.stock" style="color:var(--error);font-size:11px;font-weight:700;margin-left:6px">{{ tt('Only ' + i.stock + ' left', '仅剩 ' + i.stock + ' 件') }}</span>
                  <div style="color:var(--gray);font-size:12px">{{ i.variant }}</div>
                </div>
                <b style="font-size:13px;font-variant-numeric:tabular-nums">{{ money(i.lineC) }}</b>
              </div>
            </div>
          </div>
          <div style="display:flex;gap:8px;margin:16px 0">
            <input v-model="code" class="input" :placeholder="i18n.t('promo.codePh')" style="text-transform:uppercase" @keyup.enter="applyCode">
            <button class="btn btn-secondary" :disabled="pvBusy" @click="applyCode">{{ pvBusy ? '…' : i18n.t('promo.apply') }}</button>
          </div>
          <div v-if="appliedCode && pv" style="display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12.5px;margin:-8px 0 12px"
               :style="{ color: pv.code_valid ? 'var(--success)' : 'var(--error)' }">
            <span>{{ appliedCode }} · {{ pv.code_valid
              ? (pv.free_shipping ? i18n.t('promo.freeShipOk') : `−${money(pv.code_discount)}`)
              : reasonText(pv.code_reason) }}</span>
            <button class="gc-x" @click="removeCode">×</button>
          </div>
          <div v-if="pvError" style="font-size:12.5px;color:var(--error);margin:-6px 0 12px">{{ pvError }}</div>

          <div style="display:grid;gap:8px;font-size:14px">
            <div class="srow"><span>{{ i18n.t('cart.subtotal') }}</span><b class="num">{{ money(pv ? pv.subtotal : cart.subtotalC) }}</b></div>
            <div v-if="pv && pv.bundle_discount" class="srow ok"><span>🎁 {{ i18n.t('cart.bundleDiscount') }}</span><span>−{{ money(pv.bundle_discount) }}</span></div>
            <div v-if="pv && pv.code_valid && pv.code_discount" class="srow ok"><span>{{ i18n.t('cart.codeRow') }} {{ pv.code }}</span><span>−{{ money(pv.code_discount) }}</span></div>
            <div v-if="pv && pv.points_discount" class="srow ok"><span>⭐ {{ i18n.t('co.points') }} ({{ pv.points_applied }})</span><span>−{{ money(pv.points_discount) }}</span></div>
            <div v-if="pv && pv.giftcard_discount" class="srow ok"><span>💳 {{ i18n.t('co.giftcard') }}</span><span>−{{ money(pv.giftcard_discount) }}</span></div>
            <div class="srow">
              <span>{{ i18n.t('co.shipping') }}</span>
              <b class="num">
                <span v-if="pv && pv.shipping_fee === 0" style="color:var(--success)">{{ i18n.t('cart.free') }}</span>
                <template v-else>{{ money(pv ? pv.shipping_fee : (selMethod ? selMethod.price : 499)) }}</template>
              </b>
            </div>
            <div v-if="pv && pv.tax != null" class="srow">
              <span>{{ i18n.t('co.tax') }}<template v-if="pv.tax_state"> · {{ pv.tax_state }} {{ (pv.tax_rate * 100).toFixed(2) }}%</template></span>
              <b class="num">{{ money(pv.tax) }}</b>
            </div>
            <div v-else class="srow"><span>{{ i18n.t('co.tax') }}</span><span style="font-size:12px;color:var(--gray)">{{ i18n.t('co.taxEst') }}</span></div>
          </div>
          <div v-if="shipHint" class="ship-bar" style="margin-top:12px;font-size:12.5px" v-html="shipHint"></div>
          <div style="display:flex;justify-content:space-between;font-weight:800;font-size:17px;margin:14px 0;padding-top:12px;border-top:1px solid var(--gray-light)">
            <span>{{ i18n.t('cart.total') }}</span>
            <span style="color:var(--plum);font-variant-numeric:tabular-nums">
              {{ money(totalC) }}<span v-if="!pv" style="font-size:11px;color:var(--gray);font-weight:400;margin-left:4px">{{ tt('≈ estimate, final at checkout', '≈ 估算，以下单为准') }}</span>
            </span>
          </div>
          <button v-if="cart.items.some((i) => i.inactive)" class="btn btn-secondary btn-block" style="margin-bottom:10px" type="button" @click="removeInactive">
            {{ tt('Remove unavailable items', '移除已下架商品') }}
          </button>
          <button class="btn btn-primary btn-block btn-lg" :class="{ loading: placing }" :disabled="placing || noPayChannel" @click="place">
            {{ placing ? '' : i18n.t('co.place') + ' · ' + money(totalC) }}
          </button>
          <p style="font-size:11.5px;color:var(--gray);margin-top:10px;text-align:center">
            {{ i18n.t('co.termsPre') }}
            <router-link to="/terms" style="text-decoration:underline">{{ i18n.t('footer.terms') }}</router-link> &
            <router-link to="/returns-policy" style="text-decoration:underline">{{ i18n.t('co.returnPolicy') }}</router-link>.
          </p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.pay-row { display: flex; align-items: center; gap: 10px; border: 1.5px solid var(--gray-light); border-radius: 10px; padding: 12px 14px; margin-bottom: 10px; transition: all .15s; }
.pay-row:hover { border-color: var(--rose); }
.pay-row.on { border-color: var(--plum); background: var(--rose-pale); box-shadow: inset 3px 0 0 var(--plum); }
/* v19 移动端补漏：地址行栅格收编为类（原 inline 3 列在 375px 每列仅约 85px，state/zip 挤压）；
   ≤640px 折单列，661–768px 三列仍可容纳（~200px/列） */
.co-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.co-3col { display: grid; grid-template-columns: 1fr 1fr .7fr; gap: 12px; }
@media (max-width: 640px) { .co-2col, .co-3col { grid-template-columns: 1fr; } }
/* 摘要卡吸顶：原 top:20px 会钻到 64px 吸顶头部之下（标题被遮半截）——对齐 .acct-nav/.policy-side 的 84px；
   移动端单列时摘要在表单下方，吸顶只会半截露在头部下，取消 */
.co-summary { position: sticky; top: 84px; padding: 22px; }
@media (max-width: 768px) { .co-summary { position: static; } }
/* 三步骤号：28px 圆形徽标（rose-pale 底 plum 字） */
.co-step { display: flex; align-items: center; gap: 10px; font-size: 16px; margin-bottom: 14px; }
.step-b { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 50%; background: var(--rose-pale); color: var(--plum); font-style: normal; font-size: 14px; font-weight: 700; flex: none; }
/* 摘要列表底部渐变遮罩（仅溢出时出现） */
.sum-mask { position: relative; }
.sum-fade::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 26px; background: linear-gradient(rgba(255,255,255,0), #fff); pointer-events: none; }
.srow { display: flex; justify-content: space-between; align-items: baseline; }
.srow .num { font-variant-numeric: tabular-nums; }
.srow.ok { color: var(--success); }
.gc-x { border: none; background: var(--gray-light); color: var(--gray); width: 24px; height: 24px; border-radius: 50%; font-size: 14px; line-height: 1; cursor: pointer; flex: none; }
.gc-x:hover { background: var(--error); color: #fff; }
</style>
