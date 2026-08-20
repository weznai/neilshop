<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import { i18n } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'

const route = useRoute()
const cart = useCartStore()
const auth = useAuthStore()
const ui = useUiStore()

const zh = computed(() => i18n.lang === 'zh')
const t = (en, cn) => (zh.value ? cn : en)
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

const orderNo = computed(() => String(route.query.no || ''))
const email = computed(() => String(route.query.email || ''))
const order = ref(null)
const loaded = ref(false)
const orderError = ref(false)
const paying = ref(false)
const copied = ref(false)

const OSTATUS = ['Pending payment', 'Paid', 'Packing', 'Shipped', 'Delivered', 'Done', 'Cancelled', 'Refunded', 'Cancelled', 'Refunded']
const statusText = (s) => OSTATUS[s] || '—'
const statusTag = (s) => {
  if (s === 0) return 'tag-pending'
  if (s >= 1 && s <= 5) return 'tag-paid'
  return 'tag-error'
}

async function fetchOrder() {
  if (!orderNo.value) return
  try {
    /* 游客订单详情需双因子（订单号 + 下单邮箱）；登录本人可仅凭订单号 */
    const q = email.value ? '?email=' + encodeURIComponent(email.value) : ''
    order.value = await req('GET', '/api/orders/' + encodeURIComponent(orderNo.value) + q)
    orderError.value = false
  } catch (_) { order.value = null; orderError.value = true }
}

/* 待支付轮询：每 5s 拉一次订单，状态到 1（已支付）或满 12 次（1 分钟）即停；卸载清理 */
let pollTimer = null
let pollCount = 0
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}
function startPolling() {
  stopPolling()
  pollCount = 0
  pollTimer = setInterval(async () => {
    pollCount++
    await fetchOrder()
    if (!order.value || order.value.status !== 0 || pollCount >= 12) stopPolling()
  }, 5000)
}
onUnmounted(stopPolling)

/* 待支付订单：创建支付意向 + mock 支付（演示通道；真实 provider 走 webhook） */
async function payNow() {
  if (paying.value || !orderNo.value) return
  paying.value = true
  try {
    await req('POST', '/api/payments/create-intent', { order_no: orderNo.value })
    try {
      await req('POST', '/api/payments/mock-pay', { order_no: orderNo.value, succeed: true })
    } catch (e) {
      const m = (e.data && e.data.detail) || ''
      if (m === 'already_paid') ui.toast(t('Already paid ✓', '已支付 ✓'), 'success')
      else ui.toast(m === 'use_webhook' ? t('Please complete payment via the link emailed to you', '请通过邮件中的支付链接完成付款') : m || 'Pay failed', 'error')
    }
    await fetchOrder()
  } catch (e) {
    const m = (e.data && e.data.detail) || ''
    if (/order_not_pending/.test(m)) { ui.toast(t('This order is already paid ✓', '该订单已支付 ✓'), 'success'); await fetchOrder() }
    else ui.toast(m || 'Pay failed', 'error')
  } finally { paying.value = false }
}

async function copyNo() {
  const s = orderNo.value
  try {
    await navigator.clipboard.writeText(s)
  } catch (_) {
    const ta = document.createElement('textarea')
    ta.value = s; document.body.appendChild(ta); ta.select()
    try { document.execCommand('copy') } catch (_) { /* older browsers */ }
    document.body.removeChild(ta)
  }
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

const trackLink = computed(() => '/track?no=' + encodeURIComponent(orderNo.value) + (email.value ? '&email=' + encodeURIComponent(email.value) : ''))

onMounted(async () => {
  cart.refresh().catch(() => {})   /* 下单后服务端车已清空，拉平本地 */
  try { localStorage.removeItem('gm_applied_code') } catch (_) { /* 隐私模式 */ }
  await fetchOrder()
  if (order.value && order.value.status === 0) startPolling()
  loaded.value = true
})
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:640px;text-align:center">
      <div :style="{
        width: '72px', height: '72px', borderRadius: '50%', margin: '0 auto 18px',
        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '32px',
        background: order && order.status === 0 ? 'var(--pale-warn)' : 'rgba(62,189,147,.12)',
        border: order && order.status === 0 ? '2px solid rgba(234,170,50,.5)' : '2px solid rgba(62,189,147,.4)',
      }">
        <template v-if="order && order.status === 0">⏳</template><template v-else>✓</template>
      </div>
      <h1 style="font-family:var(--font-title);font-size:32px;margin-bottom:8px">
        {{ order && order.status === 0
          ? t('Order placed — payment pending', '订单已提交 · 待支付')
          : orderError ? t('Order placed — confirming…', '订单已提交 · 确认中…')
          : t('Order confirmed!', '下单成功！') }}
      </h1>
      <p style="color:var(--gray);margin-bottom:8px">
        {{ t('Thanks for your order', '感谢下单') }}<template v-if="!orderError && (order || email)">, {{ t('confirmation sent to', '确认邮件已发送至') }} <b>{{ (order && order.email) || email }}</b></template>.
      </p>

      <div v-if="order && order.status === 0" class="card" style="padding:18px;margin:20px 0;text-align:left;background:var(--pale-warn);border-color:rgba(234,170,50,.4)">
        <b style="display:block;margin-bottom:6px">⏳ {{ t('Payment pending', '待支付') }}</b>
        <p style="font-size:13.5px;color:var(--ink);margin-bottom:12px">
          {{ t(`Complete payment (${money(order.grand_total)}) to start packing your glam.`, `完成支付（${money(order.grand_total)}）后我们立即开始打包。`) }}
        </p>
        <button class="btn btn-primary" :class="{ loading: paying }" :disabled="paying" @click="payNow">
          {{ t(`Pay now · ${money(order.grand_total)}`, `立即支付 · ${money(order.grand_total)}`) }}
        </button>
      </div>

      <div v-if="order" class="card" style="padding:18px;margin:20px 0;text-align:left;display:grid;gap:8px;font-size:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
          <span>{{ t('Order', '订单号') }}</span>
          <span style="display:flex;align-items:center;gap:8px">
            <b>{{ order.order_no }}</b>
            <button class="copy-btn" @click="copyNo">{{ copied ? '✓' : t('Copy', '复制') }}</button>
          </span>
        </div>
        <div style="display:flex;justify-content:space-between"><span>{{ t('Total', '合计') }}</span><b style="color:var(--plum)">{{ money(order.grand_total) }}</b></div>
        <div v-if="order.discount_total" style="display:flex;justify-content:space-between;color:var(--success)"><span>{{ t('Discounts', '优惠') }}</span><span>−{{ money(order.discount_total) }}</span></div>
        <div v-if="order.points_used" style="display:flex;justify-content:space-between;color:var(--gray)"><span>⭐ {{ t('Points used', '使用积分') }}</span><span>{{ order.points_used }} pts (−{{ money(order.points_discount) }})</span></div>
        <div v-if="order.points_earned" style="display:flex;justify-content:space-between;color:var(--success)"><span>🎁 {{ t('Points earned (frozen till delivery)', '本单获得积分（确认收货后解冻）') }}</span><span>+{{ order.points_earned }} pts</span></div>
        <div v-if="order.giftcard_discount" style="display:flex;justify-content:space-between;color:var(--success)"><span>💳 {{ t('Gift card', '礼品卡') }}</span><span>−{{ money(order.giftcard_discount) }}</span></div>
        <div style="display:flex;justify-content:space-between"><span>{{ t('Status', '状态') }}</span>
          <span class="tag" :class="statusTag(order.status)">{{ statusText(order.status) }}</span>
        </div>
        <div v-if="order.items && order.items.length" style="border-top:1px solid var(--gray-light);padding-top:10px;display:grid;gap:8px">
          <div v-for="it in order.items" :key="it.id" style="display:flex;gap:10px;align-items:center;font-size:13px">
            <img :src="it.image" :alt="it.title" style="width:40px;height:40px;border-radius:8px;object-fit:cover">
            <span style="flex:1;text-align:left;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ it.title }} × {{ it.qty }}</span>
            <b style="font-variant-numeric:tabular-nums">{{ money(it.subtotal) }}</b>
          </div>
        </div>
      </div>
      <div v-else-if="loaded && orderError" class="card" style="padding:20px;margin:20px 0;text-align:left">
        <b style="display:block;margin-bottom:6px;color:var(--error)">⚠️ {{ t('Order lookup failed', '订单查询失败') }}</b>
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:14px">
          {{ t(`We couldn't load order ${orderNo}. Check it from your account orders, or contact support.`, `订单 ${orderNo} 查询失败。可到账户订单中查看，或联系客服处理。`) }}
        </p>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <router-link v-if="auth.isLoggedIn" to="/account/orders" class="btn btn-secondary btn-sm">📦 {{ t('View my orders', '我的订单') }}</router-link>
          <router-link to="/contact" class="btn btn-secondary btn-sm">💬 {{ t('Contact support', '联系客服') }}</router-link>
        </div>
      </div>
      <div v-else-if="loaded" class="card" style="padding:18px;margin:20px 0;font-size:14px">
        {{ t('Order', '订单') }} <b>{{ orderNo }}</b> {{ t('received. Track it anytime from your account.', '已收到。可随时在账户中心查看。') }}
      </div>

      <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-top:10px">
        <router-link v-if="orderNo" :to="trackLink" class="btn btn-secondary">🚚 {{ t('Track order', '查询物流') }}</router-link>
        <router-link v-if="auth.isLoggedIn" to="/account/orders" class="btn btn-primary">{{ t('View my orders', '我的订单') }}</router-link>
        <router-link v-else to="/store" class="btn btn-primary">{{ t('Keep shopping', '继续购物') }}</router-link>
        <router-link v-if="auth.isLoggedIn" to="/store" class="btn btn-secondary">{{ t('Keep shopping', '继续购物') }}</router-link>
      </div>
      <p v-if="auth.isLoggedIn" style="font-size:12.5px;color:var(--gray);margin-top:22px">
        🎁 {{ t('You earn Glow points on this order — redeem 100 pts for $1 off next time.', '本单将获得积分奖励——100 分可抵 $1。') }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.copy-btn { border: 1px solid var(--gray-light); background: #fff; color: var(--plum); font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px; cursor: pointer; }
.copy-btn:hover { background: var(--rose-pale); }
</style>
