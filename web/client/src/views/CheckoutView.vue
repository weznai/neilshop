<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req, intentNoChannel } from '../api/client'
import { i18n } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'

const cart = useCartStore()
const ui = useUiStore()
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const US_STATES = ['AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY']
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

function fillAddr(a) {
  const f = form.value
  /* 地址簿只存 full_name：首词作名、其余作姓（place 时再拼回，无损） */
  const parts = (a.full_name || '').trim().split(/\s+/)
  f.fname = parts.shift() || ''
  f.lname = parts.join(' ')
  f.addr1 = a.line1 || ''
  f.addr2 = a.line2 || ''
  f.city = a.city || ''
  f.state = a.state || ''
  f.zip = a.zip || ''
  f.phone = a.phone || ''
  country.value = (a.country || 'US').toUpperCase()
}

function pickAddr(a) {
  selAddr.value = a.id
  fillAddr(a)
  errors.value = {}
}

function pickNewAddr() {
  selAddr.value = 0
  const f = form.value
  f.fname = ''; f.lname = ''; f.addr1 = ''; f.addr2 = ''
  f.city = ''; f.state = ''; f.zip = ''; f.phone = ''
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
function removeCode() { appliedCode.value = null; code.value = ''; try { localStorage.removeItem('gm_applied_code') } catch (_) { /* 隐私模式 */ } runPreview() }

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
  }
}
function removeGiftCard() { appliedGc.value = null; gcInput.value = ''; runPreview() }

function useMaxPoints() {
  const coverable = pv.value
    ? Math.max(0, pv.value.subtotal - pv.value.discount_total - (pv.value.giftcard_discount || 0))
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
  } catch (_) { shipMethods.value = FALLBACK_METHODS }
  /* 国家切换后原方式可能不存在（如该国无 express 模板）→ 回落首个可选 */
  if (shipMethods.value.length && !shipMethods.value.some((m) => m.method === shipMethod.value)) {
    shipMethod.value = shipMethods.value[0].method
  }
}
async function loadPayMethods() {
  try {
    const d = await req('GET', '/api/payments/methods')
    payProviders.value = d.providers || []
    payDefault.value = d.default || 'mock'
    if (!paySel.value || !payProviders.value.some((p) => p.id === paySel.value)) {
      paySel.value = payDefault.value
    }
  } catch (_) {
    payProviders.value = [{ id: 'mock', name: 'Mock Pay (dev)', klarna: false }]
    payDefault.value = 'mock'; paySel.value = 'mock'
  }
}

const methodLabel = (m) => i18n.t(m.method === 'express' ? 'co.express' : 'co.standard')
const freeShipThreshold = computed(() => {
  const std = shipMethods.value.find((m) => m.method === 'standard')
  return (std && std.free_over) || 3500 /* settings.free_shipping_threshold 默认 3500 */
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
  if (!(f.zip || '').trim()) e.zip = true
  else if (country.value === 'US' && !/^\d{5}(-\d{4})?$/.test(f.zip.trim())) e.zip = true
  errors.value = e
  const ok = Object.keys(e).length === 0
  if (!ok) {
    const el = document.querySelector('.field.error')
    if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
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
  return m
}

function utmOf() {
  const q = route.query
  const out = {}
  for (const k of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']) {
    if (q[k]) out[k] = String(q[k])
  }
  return Object.keys(out).length ? out : null
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

async function place() {
  if (placing.value) return
  if (!validate()) { ui.toast(i18n.t('co.incomplete'), 'error'); return }
  /* 折扣码无效时拦截（后端 place 也会 409，前端先给中文原因） */
  if (appliedCode.value && pv.value && !pv.value.code_valid) {
    ui.toast(reasonText(pv.value.code_reason), 'error'); return
  }
  if (itemsView.value.some((i) => (i.stock || 0) <= 0)) {
    ui.toast(tt('Some items are out of stock — please remove them first', '部分商品缺货，请先移除后再下单'), 'error')
    return
  }
  placing.value = true
  try {
    try { await cart.refresh() } catch (_) { /* 拉取失败：退回本地 items 判空 */ }
    if (!cart.items.length) throw Object.assign(new Error('empty'), { data: { detail: 'empty_cart' } })
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
    if (appliedCode.value && pv.value && pv.value.code_valid) body.code = appliedCode.value
    if (pointsApplied.value > 0 && auth.isLoggedIn) body.points = pointsApplied.value
    if (appliedGc.value && pv.value && !pv.value.gift_card_error) body.gift_card_code = appliedGc.value
    if (f.note.trim()) body.note = f.note.trim().slice(0, 255)
    if (gift.value) {
      body.gift_flag = 1
      if (giftMsg.value.trim()) body.gift_message = giftMsg.value.trim().slice(0, 255)
    }
    const utm = utmOf()
    if (utm) body.utm = utm
    const d = await req('POST', '/api/checkout/place', body)
    /* 下单成功即清折扣码残留（与 SuccessView 同一 key/方式），避免弃单后旧码被自动带上 */
    try { localStorage.removeItem('gm_applied_code') } catch (_) { /* 隐私模式 */ }
    if (auth.isLoggedIn && selAddr.value === 0 && saveAddr.value) await saveAddrBook()
    /* 支付意向 + mock 支付（演示通道；真实 provider 由 webhook 回调，不 mock） */
    const useMock = paySel.value === 'mock'
    try {
      const ib = { order_no: d.order_no, email: f.email.trim() }
      if (paySel.value && paySel.value !== 'mock' && paySel.value !== payDefault.value) ib.provider = paySel.value
      const intent = await req('POST', '/api/payments/create-intent', ib)
      /* 真实通道仅返回 client_secret 而无 redirect_url：本页无法完成支付，提示并留在当前页 */
      if (intentNoChannel(intent)) {
        ui.toast(i18n.t('pay.unsupported_channel'), 'error')
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
watch(country, loadShipMethods)

onMounted(async () => {
  cart.refresh().catch(() => {})
  if (auth.user) form.value.email = auth.user.email || ''
  if (auth.isLoggedIn) auth.fetchPoints().catch(() => {})
  loadAddrs()
  /* 购物车页带入的折扣码（?code=） */
  const q = String(route.query.code || '').trim().toUpperCase()
  if (q) { code.value = q; appliedCode.value = q }
  loadShipMethods()
  loadPayMethods()
  runPreview()
})

const itemsView = computed(() => {
  if (pv.value && pv.value.items) {
    return pv.value.items.map((l) => ({
      id: l.variant_id, img: l.image, qty: l.qty, stock: l.stock,
      title: (l.title || '').split(' · ')[0], variant: (l.title || '').split(' · ')[1] || '',
      lineC: l.line_subtotal,
    }))
  }
  return cart.items.map((i) => ({ id: i.vid, img: i.img, qty: i.qty, stock: i.stock, title: i.title, variant: i.variant, lineC: (i.priceC || Math.round(i.price * 100)) * i.qty }))
})
const totalC = computed(() => (pv.value && pv.value.grand_total != null
  ? pv.value.grand_total
  : cart.subtotalC + (shipMethod.value === 'express' ? 1499 : 499)))
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head"><h2 class="section-title">{{ i18n.t('cart.checkout') }}</h2></div>

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
                <label>{{ country === 'US' ? i18n.t('co.state') : i18n.t('co.stateProv') }}<template v-if="country === 'US'"> *</template></label>
                <select v-if="country === 'US'" v-model="form.state" class="input" :class="{ error: errors.state }">
                  <option value="">—</option>
                  <option v-for="s in US_STATES" :key="s" :value="s">{{ s }}</option>
                </select>
                <input v-else v-model="form.state" class="input" placeholder="ON">
                <div v-if="country === 'US'" class="field-msg">{{ tt('Select a state', '请选择州') }}</div>
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
            <p style="font-size:12px;color:var(--gray);margin-top:12px">
              🔒 {{ i18n.t('co.payNote') }}
            </p>
          </div>

          <!-- 备注 / 礼物 / 积分 / 礼品卡 -->
          <div class="card" style="padding:22px;display:grid;gap:14px">
            <div class="field" style="margin:0">
              <label>{{ i18n.t('co.note') }}</label>
              <textarea v-model="form.note" class="input" rows="2" :placeholder="i18n.t('co.notePh')"></textarea>
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
                  <b>{{ i.title }}</b><span v-if="(i.stock || 0) <= 0" style="color:var(--error);font-size:11px;font-weight:700;margin-left:6px">{{ tt('Out of stock', '缺货') }}</span>
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
                <template v-else>{{ money(pv ? pv.shipping_fee : (shipMethod === 'express' ? 1499 : 499)) }}</template>
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
          <button class="btn btn-primary btn-block btn-lg" :class="{ loading: placing }" :disabled="placing" @click="place">
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
