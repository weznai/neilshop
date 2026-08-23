<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req, intentNoChannel } from '../../api/client'
import { useUiStore } from '../../stores/ui'
import { statusLabel, statusTag } from '../../composables/orderStatus'
import { useArmConfirm } from '../../composables/useArmConfirm'
import { fmtDateTime } from '../../composables/datetime'
import { i18n, tt } from '../../i18n'

const ui = useUiStore()
const route = useRoute()
const router = useRouter()

const orders = ref([])
const loaded = ref(false)
const loading = ref(false)
const failed = ref(false)
const page = ref(1)
const pages = ref(1)
const total = ref(0)
const payingNo = ref('')
const cancelingNo = ref('')
const confirmingNo = ref('')

/* 两段式确认（useArmConfirm：5s 复位；arm 态红字 + 二段文案） */
const cancelArm = useArmConfirm()
const recvArm = useArmConfirm()

const SHIP = { 0: '', 1: [' · partially shipped', ' · 部分发货'], 2: [' · all shipped', ' · 全部发货'] }
/* 服务端筛选（GET /api/orders?status=&page=，每页 10 条）；标签 tt 双语 [en, zh]；
   s2 备货中：后台"开始备货"将订单 1→2（prepare_order CAS），需可筛选 */
const TABS = [
  ['all', ['All', '全部'], null], ['s0', ['Unpaid', '待付款'], 0], ['s1', ['Paid', '已支付'], 1],
  ['s2', ['Packing', '备货中'], 2],
  ['s3', ['Shipped', '已发货'], 3], ['s4', ['Delivered', '已送达'], 4],
  ['s5', ['Completed', '已完成'], 5], ['s8', ['Cancelled', '已取消'], 8], ['s9', ['Refunded', '已退款'], 9],
]
function tabFromQuery(q) {
  const row = TABS.find(([k]) => k === q)
  return row ? row[2] : null
}
function keyFromTab(sv) {
  const row = TABS.find(([, , v]) => v === sv)
  return row ? row[0] : 'all'
}
const tab = ref(null)

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const fmt = fmtDateTime

async function load() {
  loading.value = true
  failed.value = false
  try {
    const q = '/api/orders?page=' + page.value + (tab.value === null ? '' : '&status=' + tab.value)
    const d = await req('GET', q)
    orders.value = d.items || []
    pages.value = d.pages || 1
    total.value = d.total || 0
  } catch (_) {
    failed.value = true
  } finally {
    loaded.value = true
    loading.value = false
  }
}

/* tab/page ↔ route.query（replace）：刷新/回退不丢状态 */
function syncQuery() {
  const query = Object.assign({}, route.query)
  const k = keyFromTab(tab.value)
  if (k === 'all') delete query.tab
  else query.tab = k
  if (page.value > 1) query.page = String(page.value)
  else delete query.page
  router.replace({ query })
}
function applyQuery(q) {
  const nt = tabFromQuery(q.tab)
  const np = Math.max(1, Number(q.page) || 1)
  if (nt !== tab.value) { tab.value = nt; page.value = 1; return true }
  if (np !== page.value) { page.value = np; return true }
  return false
}

/* 初始状态来自 URL */
tab.value = tabFromQuery(route.query.tab)
page.value = Math.max(1, Number(route.query.page) || 1)
onMounted(load)
/* 双发守卫：route.query 变化引发的 tab 赋值会再触发本 watcher → 用标志位跳过本次，避免回退时双请求 */
let _byQuery = false
watch(tab, () => {
  if (_byQuery) { _byQuery = false; syncQuery(); return }
  page.value = 1; syncQuery(); load()
})
/* 浏览器回退/前进（同路由 query 变化）时恢复状态；
   _byQuery 仅在 query 驱动真的改了 tab 时置位，跳过随后触发的 tab watcher，避免双请求 */
watch(() => route.query, (q) => {
  const prevTab = tab.value
  const changed = applyQuery(q)
  if (!changed) return
  _byQuery = tab.value !== prevTab
  load()
})

function go(p) {
  if (p < 1 || p > pages.value || p === page.value) return
  page.value = p
  syncQuery()
  load()
}

/* 待付订单支付：与 Checkout 同口径 —— hosted 通道（redirect_url）跳收银台，mock 通道直付 */
async function pay(o) {
  payingNo.value = o.order_no
  try {
    let provider = ''
    try { provider = (localStorage.getItem('gm_pay_provider') || '').trim() } catch (_) { /* 隐私模式 */ }
    const ib = { order_no: o.order_no }
    if (provider && provider !== 'mock') ib.provider = provider
    const intent = await req('POST', '/api/payments/create-intent', ib)
    if (intentNoChannel(intent)) {
      ui.toast(i18n.t('pay.unsupported_channel'), 'error')
      return
    }
    if (provider !== 'mock' && intent && intent.redirect_url) {
      window.location.href = intent.redirect_url
      return
    }
    const d = await req('POST', '/api/payments/mock-pay', { order_no: o.order_no, succeed: true })
    ui.toast(d.order_status === 1 ? tt('Payment successful — points will be credited after confirmation', '支付成功，积分将在确认后发放') : tt('Payment processing', '支付处理中'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('order_not_pending')) { ui.toast(tt('Order status changed — refreshed', '订单状态已变化，已刷新'), 'error'); load() }
    else if (d === 'already_paid') { ui.toast(tt('This order is already paid', '该订单已支付'), 'error'); load() }
    else ui.toast(tt('Payment failed — please retry later', '支付失败，请稍后再试'), 'error')
  } finally { payingNo.value = '' }
}

/* 订单取消：待付（释放库存）/ 已付未发货（自助取消 + 后端自动全额原路退款）；两段式确认防误触 */
async function cancel(o) {
  const paid = o.status === 1 && (o.shipping_status || 0) === 0
  cancelingNo.value = o.order_no
  try {
    const d = await req('POST', '/api/orders/' + encodeURIComponent(o.order_no) + '/cancel', { reason: 'user' })
    const ref = d && d.refund
    if (paid && ref && ref.amount) ui.toast(tt(`Order cancelled — ${money(ref.amount)} refund on its way back`, `订单已取消，退款 ${money(ref.amount)} 将原路退回`), 'success')
    else ui.toast(tt('Order cancelled', '订单已取消'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('no_refundable_payment')) ui.toast(tt('Auto refund unavailable — please contact support', '无法自动退款，请联系客服'), 'error')
    else if (String(d).startsWith('not_cancellable')) { ui.toast(tt('Order status changed — refreshed', '订单状态已变化，已刷新'), 'error'); load() }
    else ui.toast(tt('Cancel failed — please retry later', '取消失败，请稍后再试'), 'error')
  } finally { cancelingNo.value = '' }
}

/* 确认收货（仅 status=4 已送达）：CAS 4→5 已完成；两段式确认防误触 */
async function confirmRecv(o) {
  confirmingNo.value = o.order_no
  try {
    await req('POST', '/api/orders/' + encodeURIComponent(o.order_no) + '/confirm-received')
    ui.toast(tt('Thanks! Order completed 🎉', '感谢确认收货，订单已完成 🎉'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('not_confirmable')) { ui.toast(tt('Order status changed — refreshed', '订单状态已变化，已刷新'), 'error'); load() }
    else ui.toast(tt('Could not confirm — please retry later', '确认失败，请稍后再试'), 'error')
  } finally { confirmingNo.value = '' }
}
</script>

<template>
  <div>
    <div class="o-tabs" role="tablist">
      <button
        v-for="[k, label, sv] in TABS" :key="k" class="o-tab"
        :class="{ on: tab === sv }" role="tab" :aria-selected="tab === sv" @click="tab = sv"
      >{{ tt(label[0], label[1]) }}</button>
    </div>

    <div v-if="loading" style="display:grid;gap:12px">
      <div v-for="i in 3" :key="i" class="skeleton" style="height:76px;border-radius:14px" />
    </div>

    <template v-else>
      <div v-if="failed" class="card" style="padding:30px;text-align:center;color:var(--gray)">
        {{ tt('Could not load your orders —', '订单加载失败，') }}<a href="javascript:void(0)" style="color:var(--plum)" @click="load">{{ tt('retry', '重试') }}</a>
      </div>
      <div v-else-if="orders.length" style="display:grid;gap:12px">
        <div v-for="o in orders" :key="o.order_no" class="card ocard" :data-no="o.order_no" style="padding:18px">
          <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
            <div>
              <b>{{ o.order_no }}</b>
              <div style="font-size:12px;color:var(--gray)">
                {{ fmt(o.placed_at) }}<span v-if="[3, 4, 5].includes(o.status) && SHIP[o.shipping_status]">{{ tt(SHIP[o.shipping_status][0], SHIP[o.shipping_status][1]) }}</span>
              </div>
            </div>
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
              <span class="tag" :class="statusTag(o.status)">{{ statusLabel(o.status) }}</span>
              <b style="color:var(--plum)">{{ money(o.grand_total) }}</b>
              <template v-if="o.status === 0">
                <button class="btn btn-primary btn-sm" :class="{ loading: payingNo === o.order_no }" :disabled="payingNo === o.order_no || !!cancelingNo" @click="pay(o)">{{ tt('Pay now', '去支付') }}</button>
                <button
                  class="btn btn-ghost btn-sm" :class="{ arm: cancelArm.is(o.order_no), loading: cancelingNo === o.order_no }"
                  :disabled="cancelingNo === o.order_no || !!payingNo" @click="cancelArm.hit(o.order_no, () => cancel(o))"
                >{{ cancelArm.is(o.order_no) ? tt('Tap again to confirm', '再点一次确认') : tt('Cancel', '取消') }}</button>
              </template>
              <template v-else-if="o.status === 1 && (o.shipping_status || 0) === 0">
                <button
                  class="btn btn-ghost btn-sm" :class="{ arm: cancelArm.is(o.order_no), loading: cancelingNo === o.order_no }"
                  :disabled="cancelingNo === o.order_no" @click="cancelArm.hit(o.order_no, () => cancel(o))"
                >{{ cancelArm.is(o.order_no) ? tt('Tap again to confirm', '再点一次确认') : tt('Cancel & refund', '取消并退款') }}</button>
              </template>
              <template v-else-if="o.status === 4">
                <button
                  class="btn btn-primary btn-sm" :class="{ arm: recvArm.is(o.order_no), loading: confirmingNo === o.order_no }"
                  :disabled="confirmingNo === o.order_no" @click="recvArm.hit(o.order_no, () => confirmRecv(o))"
                >{{ recvArm.is(o.order_no) ? tt('Tap again to confirm', '再点一次确认') : tt('✓ Confirm delivery', '确认收货') }}</button>
              </template>
              <router-link class="btn btn-secondary btn-sm" :to="{ path: '/account/orders/detail', query: { no: o.order_no } }">{{ tt('Details →', '详情 →') }}</router-link>
            </div>
          </div>
        </div>

        <div v-if="pages > 1" style="display:flex;gap:8px;align-items:center;justify-content:center;padding:6px 0">
          <button class="btn btn-secondary btn-sm" :disabled="page <= 1" @click="go(page - 1)">{{ tt('← Prev', '← 上一页') }}</button>
          <span style="font-size:13px;color:var(--gray)">{{ tt(`Page ${page} / ${pages} · ${total} orders`, `第 ${page} / ${pages} 页 · 共 ${total} 单`) }}</span>
          <button class="btn btn-secondary btn-sm" :disabled="page >= pages" @click="go(page + 1)">{{ tt('Next →', '下一页 →') }}</button>
        </div>
      </div>
      <div v-else class="card" style="padding:30px;text-align:center;color:var(--gray)">
        {{ tt('No orders in this tab yet.', '该状态下暂无订单。') }}
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 状态筛选：单行横滑 + 选中态下划线指示（plum 2px） */
.o-tabs { display: flex; gap: 4px; margin-bottom: 16px; overflow-x: auto; scrollbar-width: none; -ms-overflow-style: none; }
.o-tabs::-webkit-scrollbar { display: none; }
.o-tab { flex: none; padding: 10px 12px; font-size: 13.5px; font-weight: 600; color: var(--gray); background: none; border: none; border-bottom: 2px solid transparent; white-space: nowrap; cursor: pointer; transition: color .15s, border-color .15s; }
.o-tab:hover { color: var(--plum); }
.o-tab.on { color: var(--plum); border-bottom-color: var(--plum); }
</style>
