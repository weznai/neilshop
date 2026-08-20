<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../../api/client'
import { useUiStore } from '../../stores/ui'
import { statusLabel, statusTag } from '../../composables/orderStatus'
import { i18n } from '../../i18n'

const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)

const orders = ref([])
const loaded = ref(false)
const loading = ref(false)
const failed = ref(false)
const page = ref(1)
const pages = ref(1)
const total = ref(0)
const payingNo = ref('')
const cancelingNo = ref('')

const SHIP = { 0: '', 1: ' · 部分发货', 2: ' · 全部发货' }
/* 服务端筛选（GET /api/orders?status=&page=，每页 10 条） */
const TABS = [
  ['all', '全部', null], ['s0', '待付款', 0], ['s1', '已支付', 1], ['s3', '已发货', 3],
  ['s5', '已完成', 5], ['s8', '已取消', 8], ['s9', '已退款', 9],
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
function fmt(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

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
watch(tab, () => { page.value = 1; syncQuery(); load() })
/* 浏览器回退/前进（同路由 query 变化）时恢复状态 */
watch(() => route.query, (q) => { if (applyQuery(q)) load() })

function go(p) {
  if (p < 1 || p > pages.value || p === page.value) return
  page.value = p
  syncQuery()
  load()
}

/* 待付订单支付：先建支付意图再 mock 支付（与 Checkout 一致）；积分由后端确认后发放，前端不自算 */
async function pay(o) {
  payingNo.value = o.order_no
  try {
    await req('POST', '/api/payments/create-intent', { order_no: o.order_no })
    const d = await req('POST', '/api/payments/mock-pay', { order_no: o.order_no, succeed: true })
    ui.toast(d.order_status === 1 ? tt('Payment successful — points will be credited after confirmation', '支付成功，积分将在确认后发放') : tt('Payment processing', '支付处理中'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('order_not_pending')) { ui.toast('订单状态已变化，已刷新', 'error'); load() }
    else if (d === 'already_paid') { ui.toast('该订单已支付', 'error'); load() }
    else ui.toast('支付失败，请稍后再试', 'error')
  } finally { payingNo.value = '' }
}

/* 待付订单取消：POST /api/orders/{no}/cancel（释放库存） */
async function cancel(o) {
  if (!window.confirm(`确认取消订单 ${o.order_no}？已锁定库存将释放。`)) return
  cancelingNo.value = o.order_no
  try {
    await req('POST', '/api/orders/' + encodeURIComponent(o.order_no) + '/cancel', { reason: 'user' })
    ui.toast('订单已取消', 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('not_cancellable')) ui.toast('该订单当前状态不可取消', 'error')
    else ui.toast('取消失败，请稍后再试', 'error')
  } finally { cancelingNo.value = '' }
}
</script>

<template>
  <div>
    <div style="display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap">
      <button
        v-for="[k, label, sv] in TABS" :key="k" class="btn btn-sm"
        :class="tab === sv ? 'btn-primary' : 'btn-secondary'" :aria-pressed="tab === sv" @click="tab = sv"
      >{{ label }}</button>
    </div>

    <div v-if="loading" style="display:grid;gap:12px">
      <div v-for="i in 3" :key="i" class="skeleton" style="height:76px;border-radius:14px" />
    </div>

    <template v-else>
      <div v-if="failed" class="card" style="padding:30px;text-align:center;color:var(--gray)">
        订单加载失败，<a href="javascript:void(0)" style="color:var(--plum)" @click="load">重试</a>
      </div>
      <div v-else-if="orders.length" style="display:grid;gap:12px">
        <div v-for="o in orders" :key="o.order_no" class="card ocard" :data-no="o.order_no" style="padding:18px">
          <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
            <div>
              <b>{{ o.order_no }}</b>
              <div style="font-size:12px;color:var(--gray)">
                {{ fmt(o.placed_at) }}<span v-if="o.status === 3 && o.shipping_status === 1">{{ SHIP[1] }}</span>
              </div>
            </div>
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
              <span class="tag" :class="statusTag(o.status)">{{ statusLabel(o.status) }}</span>
              <b style="color:var(--plum)">{{ money(o.grand_total) }}</b>
              <template v-if="o.status === 0">
                <button class="btn btn-primary btn-sm" :class="{ loading: payingNo === o.order_no }" :disabled="payingNo === o.order_no || !!cancelingNo" @click="pay(o)">去支付</button>
                <button class="btn btn-ghost btn-sm" style="color:var(--error)" :class="{ loading: cancelingNo === o.order_no }" :disabled="cancelingNo === o.order_no || !!payingNo" @click="cancel(o)">取消</button>
              </template>
              <router-link class="btn btn-secondary btn-sm" :to="{ path: '/account/orders/detail', query: { no: o.order_no } }">详情 →</router-link>
            </div>
          </div>
        </div>

        <div v-if="pages > 1" style="display:flex;gap:8px;align-items:center;justify-content:center;padding:6px 0">
          <button class="btn btn-secondary btn-sm" :disabled="page <= 1" @click="go(page - 1)">← 上一页</button>
          <span style="font-size:13px;color:var(--gray)">第 {{ page }} / {{ pages }} 页 · 共 {{ total }} 单</span>
          <button class="btn btn-secondary btn-sm" :disabled="page >= pages" @click="go(page + 1)">下一页 →</button>
        </div>
      </div>
      <div v-else class="card" style="padding:30px;text-align:center;color:var(--gray)">
        该状态下暂无订单。
      </div>
    </template>
  </div>
</template>
