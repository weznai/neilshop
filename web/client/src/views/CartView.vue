<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { i18n, tt } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'
import { req } from '../api/client'

const cart = useCartStore()
const ui = useUiStore()
const auth = useAuthStore()


/* 折扣码失败原因走 i18n promo.*（对齐后端 promo REASON_TEXT；preview 返回裸 reason 码），
   t() 缺键返回键本身 → 回退展示原始 reason 码 */
const reasonText = (r) => {
  const v = i18n.t('promo.' + r)
  return v === 'promo.' + r ? r : v
}

/* 免邮门槛：以 shipping-methods 下发的 settings 值为准（运营改配置后进度条即时对齐），失败回落 3500 */
const FREE_SHIP_C = ref(3500)
const FALLBACK_SHIP_C = 499 /* settings.shipping_standard 默认 */

const code = ref('')
const appliedCode = ref(null)
const pv = ref(null)
const pvBusy = ref(false)

/* 行项图兜底：回落 placehold + dataset 守卫防循环 */
const IMG_FALLBACK = 'https://placehold.co/200x200/E8B4B8/552338?text=GLOWMAG'
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = IMG_FALLBACK
}

/* preview 试算（standard 运费模板）：小计/组合折扣/码折扣/运费与后端逐字一致 */
let pvSeq = 0
async function runPreview() {
  if (!cart.items.length) { pv.value = null; return }
  const seq = ++pvSeq
  pvBusy.value = true
  try {
    const d = await req('POST', '/api/checkout/preview', {
      country: 'US',
      shipping_method: 'standard',
      code: appliedCode.value || undefined,
      email: (auth.user && auth.user.email) || undefined,
    })
    if (seq === pvSeq) pv.value = d
  } catch (_) {
    if (seq === pvSeq) pv.value = null
  } finally {
    if (seq === pvSeq) pvBusy.value = false
  }
}

async function applyCode() {
  const c = (code.value || '').trim().toUpperCase()
  if (!c) { appliedCode.value = null; try { localStorage.removeItem('gm_applied_code') } catch (_) { /* 隐私模式 */ } runPreview(); return }
  appliedCode.value = c
  await runPreview()
  const p = pv.value
  if (p && p.code_valid) {
    try { localStorage.setItem('gm_applied_code', c) } catch (_) { /* 隐私模式 */ }
    const save = ((p.code_discount || 0) / 100).toFixed(2)
    ui.toast(p.free_shipping
      ? i18n.t('promo.appliedShip', c)
      : i18n.t('promo.appliedSave', c, save), 'success')
  } else if (p) {
    try { localStorage.removeItem('gm_applied_code') } catch (_) { /* 隐私模式 */ }
    ui.toast(reasonText(p.code_reason), 'error')
  } else {
    /* preview 网络失败：无法判定码有效性，如实提示 */
    ui.toast(i18n.t('promo.verifyFail'), 'error')
  }
}
function removeCode() {
  appliedCode.value = null
  code.value = ''
  try { localStorage.removeItem('gm_applied_code') } catch (_) { /* 隐私模式 */ }
  runPreview()
}

/* 删除撤销条（6s 自动消失） */
const undoTimer = ref(null)
watch(
  () => cart.removed && cart.removed.at,
  () => {
    clearTimeout(undoTimer.value)
    if (cart.removed) undoTimer.value = setTimeout(() => cart.dismissRemoved(), 6000)
  },
)
function undoRemove() {
  clearTimeout(undoTimer.value)
  cart.undoRemove(ui)
}

function onQtyInput(i, e) {
  const n = Math.floor(Number(e.target.value) || 0)
  if (n < 1 || n === i.qty) { e.target.value = i.qty; return }
  cart.setQty(i.vid, n, ui)
}

onMounted(() => {
  cart.refresh().catch(() => {})
  /* 免邮门槛（settings 下发；失败回落默认） */
  req('GET', '/api/checkout/shipping-methods?country=US').then((d) => {
    if (d && d.free_shipping_threshold) FREE_SHIP_C.value = Number(d.free_shipping_threshold) || 3500
  }).catch(() => {})
  /* 跨页恢复已应用的折扣码（抽屉/checkout 同一 localStorage 键，保持三入口一致）；
     试算由 items watcher（immediate）覆盖，不重复手动跑 */
  const saved = (localStorage.getItem('gm_applied_code') || '').trim().toUpperCase()
  if (saved && !appliedCode.value) { code.value = saved; appliedCode.value = saved }
})
watch(
  () => cart.items.map((i) => i.vid + ':' + i.qty).join('|'),
  () => runPreview(),
  { immediate: true },
)

/* 摘要（全部美分 → $xx.xx） */
const subC = computed(() => cart.subtotalC)
const bundleC = computed(() => (pv.value && pv.value.bundle_discount) || 0)
const codeC = computed(() => (pv.value && pv.value.code_valid && pv.value.code === appliedCode.value && pv.value.code_discount) || 0)
const shipC = computed(() => {
  if (!pv.value) return subC.value >= FREE_SHIP_C.value ? 0 : FALLBACK_SHIP_C
  return pv.value.free_shipping ? 0 : (pv.value.shipping_fee != null ? pv.value.shipping_fee : FALLBACK_SHIP_C)
})
const freeShip = computed(() => shipC.value === 0)
/* 免邮达成瞬间脉冲（复用全局 pillPop 关键帧，跑两遍） */
const freePop = ref(false)
let freePopT = null
watch(freeShip, (v) => {
  if (!v) return
  freePop.value = true
  clearTimeout(freePopT)
  freePopT = setTimeout(() => { freePop.value = false }, 1100)
})
/* 免邮进度口径：preview 可用时统一以折后小计判定（后端免邮按折后金额），否则按原小计 */
const awayC = computed(() => {
  if (pv.value) {
    if (pv.value.free_shipping || pv.value.shipping_fee === 0) return 0
    const after = pv.value.subtotal - (pv.value.discount_total || 0)
    return Math.max(0, FREE_SHIP_C.value - after)
  }
  return Math.max(0, FREE_SHIP_C.value - subC.value)
})
/* 免邮进度条文案：preview 可用显示「还差 $X」；preview 失败（pv=null）只展示门槛不报金额（以结算页试算为准） */
const shipBarHtml = computed(() => {
  if (freeShip.value) return i18n.t('ship.unlocked')
  if (pv.value) return i18n.t('ship.away', (awayC.value / 100).toFixed(2))
  return tt(`Free shipping on orders over $${(FREE_SHIP_C.value / 100).toFixed(0)}`, `满 $${(FREE_SHIP_C.value / 100).toFixed(0)} 可免邮`)
})
const totalD = computed(() => ((subC.value - bundleC.value - codeC.value + shipC.value) / 100).toFixed(2))
const shipPct = computed(() => Math.min(100, ((FREE_SHIP_C.value - awayC.value) / FREE_SHIP_C.value) * 100))

/* 穿戴甲组合进度（后端规则：press-on 2 件 85 折 / 3 件 8 折，只算 press-on-nails 类目） */
const pressQty = computed(() => (pv.value && pv.value.bundle_qty) || 0)
const bundleHint = computed(() => i18n.t(pressQty.value >= 3
  ? 'cart.bundle.3'
  : pressQty.value === 2 ? 'cart.bundle.2' : pressQty.value === 1 ? 'cart.bundle.1' : 'cart.bundle.0'))

/* 结算链接仅在当前 preview 判定码有效时携带 ?code=（无效码不带，避免 checkout 反复 409 提示） */
const checkoutLink = computed(() => '/checkout' + (appliedCode.value && pv.value && pv.value.code_valid ? `?code=${encodeURIComponent(appliedCode.value)}` : ''))
const hasOos = computed(() => cart.items.some((i) => i.inactive || (i.stock || 0) <= 0 || i.stockStatus === 'out'))
const hasOver = computed(() => cart.items.some((i) => i.stock > 0 && i.qty > i.stock))
const hasInactive = computed(() => cart.items.some((i) => i.inactive))
async function removeInactive() {
  const dead = cart.items.filter((i) => i.inactive).map((i) => i.vid)
  for (const vid of dead) await cart.remove(vid, ui)
}
function isLash(i) {
  const l = pv.value && pv.value.items ? pv.value.items.find((x) => x.variant_id === i.vid) : null
  if (l && l.category_slug) return l.category_slug === 'magnetic-lashes'
  return /\b(lashes?)\b/i.test(i.title)
}
const hasLash = computed(() => cart.items.some(isLash))
const hasNail = computed(() => cart.items.some((i) => !isLash(i)))
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head"><h2 class="section-title">{{ i18n.t('cart.title') }}</h2></div>

      <div v-if="!cart.items.length" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:52px;margin-bottom:12px">🛒</div>
        <p style="margin-bottom:18px">{{ i18n.t('cart.empty') }}</p>
        <router-link class="btn btn-primary" to="/store">{{ i18n.t('cart.shop') }}</router-link>
      </div>

      <div v-else class="grid-m-1" style="display:grid;grid-template-columns:1.6fr 1fr;gap:32px;align-items:start">
        <div class="card" style="padding:8px 20px">
          <div v-if="cart.removed" class="undo-bar">
            <span>{{ i18n.t('cart.removedMsg', cart.removed.title) }}</span>
            <button class="undo-btn" @click="undoRemove">{{ i18n.t('cart.undo') }}</button>
          </div>
          <div
            v-for="i in cart.items" :key="i.id"
            class="cart-row"
            style="display:flex;gap:14px;padding:18px 12px;margin:0 -12px;border-bottom:1px solid var(--gray-light)"
          >
            <router-link v-if="!i.inactive && i.pid" :to="`/product?id=${i.pid}`">
              <img :src="i.img" :alt="i.title" style="width:88px;height:88px;border-radius:12px;object-fit:cover" loading="lazy" @error="imgFallback">
            </router-link>
            <img v-else :src="i.img || IMG_FALLBACK" :alt="i.title || ''" style="width:88px;height:88px;border-radius:12px;object-fit:cover;opacity:.6" loading="lazy" @error="imgFallback">
            <div style="flex:1;min-width:0">
              <div style="display:flex;justify-content:space-between;gap:10px">
                <div>
                  <b style="font-size:15px">{{ i.title || tt('Unavailable item', '已失效商品') }}</b>
                  <span v-if="i.inactive" class="tag" style="background:var(--gray-light);color:var(--error);font-size:11px;margin-left:6px">{{ tt('Delisted', '已下架') }}</span>
                  <div style="font-size:12.5px;color:var(--gray)">{{ i.variant }}</div>
                  <div v-if="i.inactive" style="font-size:12px;color:var(--error);font-weight:600;margin-top:2px">
                    {{ tt('No longer available — please remove it', '该商品已不可购买，请移除') }}
                  </div>
                  <div v-else-if="i.stock > 0 && i.qty > i.stock" style="font-size:12px;color:var(--error);font-weight:600;margin-top:2px">
                    {{ tt('Only ' + i.stock + ' left', '仅剩 ' + i.stock + ' 件') }}
                  </div>
                  <div v-else-if="i.stock > 0 && i.stock <= 5" style="font-size:12px;color:var(--warn);font-weight:600;margin-top:2px">
                    {{ i18n.t('cart.lowStock', i.stock) }}
                  </div>
                  <div v-else-if="i.stock <= 0" style="font-size:12px;color:var(--error);font-weight:600;margin-top:2px">
                    {{ i18n.t('cart.oos') }}
                  </div>
                </div>
                <b v-if="!i.inactive" style="font-size:15px;color:var(--plum);font-variant-numeric:tabular-nums">${{ ((i.priceC ?? i.price * 100) * i.qty / 100).toFixed(2) }}</b>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px">
                <div v-if="!i.inactive" style="display:flex;align-items:center;border:1px solid var(--gray-light);border-radius:8px">
                  <button class="qbtn" :disabled="i.qty <= 1" @click="cart.setQty(i.vid, i.qty - 1, ui)">−</button>
                  <input
                    class="qty-in" type="number" min="1" inputmode="numeric" :value="i.qty"
                    :aria-label="tt('Quantity', '数量')"
                    @change="onQtyInput(i, $event)"
                  >
                  <button
                    class="qbtn" :disabled="(i.stock || 0) <= 0 || (i.stock > 0 && i.qty >= i.stock)"
                    :title="(i.stock || 0) <= 0 ? i18n.t('cart.oos') : (i.stock > 0 && i.qty >= i.stock ? i18n.t('cart.maxStock') : '')"
                    @click="cart.setQty(i.vid, i.qty + 1, ui)"
                  >＋</button>
                </div>
                <button class="btn btn-ghost btn-sm" @click="cart.remove(i.vid, ui)">{{ i18n.t('cart.remove') }}</button>
              </div>
            </div>
          </div>
          <div :style="{ padding: '14px 0', fontSize: '13px', color: bundleC ? 'var(--success)' : 'var(--gray)', fontWeight: 600 }">
            🎁 {{ bundleHint }}<template v-if="bundleC"> — {{ i18n.t('cart.bundleSaved') }} ${{ (bundleC / 100).toFixed(2) }}</template>
          </div>
          <div v-if="hasLash && !hasNail" style="padding:0 0 14px;font-size:13px;color:var(--gray)">
            💅 {{ i18n.t('cart.pairsHint') }}
            <router-link to="/store?cat=nails" style="color:var(--plum)">{{ i18n.t('cart.shopSets') }}</router-link>
          </div>
        </div>

        <div class="card cart-summary">
          <div
            class="ship-bar"
            :class="[{ 'gwp-bar': freeShip }, freePop ? 'free-pop' : '']"
            style="margin-bottom:10px"
            v-html="shipBarHtml"></div>
          <div class="ship-track" style="margin-bottom:16px"><div class="ship-fill" :style="{ width: shipPct + '%' }"></div></div>

          <div style="display:flex;gap:8px;margin-bottom:6px">
            <input v-model="code" class="input" :placeholder="i18n.t('promo.codePh')" style="text-transform:uppercase" @keyup.enter="applyCode">
            <button class="btn btn-secondary" :disabled="pvBusy" @click="applyCode">{{ pvBusy ? '…' : i18n.t('promo.apply') }}</button>
          </div>
          <div v-if="appliedCode && pv" style="display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12.5px;margin-bottom:12px"
               :style="{ color: pv.code_valid ? 'var(--success)' : 'var(--error)' }">
            <span>{{ appliedCode }} · {{ pv.code_valid
              ? (pv.free_shipping ? i18n.t('promo.freeShipOk') : `−$${((pv.code_discount || 0) / 100).toFixed(2)}`)
              : reasonText(pv.code_reason) }}</span>
            <button class="undo-btn" style="background:var(--gray-light);color:var(--gray)" @click="removeCode">×</button>
          </div>
          <div v-else style="height:6px;margin-bottom:12px"></div>

          <div style="display:grid;gap:10px;font-size:14px">
            <div class="srow"><span>{{ i18n.t('cart.subtotal') }}</span><span class="val">${{ (subC / 100).toFixed(2) }}</span></div>
            <div v-if="bundleC" class="srow" style="color:var(--success)">
              <span>{{ i18n.t('cart.bundleDiscount') }}</span><span>−${{ (bundleC / 100).toFixed(2) }}</span>
            </div>
            <div v-if="codeC" class="srow" style="color:var(--success)">
              <span>{{ i18n.t('cart.codeRow') }} {{ appliedCode }}</span><span>−${{ (codeC / 100).toFixed(2) }}</span>
            </div>
            <div class="srow">
              <span>{{ i18n.t('cart.shipStd') }}</span>
              <span class="val">
                <span v-if="freeShip" style="color:var(--success)">{{ i18n.t('cart.free') }}</span>
                <template v-else>${{ (shipC / 100).toFixed(2) }}</template>
              </span>
            </div>
            <div class="srow"><span>{{ i18n.t('cart.tax') }}</span><span class="val" style="color:var(--gray)">{{ i18n.t('cart.taxNote') }}</span></div>
          </div>
          <div style="display:flex;justify-content:space-between;font-weight:800;font-size:17px;margin:16px 0;padding-top:14px;border-top:1px solid var(--gray-light)">
            <span>{{ tt('Estimated total', '预估总额') }} <span style="font-size:11px;color:var(--gray);font-weight:400">({{ tt('excl. tax', '不含税') }})</span></span><span style="color:var(--plum);font-variant-numeric:tabular-nums">${{ totalD }}</span>
          </div>
          <router-link v-if="!hasOos && !hasOver" :to="checkoutLink" class="btn btn-primary btn-block btn-lg">{{ i18n.t('cart.checkout') }} · ${{ totalD }}</router-link>
          <button v-else class="btn btn-primary btn-block btn-lg" disabled>{{ i18n.t('cart.checkout') }}</button>
          <button v-if="hasInactive" class="btn btn-secondary btn-block" style="margin-top:8px" type="button" @click="removeInactive">
            {{ tt('Remove unavailable items', '移除已下架商品') }}
          </button>
          <div v-if="hasOos" style="font-size:12.5px;color:var(--error);font-weight:600;margin-top:10px;text-align:center">
            {{ tt('Please remove out-of-stock items before checkout', '请先移除缺货/下架商品后再结算') }}
          </div>
          <div v-if="hasOver" style="font-size:12.5px;color:var(--error);font-weight:600;margin-top:10px;text-align:center">
            {{ tt('Some items exceed available stock — please adjust quantities', '部分商品库存不足，请调整数量后再结算') }}
          </div>
          <router-link to="/store" style="display:block;text-align:center;margin-top:12px;font-size:13px;color:var(--gray);text-decoration:underline">
            {{ i18n.t('cart.continue') }}
          </router-link>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* v19 移动端补漏：摘要卡吸顶对齐头部（原 top:20px 钻到 64px 吸顶头部下）；移动端单列取消吸顶 */
.cart-summary { position: sticky; top: 84px; padding: 22px; }
@media (max-width: 768px) { .cart-summary { position: static; } }
.qbtn { width: 30px; height: 30px; border: none; background: none; color: var(--plum); font-size: 16px; font-weight: 700; line-height: 1; cursor: pointer; border-radius: 6px; transition: background .15s; }
.qbtn:hover:not(:disabled) { background: var(--rose-pale); }
.qbtn:disabled { opacity: .35; cursor: not-allowed; }
.qty-in { width: 34px; height: 30px; border: none; background: none; text-align: center; font-weight: 600; font-size: 13px; color: inherit; padding: 0; -moz-appearance: textfield; }
.qty-in:focus { outline: none; background: var(--rose-pale); border-radius: 6px; }
.qty-in::-webkit-outer-spin-button, .qty-in::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.srow { display: flex; justify-content: space-between; align-items: baseline; }
.srow .val { font-variant-numeric: tabular-nums; font-weight: 600; }
.undo-bar { display: flex; align-items: center; justify-content: space-between; gap: 10px; background: var(--rose-pale); border-radius: 10px; padding: 10px 12px; font-size: 13px; margin: 14px 0 4px; animation: undoIn .25s ease-out; }
.undo-bar span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.undo-btn { border: none; background: var(--plum); color: #fff; font-size: 12px; font-weight: 700; padding: 5px 13px; border-radius: 999px; cursor: pointer; flex: none; }
.undo-btn:hover { opacity: .88; }
/* 行 hover 背景 rose-pale 渐显 */
.cart-row { border-radius: 10px; transition: background .2s ease-out; }
.cart-row:hover { background: var(--rose-pale); }
/* 免邮达成瞬间 pill 脉冲 */
.free-pop { animation: pillPop .5s ease-out 2; }
@keyframes undoIn { from { opacity: 0; transform: translateY(-6px); } }
</style>
