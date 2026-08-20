<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import { statusLabel } from '../composables/orderStatus'
import { i18n } from '../i18n'

const route = useRoute()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)

const no = ref(String(route.query.no || ''))
const email = ref(String(route.query.email || ''))
const result = ref(null)
const err = ref('')
const busy = ref(false)

/* OrderStatus 0-5 / 8 / 9（共享 composable，无 6/7 下标） */
const STEPS = [
  ['Placed', '下单'],
  ['Paid', '支付'],
  ['Packing', '备货'],
  ['Shipped', '发货'],
  ['Delivered', '送达'],
]

const isCancelled = computed(() => !!result.value && [8, 9].includes(result.value.status))
const stepState = computed(() => {
  if (!result.value) return []
  const upto = Math.min(result.value.status, 4)
  return STEPS.map((s, i) => ({ l: tt(s[0], s[1]), done: i <= upto }))
})

/* 时间线事件 → 可读文案（对齐后端 order_timeline 事件名） */
const EVENT_TEXT = {
  checkout_created: ['Order placed', '订单已创建'],
  payment_succeeded: ['Payment confirmed', '支付成功'],
  payment_failed: ['Payment failed', '支付失败'],
  status_changed: ['Status updated', '状态更新'],
  shipment_created: ['Package shipped', '包裹已发出'],
  refund_issued: ['Refund issued', '退款已发放'],
  rma_created: ['Return requested', '退货申请'],
  rma_label_sent: ['Return label sent', '退货标签已发送'],
  rma_received: ['Return received', '退货已签收'],
  giftcard_created: ['Gift card issued', '礼品卡已开出'],
  exchange_created: ['Exchange requested', '换货申请'],
  exchange_approved: ['Exchange approved', '换货已批准'],
  exchange_rejected: ['Exchange declined', '换货被拒绝'],
  exchange_shipped: ['Exchange shipped', '换货已发货'],
  exchange_completed: ['Exchange completed', '换货完成'],
  exchange_diff_paid: ['Exchange difference paid', '换货差价已支付'],
}
function eventLabel(ev) {
  if (ev.event === 'status_changed' && ev.detail && ev.detail.to != null) {
    return tt(`Status → ${statusLabel(ev.detail.to)}`, `状态 → ${statusLabel(ev.detail.to)}`)
  }
  const row = EVENT_TEXT[ev.event]
  if (row) return tt(row[0], row[1])
  return (ev.event || '').replace(/_/g, ' ')
}
function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d) ? '' : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function shipState(s) {
  if (s.delivered_at) return { text: tt('Delivered ✓', '已送达 ✓'), cls: 'tag-paid' }
  if (s.shipped_at) return { text: tt('In transit', '运输中'), cls: 'tag-ship' }
  return { text: tt('Preparing', '备货中'), cls: 'tag-pending' }
}
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

async function track() {
  err.value = ''
  result.value = null
  if (!no.value.trim()) { err.value = tt('Enter your order number (NS…)', '请输入订单号（NS…）'); return }
  if (!email.value.trim()) { err.value = tt('Enter the email you used at checkout', '请输入下单时使用的邮箱'); return }
  busy.value = true
  try {
    result.value = await req('GET', '/api/orders/track?no=' + encodeURIComponent(no.value.trim()) + '&email=' + encodeURIComponent(email.value.trim()))
  } catch (e) {
    if (e && e.status === 404) err.value = tt('Order not found — check the number & email (must match checkout email)', '未找到订单——请核对订单号与下单邮箱（须与结算邮箱一致）')
    else if (e && (e.status === 0 || e.name === 'TypeError')) err.value = tt('Network unreachable — check your connection and retry', '网络连接失败，请检查网络后重试')
    else err.value = tt('Track failed — please try later', '查询失败，请稍后再试')
  } finally { busy.value = false }
}

onMounted(() => {
  if (no.value && email.value) track()
})
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:560px">
      <div class="section-head"><h2 class="section-title">{{ tt('Track Order 🚚', '订单查询 🚚') }}</h2></div>
      <div class="card" style="padding:24px">
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:16px">{{ tt('No login needed — order number + email used at checkout.', '免登录——订单号 + 下单邮箱即可查询。') }}</p>
        <form @submit.prevent="track">
          <div class="field"><label>{{ tt('Order number', '订单号') }}</label><input v-model="no" class="input" placeholder="NS260728D4E5F6"></div>
          <div class="field"><label>{{ tt('Email', '邮箱') }}</label><input v-model="email" class="input" type="email" placeholder="you@example.com"></div>
          <div v-if="err" class="field-msg" style="display:block;color:var(--error)">{{ err }}</div>
          <button class="btn btn-primary btn-block" :class="{ loading: busy }" :disabled="busy">{{ tt('Track', '查询') }}</button>
        </form>
      </div>

      <div v-if="result" class="card" style="padding:24px;margin-top:16px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">
          <b style="font-size:16px">{{ result.order_no }}</b>
          <span class="tag" :class="isCancelled ? 'tag-error' : result.status >= 1 ? 'tag-paid' : 'tag-pending'">
            {{ statusLabel(result.status) }}
          </span>
        </div>
        <div style="font-size:12.5px;color:var(--gray);margin-bottom:18px">
          {{ fmtTime(result.placed_at) }} · {{ money(result.grand_total) }}
        </div>

        <div v-if="!isCancelled" style="display:flex;gap:0">
          <div v-for="(s, i) in stepState" :key="i" style="flex:1;text-align:center">
            <div :style="{ background: s.done ? 'var(--success)' : 'var(--gray-light)' }"
                 style="width:24px;height:24px;border-radius:50%;margin:0 auto 6px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px">
              {{ s.done ? '✓' : i + 1 }}
            </div>
            <div style="font-size:11px" :style="{ color: s.done ? 'var(--ink)' : 'var(--gray)' }">{{ s.l }}</div>
          </div>
        </div>
        <div v-else class="ship-bar" style="background:var(--pale-error);margin-bottom:4px">
          <b style="color:var(--error)">{{ tt('This order was cancelled or refunded.', '该订单已取消或已退款。') }}</b>
        </div>

        <!-- 包裹（track 响应 shipments：carrier/tracking_no/时间） -->
        <div v-for="s in result.shipments || []" :key="s.shipment_no" style="display:flex;justify-content:space-between;align-items:center;gap:10px;border:1px solid var(--gray-light);border-radius:10px;padding:12px 14px;margin-top:14px;font-size:13.5px">
          <div>
            <b>{{ (s.carrier || 'CARRIER').toUpperCase() }}</b>
            <div style="font-family:monospace;font-size:12.5px;color:var(--gray);margin-top:2px">{{ s.tracking_no }}</div>
            <div v-if="s.delivered_at || s.shipped_at" style="font-size:11.5px;color:var(--gray);margin-top:2px">
              {{ s.delivered_at ? tt('Delivered ', '已送达 ') + fmtTime(s.delivered_at) : tt('Shipped ', '已发货 ') + fmtTime(s.shipped_at) }}
            </div>
          </div>
          <span class="tag" :class="shipState(s).cls">{{ shipState(s).text }}</span>
        </div>

        <!-- 时间线（倒序，后端最新在前） -->
        <div v-if="result.timeline && result.timeline.length" style="margin-top:18px">
          <h3 style="font-size:14px;margin-bottom:12px">{{ tt('Activity', '订单动态') }}</h3>
          <div style="display:grid;gap:2px">
            <div v-for="(ev, i) in result.timeline" :key="i" style="display:flex;gap:12px">
              <div style="display:flex;flex-direction:column;align-items:center">
                <div :style="{ background: i === 0 ? 'var(--plum)' : 'var(--gray-light)' }"
                     style="width:10px;height:10px;border-radius:50%;margin-top:5px;flex:none"></div>
                <div v-if="i < result.timeline.length - 1" style="width:2px;flex:1;background:var(--gray-light);min-height:14px"></div>
              </div>
              <div style="padding-bottom:14px;min-width:0">
                <div style="font-size:13.5px;font-weight:600" :style="{ color: i === 0 ? 'var(--ink)' : 'var(--gray)' }">{{ eventLabel(ev) }}</div>
                <div style="font-size:11.5px;color:var(--gray)">{{ fmtTime(ev.created_at) }}<template v-if="ev.actor && ev.actor !== 'system'"> · {{ ev.actor }}</template></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
