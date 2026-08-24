<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req, intentNoChannel } from '../api/client'
import { i18n } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'
import { statusLabel, statusTag } from '../composables/orderStatus'
import { useArmConfirm } from '../composables/useArmConfirm'
import { createOrderIntent } from '../composables/useOrderPay'

const route = useRoute()
const router = useRouter()
const cart = useCartStore()
const auth = useAuthStore()
const ui = useUiStore()
const { is: armIs, hit: armHit } = useArmConfirm()

const zh = computed(() => i18n.lang === 'zh')
const t = (en, cn) => (zh.value ? cn : en)
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

/* 订单行项图兜底：回落 placehold + dataset 守卫防循环 */
const IMG_FALLBACK = 'https://placehold.co/200x200/E8B4B8/552338?text=GLOWMAG'
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = IMG_FALLBACK
}

const orderNo = computed(() => String(route.query.no || ''))
const email = computed(() => String(route.query.email || ''))
const order = ref(null)
const loaded = ref(false)
const orderError = ref(false)
const paying = ref(false)
const copied = ref(false)
const retryEmail = ref('')
const noChannel = ref(false)

/* fetchOrder 连续失败计数：轮询瞬时失败保留已有 order 数据（不翻错误页），≥3 次才停 */
let failCount = 0
async function fetchOrder() {
  if (!orderNo.value) return
  try {
    /* 游客订单详情需双因子（订单号 + 下单邮箱）；登录本人可仅凭订单号 */
    const q = email.value ? '?email=' + encodeURIComponent(email.value) : ''
    order.value = await req('GET', '/api/orders/' + encodeURIComponent(orderNo.value) + q)
    orderError.value = false
    failCount = 0
  } catch (_) {
    failCount++
    /* 仅在完全无数据且失败时才显示错误卡；已有 order 则继续展示旧数据 */
    if (!order.value) orderError.value = true
  }
}

/* hosted 支付回跳可能不带 email：游客单查询失败时补 email 重查（写入 query 使支付/取消沿用） */
async function retryLookup() {
  const em = retryEmail.value.trim()
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) { ui.toast(t('Enter a valid email address', '请输入有效的邮箱地址'), 'error'); return }
  await router.replace({ query: { ...route.query, email: em } })
  await fetchOrder()
  if (order.value && order.value.status === 0) startPolling()
}

/* 待支付轮询：每 5s 拉一次订单，状态到 1（已支付）或满 12 次（1 分钟）即停；超时停后展示手动刷新按钮；卸载清理 */
let pollTimer = null
let pollCount = 0
const pollTimedOut = ref(false)
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}
function startPolling() {
  stopPolling()
  pollCount = 0
  failCount = 0
  pollTimedOut.value = false
  pollTimer = setInterval(async () => {
    pollCount++
    await fetchOrder()
    if (!order.value || order.value.status !== 0 || failCount >= 3) stopPolling()
    else if (pollCount >= 12) { pollTimedOut.value = true; stopPolling() }
  }, 5000)
}
async function refreshStatus() {
  await fetchOrder()
  if (order.value && order.value.status === 0) startPolling()
}
onUnmounted(stopPolling)

/* 待支付订单：创建支付意向 + mock 支付（演示通道；真实 provider 走 webhook）；游客单带下单 email 过归属校验
    provider 沿用结算页选择（createOrderIntent 内读 gm_pay_provider 并与 methods 对账，下线自动回落默认）；hosted 通道跳转收银台 */
async function payNow() {
  if (paying.value || !orderNo.value) return
  paying.value = true
  const em = email.value || undefined
  try {
    const intent = await createOrderIntent(orderNo.value, em)
    if (intentNoChannel(intent)) {
      noChannel.value = true
      ui.toast(i18n.t('pay.unsupported_channel'), 'error')
      return
    }
    if (intent && intent.redirect_url) {
      window.location.href = intent.redirect_url
      return
    }
    try {
      await req('POST', '/api/payments/mock-pay', { order_no: orderNo.value, email: em, succeed: true })
    } catch (e) {
      const m = (e.data && e.data.detail) || (e.message || '')
      if (m === 'use_webhook') ui.toast(t('Please complete payment via the link emailed to you', '请通过邮件中的支付链接完成付款'), 'error')
      else ui.toast(m || i18n.t('pay.failed'), 'error')
    }
    await fetchOrder()
  } catch (e) {
    const m = (e.data && e.data.detail) || ''
    if (/order_not_pending/.test(m)) { ui.toast(t('This order is already paid', '该订单已支付'), 'success'); await fetchOrder() }
    else ui.toast(m || i18n.t('pay.failed'), 'error')
  } finally { paying.value = false }
}

/* 待支付订单自助取消：游客 email 双因子 / 登录属主（后端与详情页同口径），两段式确认防误触 */
async function cancelOrder() {
  if (!orderNo.value) return
  try {
    const q = email.value ? '?email=' + encodeURIComponent(email.value) : ''
    await req('POST', '/api/orders/' + encodeURIComponent(orderNo.value) + '/cancel' + q)
    ui.toast(t('Order canceled', '订单已取消'), 'success')
    stopPolling()
    await fetchOrder()
  } catch (e) {
    const m = (e.data && e.data.detail) || ''
    ui.toast(/not_cancellable/.test(m)
      ? t('This order can no longer be canceled', '该订单已无法取消')
      : m || t('Failed to cancel, please try again', '取消失败，请重试'), 'error')
    await fetchOrder()
  }
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

/* 圆环样式/图标随订单状态：0 待付(琥珀) 8 已取消(灰) 9 已退款(红) 查单失败(琥珀中性) 首帧未加载(灰) 其余成功(绿) */
const ringStyle = computed(() => {
  const st = order.value && order.value.status
  const border = !loaded.value ? '2px solid var(--gray-light)'
    : orderError.value ? '2px solid rgba(234,170,50,.5)'
    : st === 8 ? '2px solid var(--gray)'
    : st === 9 ? '2px solid var(--error)'
    : st === 0 ? '2px solid rgba(234,170,50,.5)'
    : '2px solid rgba(62,189,147,.4)'
  const background = !loaded.value ? 'var(--gray-light)'
    : orderError.value ? 'var(--pale-warn)'
    : st === 8 ? 'var(--gray-light)'
    : st === 9 ? 'var(--pale-error)'
    : st === 0 ? 'var(--pale-warn)'
    : 'rgba(62,189,147,.12)'
  return {
    width: '72px', height: '72px', borderRadius: '50%', margin: '0 auto 18px',
    display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '32px',
    background, border,
  }
})
const ringIcon = computed(() => {
  const st = order.value && order.value.status
  return !loaded.value ? '⟳' : orderError.value ? '⟳' : st === 0 ? '⏳' : st === 8 ? '✕' : st === 9 ? '↩' : '✓'
})

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
      <div class="ok-ring" :class="{ 'ok-ring-wait': !loaded || orderError }" :style="ringStyle">
        {{ ringIcon }}
      </div>
      <h1 style="font-family:var(--font-title);font-size:32px;margin-bottom:8px">
        {{ !loaded
          ? i18n.t('pay.orderLoading')
          : order && order.status === 0
          ? t('Order placed — payment pending', '订单已提交 · 待支付')
          : order && order.status === 8 ? t('Order canceled', '订单已取消')
          : order && order.status === 9 ? t('Order refunded', '订单已退款')
          : orderError ? t('Order placed — confirming…', '订单已提交 · 确认中…')
          : t('Order confirmed!', '下单成功！') }}
      </h1>
      <p style="color:var(--gray);margin-bottom:8px">
        {{ !loaded ? '' : t('Thanks for your order', '感谢下单') }}<template v-if="loaded && !orderError && (order || email)">, {{ t('confirmation sent to', '确认邮件已发送至') }} <b>{{ (order && order.email) || email }}</b></template>{{ loaded ? '.' : '' }}
      </p>

      <div v-if="order && order.status === 0" class="card" style="padding:18px;margin:20px 0;text-align:left;background:var(--pale-warn);border-color:rgba(234,170,50,.4)">
        <b style="display:block;margin-bottom:6px">⏳ {{ t('Payment pending', '待支付') }}</b>
        <p style="font-size:13.5px;color:var(--ink);margin-bottom:12px">
          {{ t(`Complete payment (${money(order.grand_total)}) to start packing your glam.`, `完成支付（${money(order.grand_total)}）后我们立即开始打包。`) }}
        </p>
        <p v-if="pollTimedOut" style="font-size:12.5px;color:var(--gray);margin:-4px 0 10px">
          {{ t('Payment is being confirmed — it usually takes 1–2 minutes. Feel free to refresh later.', '支付确认中，约需 1–2 分钟，可稍后手动刷新。') }}
        </p>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <button class="btn btn-primary" :class="{ loading: paying }" :disabled="paying" @click="payNow">
            {{ t(`Pay now · ${money(order.grand_total)}`, `立即支付 · ${money(order.grand_total)}`) }}
          </button>
          <button v-if="pollTimedOut" class="btn btn-secondary" @click="refreshStatus">⟳ {{ t('Refresh status', '刷新状态') }}</button>
          <router-link v-if="noChannel" to="/contact" class="btn btn-secondary">💬 {{ t('Contact support', '联系客服') }}</router-link>
          <button
            class="btn btn-ghost btn-sm" :class="{ arm: armIs('cancel') }"
            style="margin-left:auto"
            @click="armHit('cancel', cancelOrder)"
          >{{ armIs('cancel') ? t('Tap again to cancel', '再点一次确认取消') : t('Cancel order', '取消订单') }}</button>
        </div>
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
        <div v-if="order.points_earned" style="display:flex;justify-content:space-between;color:var(--success)"><span>🎁 {{ t('Points earned (unfreeze after return window)', '本单获得积分（退货期结束后解冻）') }}</span><b style="color:var(--gold)">+{{ order.points_earned }} pts</b></div>
        <div v-if="order.giftcard_discount" style="display:flex;justify-content:space-between;color:var(--success)"><span>💳 {{ t('Gift card', '礼品卡') }}</span><span>−{{ money(order.giftcard_discount) }}</span></div>
        <div style="display:flex;justify-content:space-between"><span>{{ t('Status', '状态') }}</span>
          <span class="tag" :class="statusTag(order.status)">{{ statusLabel(order.status) }}</span>
        </div>
        <div v-if="order.items && order.items.length" style="border-top:1px solid var(--gray-light);padding-top:10px;display:grid;gap:8px">
          <div v-for="it in order.items" :key="it.id" style="display:flex;gap:10px;align-items:center;font-size:13px">
            <img :src="it.image" :alt="it.title" style="width:40px;height:40px;border-radius:8px;object-fit:cover" @error="imgFallback">
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
        <div v-if="!auth.isLoggedIn" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
          <input
            v-model="retryEmail" class="input" type="email" style="flex:1;min-width:200px"
            :placeholder="t('Email used at checkout', '下单时使用的邮箱')" @keyup.enter="retryLookup"
          >
          <button class="btn btn-primary btn-sm" @click="retryLookup">⟳ {{ t('Look up again', '重新查询') }}</button>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <button v-if="auth.isLoggedIn" class="btn btn-primary btn-sm" @click="refreshStatus">⟳ {{ i18n.t('pay.retry') }}</button>
          <router-link v-if="auth.isLoggedIn" to="/account/orders" class="btn btn-secondary btn-sm">📦 {{ t('View my orders', '我的订单') }}</router-link>
          <router-link to="/contact" class="btn btn-secondary btn-sm">💬 {{ t('Contact support', '联系客服') }}</router-link>
        </div>
      </div>
      <div v-else-if="loaded" class="card" style="padding:18px;margin:20px 0;font-size:14px">
        <template v-if="orderNo">{{ t('Order', '订单') }} <b>{{ orderNo }}</b> {{ t('received. Track it anytime from your account.', '已收到。可随时在账户中心查看。') }}</template>
        <template v-else>{{ t('Thanks for your order — you can track it anytime from your account.', '感谢下单——可随时在账户中心查看订单。') }}</template>
      </div>

      <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-top:10px">
        <router-link v-if="orderNo" :to="trackLink" class="btn btn-secondary">🚚 {{ t('Track order', '查询物流') }}</router-link>
        <router-link v-if="auth.isLoggedIn" to="/account/orders" class="btn btn-primary">{{ t('View my orders', '我的订单') }}</router-link>
        <router-link v-else to="/store" class="btn btn-primary">{{ t('Keep shopping', '继续购物') }}</router-link>
        <router-link v-if="auth.isLoggedIn" to="/store" class="btn btn-secondary">{{ t('Keep shopping', '继续购物') }}</router-link>
      </div>
      <p v-if="auth.isLoggedIn && order && order.status >= 1 && ![8, 9].includes(order.status)" style="font-size:12.5px;color:var(--gray);margin-top:22px">
        🎁 {{ t('You earn Glow points on this order — redeem 100 pts for $1 off next time.', '本单将获得积分奖励——100 分可抵 $1。') }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.copy-btn { border: 1px solid var(--gray-light); background: #fff; color: var(--plum); font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px; cursor: pointer; }
.copy-btn:hover { background: var(--rose-pale); }
/* 成功圆环：popIn 入场 + 常驻柔光 pulse 组合 */
.ok-ring { animation: ringIn .45s cubic-bezier(.34,1.56,.64,1) both, ringPulse 2s ease-out .6s infinite; }
/* 查单失败（确认中）态：仅保留入场动画，去掉成功绿脉冲 */
.ok-ring-wait { animation: ringIn .45s cubic-bezier(.34,1.56,.64,1) both; }
@keyframes ringIn { from { transform: scale(.5); opacity: 0; } }
@keyframes ringPulse { 0%,100% { box-shadow: 0 0 0 0 rgba(62,189,147,.32); } 50% { box-shadow: 0 0 0 14px rgba(62,189,147,0); } }
</style>
