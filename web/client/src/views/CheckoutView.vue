<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { req } from '../api/client'
import { i18n } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'

const cart = useCartStore()
const ui = useUiStore()
const auth = useAuthStore()
const router = useRouter()

const form = ref({
  email: '', fname: '', lname: '', addr1: '', addr2: '', city: '', state: '', zip: '', phone: '', note: '',
})
const country = ref(0)
const COUNTRIES = ['US', 'CA', 'GB', 'AU', 'DE', 'FR']
const shipMethod = ref('standard')
const payMethod = ref('card')
const payProviders = ref([])
const payWhich = ref('card')
const provSel = ref(0)
const code = ref('')
const apiCode = ref(null)
const lastPv = ref(null)
const usePoints = ref(false)
const placing = ref(false)
const pv = ref(null)

const emailFilled = computed(() => form.value.email || (auth.user && auth.user.email) || '')

async function loadPayMethods() {
  try {
    const d = await req('GET', '/api/checkout/shipping-methods')
    /* 支付方式接口（providers）如存在则填充 */
  } catch (_) { /* 静态卡组原样 */ }
}

let pvTimer = null
function schedulePreview() {
  clearTimeout(pvTimer)
  pvTimer = setTimeout(runPreview, 600)
}
async function runPreview() {
  if (!cart.items.length) return
  try {
    pv.value = await req('POST', '/api/checkout/preview', {
      country: COUNTRIES[country.value] || 'US',
      shipping_method: shipMethod.value === 'exp' ? 'express' : 'standard',
      code: apiCode.value || undefined,
    })
    lastPv.value = pv.value
  } catch (_) { pv.value = null }
}

async function applyCode() {
  apiCode.value = (code.value || '').trim().toUpperCase() || null
  await runPreview()
  if (apiCode.value && lastPv.value && lastPv.value.code_valid) {
    ui.toast(`${apiCode.value} applied — you save $${((lastPv.value.subtotal - lastPv.value.discount_total) / 100).toFixed(2)}`, 'success')
  } else if (apiCode.value && lastPv.value) {
    ui.toast(lastPv.value.code_reason === 'min_subtotal'
      ? 'Spend more to use this code' : 'Code not valid', 'error')
  }
}

async function pointsWanted() {
  if (!auth.isLoggedIn || !usePoints.value) return 0
  try { return (await req('GET', '/api/points')).usable || 0 } catch (_) { return 0 }
}

async function place() {
  const f = form.value
  const need = { email: (v) => v.includes('@'), fname: (v) => !!v, addr1: (v) => !!v, city: (v) => !!v, zip: (v) => !!v }
  for (const [k, ok] of Object.entries(need)) {
    if (!ok(f[k])) { ui.toast('Please complete the highlighted fields', 'error'); return }
  }
  placing.value = true
  try {
    await cart.refresh() /* 下单前拉平服务端车 */
    const body = {
      email: f.email,
      address: {
        full_name: (f.fname + ' ' + f.lname).trim(),
        line1: f.addr1, line2: f.addr2 || null,
        city: f.city, state: f.state || null, zip: f.zip,
        country: COUNTRIES[country.value] || 'US', phone: f.phone || null,
      },
      shipping_method: shipMethod.value === 'exp' ? 'express' : 'standard',
    }
    if (apiCode.value && lastPv.value && lastPv.value.code_valid) body.code = apiCode.value
    const pts = await pointsWanted()
    if (pts > 0) body.points = pts
    if (f.note) body.note = f.note
    const d = await req('POST', '/api/checkout/place', body)
    /* 支付意向 + mock 支付（演示通道） */
    try {
      await req('POST', '/api/payments/create-intent', { order_no: d.order_no })
      await req('POST', '/api/payments/mock-pay', { order_no: d.order_no, succeed: true })
    } catch (_) { /* 也可走 /success 页手动支付 */ }
    router.push({ path: '/success', query: { no: d.order_no } })
  } catch (e) {
    let m = (e.data && e.data.detail) || e.message || 'Place order failed'
    if (/insufficient/i.test(m)) m = 'Insufficient stock — your cart was refreshed'
    if (/empty_cart/.test(m)) m = 'Your cart is empty'
    ui.toast(m, 'error')
  } finally { placing.value = false }
}

onMounted(() => {
  if (auth.user) form.value.email = auth.user.email || ''
  loadPayMethods()
  schedulePreview()
})
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head"><h2 class="section-title">Checkout</h2></div>

      <div v-if="!cart.items.length" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">🛒</div>
        Your cart is empty — <router-link to="/store" style="color:var(--plum)">shop best sellers</router-link>
      </div>

      <div v-else class="grid-m-1" style="display:grid;grid-template-columns:1.5fr 1fr;gap:32px;align-items:start">
        <div style="display:grid;gap:18px">
          <!-- 联系 & 地址 -->
          <div class="card" style="padding:22px">
            <h3 style="font-size:16px;margin-bottom:14px">1 · Contact &amp; shipping address</h3>
            <div class="field">
              <label>Email</label>
              <input v-model="form.email" class="input" type="email" placeholder="you@example.com" autocomplete="email">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div class="field"><label>First name</label><input v-model="form.fname" class="input" autocomplete="given-name"></div>
              <div class="field"><label>Last name</label><input v-model="form.lname" class="input" autocomplete="family-name"></div>
            </div>
            <div class="field"><label>Address</label><input v-model="form.addr1" class="input" autocomplete="address-line1" placeholder="Street & number"></div>
            <div class="field"><label>Apt / Suite (optional)</label><input v-model="form.addr2" class="input" autocomplete="address-line2"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr 0.7fr;gap:12px">
              <div class="field"><label>City</label><input v-model="form.city" class="input" autocomplete="address-level2"></div>
              <div class="field"><label>State</label><input v-model="form.state" class="input" placeholder="TX"></div>
              <div class="field"><label>ZIP</label><input v-model="form.zip" class="input" autocomplete="postal-code"></div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div class="field">
                <label>Country</label>
                <select v-model="country" class="input" @change="schedulePreview">
                  <option v-for="(c, i) in COUNTRIES" :key="c" :value="i">{{ c }}</option>
                </select>
              </div>
              <div class="field"><label>Phone (optional)</label><input v-model="form.phone" class="input" type="tel" autocomplete="tel"></div>
            </div>
          </div>

          <!-- 配送 -->
          <div class="card" style="padding:22px">
            <h3 style="font-size:16px;margin-bottom:14px">2 · Shipping method</h3>
            <label class="pay-row" :class="{ on: shipMethod === 'standard' }" style="cursor:pointer">
              <input v-model="shipMethod" type="radio" value="standard" style="display:none" @change="schedulePreview">
              <b>Standard</b><span style="color:var(--gray);font-size:13px">3–6 business days</span>
              <b style="margin-left:auto">$4.99</b>
            </label>
            <label class="pay-row" :class="{ on: shipMethod === 'exp' }" style="cursor:pointer">
              <input v-model="shipMethod" type="radio" value="exp" style="display:none" @change="schedulePreview">
              <b>Express</b><span style="color:var(--gray);font-size:13px">1–3 business days</span>
              <b style="margin-left:auto">$14.99</b>
            </label>
          </div>

          <!-- 支付 -->
          <div class="card" style="padding:22px">
            <h3 style="font-size:16px;margin-bottom:14px">3 · Payment</h3>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <label class="pay-row on" style="cursor:pointer">
                <b>💳 Card</b>
                <span style="margin-left:auto;font-size:11px;color:var(--gray)">VISA · MC · AMEX</span>
              </label>
              <span class="pay-pill">PAYPAL</span><span class="pay-pill">KLARNA</span><span class="pay-pill">APPLE PAY</span>
            </div>
            <p style="font-size:12px;color:var(--gray);margin-top:12px">
              🔒 Payments run through the mock provider in this demo — no real charge. Order confirmation lands in your inbox.
            </p>
          </div>

          <!-- 备注 + 积分 -->
          <div class="card" style="padding:22px">
            <div class="field"><label>Order note (optional)</label><textarea v-model="form.note" class="input" rows="2" placeholder="Delivery instructions…"></textarea></div>
            <label v-if="auth.isLoggedIn" style="display:flex;gap:10px;align-items:center;margin-top:12px;font-size:13.5px;cursor:pointer">
              <input v-model="usePoints" type="checkbox" style="width:16px;height:16px">
              Redeem Glow points (100 pts = $1)
            </label>
          </div>
        </div>

        <!-- 摘要 -->
        <div class="card" style="padding:22px;position:sticky;top:20px">
          <h3 style="font-size:16px;margin-bottom:14px">Order summary</h3>
          <div id="sumItems" style="display:grid;gap:12px;max-height:240px;overflow-y:auto">
            <div v-for="i in cart.items" :key="i.id" style="display:flex;gap:10px;align-items:center">
              <div style="position:relative">
                <img :src="i.img" :alt="i.title" style="width:48px;height:48px;border-radius:8px">
                <span style="position:absolute;top:-6px;right:-6px;background:var(--ink);color:#fff;font-size:10px;font-weight:700;min-width:16px;height:16px;border-radius:8px;display:flex;align-items:center;justify-content:center">{{ i.qty }}</span>
              </div>
              <div style="flex:1;font-size:13px"><b>{{ i.title }}</b><div style="color:var(--gray);font-size:12px">{{ i.variant }}</div></div>
              <b style="font-size:13px">${{ (i.price * i.qty).toFixed(2) }}</b>
            </div>
          </div>
          <div style="display:flex;gap:8px;margin:16px 0">
            <input v-model="code" class="input" placeholder="Discount code" style="text-transform:uppercase">
            <button class="btn btn-secondary" @click="applyCode">Apply</button>
          </div>
          <div style="display:grid;gap:8px;font-size:14px">
            <div style="display:flex;justify-content:space-between"><span>Subtotal</span><b>${{ cart.subtotal.toFixed(2) }}</b></div>
            <div v-if="lastPv && lastPv.discount_total" style="display:flex;justify-content:space-between;color:var(--success)">
              <span>Discount ({{ lastPv.code || '' }})</span><span>−${{ (lastPv.discount_total / 100).toFixed(2) }}</span>
            </div>
            <div style="display:flex;justify-content:space-between">
              <span>Shipping</span>
              <b>${{ ((lastPv && lastPv.shipping_fee) != null ? lastPv.shipping_fee / 100 : shipMethod === 'exp' ? 14.99 : 4.99).toFixed(2) }}</b>
            </div>
            <div v-if="lastPv && lastPv.tax" style="display:flex;justify-content:space-between">
              <span>Tax</span><b>${{ (lastPv.tax / 100).toFixed(2) }}</b>
            </div>
          </div>
          <div style="display:flex;justify-content:space-between;font-weight:800;font-size:17px;margin:14px 0;padding-top:12px;border-top:1px solid var(--gray-light)">
            <span>Total</span>
            <span style="color:var(--plum);font-variant-numeric:tabular-nums">
              ${{ ((lastPv && lastPv.grand_total ? lastPv.grand_total / 100 : cart.subtotal + (shipMethod === 'exp' ? 14.99 : 4.99))).toFixed(2) }}
            </span>
          </div>
          <button class="btn btn-primary btn-block btn-lg" :class="{ loading: placing }" :disabled="placing" @click="place">
            Place Order
          </button>
          <p style="font-size:11.5px;color:var(--gray);margin-top:10px;text-align:center">
            By placing this order you agree to our <router-link to="/terms" style="text-decoration:underline">Terms</router-link> &amp; <router-link to="/returns-policy" style="text-decoration:underline">Return Policy</router-link>.
          </p>
        </div>
      </div>
    </div>
  </section>
</template>
