<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../../api/client'
import { useUiStore } from '../../stores/ui'
import { statusLabel, statusTag } from '../../composables/orderStatus'
import { useArmConfirm } from '../../composables/useArmConfirm'
import { useOrderPay } from '../../composables/useOrderPay'
import { fmtDateTime } from '../../composables/datetime'
import { money } from '../../composables/format'
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
const confirmingNo = ref('')

/* 两段式确认（useArmConfirm：5s 复位；arm 态红字 + 二段文案） */
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
const kw = ref(String(route.query.q || '').trim())

const fmt = fmtDateTime

/* 请求序列守卫：仅最新一次 load 的响应可落地（tab 快速切换/翻页竞态丢弃过期响应） */
let _loadSeq = 0
async function load() {
  const seq = ++_loadSeq
  loading.value = true
  failed.value = false
  try {
    const path = '/api/orders?page=' + page.value + (tab.value === null ? '' : '&status=' + tab.value) + (kw.value.trim() ? '&q=' + encodeURIComponent(kw.value.trim()) : '')
    const d = await req('GET', path)
    if (seq !== _loadSeq) return
    orders.value = d.items || []
    pages.value = d.pages || 1
    total.value = d.total || 0
    /* URL 直达页码越界（?page=999）：回落第 1 页重拉，避免误导性空态 */
    if (page.value > pages.value && pages.value > 0) { page.value = 1; syncQuery(); load(); return }
  } catch (_) {
    if (seq !== _loadSeq) return
    failed.value = true
  } finally {
    if (seq === _loadSeq) {
      loaded.value = true
      loading.value = false
    }
  }
}

/* tab/page/q ↔ route.query（replace）：刷新/回退不丢状态 */
function syncQuery() {
  const query = Object.assign({}, route.query)
  const k = keyFromTab(tab.value)
  if (k === 'all') delete query.tab
  else query.tab = k
  if (page.value > 1) query.page = String(page.value)
  else delete query.page
  if (kw.value.trim()) query.q = kw.value.trim()
  else delete query.q
  router.replace({ query })
}
function applyQuery(q) {
  const nt = tabFromQuery(q.tab)
  const np = Math.max(1, Number(q.page) || 1)
  const nq = String(q.q || '').trim()
  if (nq !== kw.value.trim()) { kw.value = nq; page.value = 1; return true }
  if (nt !== tab.value) { tab.value = nt; page.value = 1; return true }
  if (np !== page.value) { page.value = np; return true }
  return false
}
function search() {
  page.value = 1
  syncQuery()
  load()
}

/* 初始状态来自 URL */
tab.value = tabFromQuery(route.query.tab)
page.value = Math.max(1, Number(route.query.page) || 1)
const tabsEl = ref(null)
/* tab 条 active 项滚入视野（移动端横滑 tab 常态下选中项可能在屏外） */
function scrollTabIntoView() {
  const el = tabsEl.value && tabsEl.value.querySelector('.o-tab.on')
  if (el && el.scrollIntoView) { try { el.scrollIntoView({ inline: 'center', block: 'nearest' }) } catch (_) { /* 旧浏览器 */ } }
}
onMounted(() => {
  load()
  nextTick(scrollTabIntoView)
})
/* 双发守卫：route.query 变化引发的 tab 赋值会再触发本 watcher → 用标志位跳过本次，避免回退时双请求 */
let _byQuery = false
watch(tab, () => {
  if (_byQuery) { _byQuery = false; syncQuery(); return }
  page.value = 1; syncQuery(); load()
})
/* 浏览器回退/前进（同路由 query 变化）时恢复状态；
   _byQuery 仅在 query 驱动真的改了 tab 时置位，跳过随后触发的 tab watcher，避免双请求 */
watch(() => route.query, (q) => {
  if (route.name !== 'account-orders') return
  const prevTab = tab.value
  const changed = applyQuery(q)
  if (!changed) return
  _byQuery = tab.value !== prevTab
  load()
  nextTick(scrollTabIntoView)
})

function go(p) {
  if (p < 1 || p > pages.value || p === page.value) return
  page.value = p
  syncQuery()
  load()
}

/* 待付订单支付：useOrderPay 统一封装（hosted 跳收银台 / mock 直付，already_paid 幂等） */
const { payingNo, pay } = useOrderPay(load)

/* 订单取消入口已下沉：列表不再提供取消按钮，统一走订单详情 → 订单帮助 →
   /account/orders/cancel 三步挽留向导（reason=user_wizard:* 归因） */

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
    <div ref="tabsEl" class="o-tabs" role="tablist">
      <button
        v-for="[k, label, sv] in TABS" :key="k" class="o-tab"
        :class="{ on: tab === sv }" role="tab" :aria-selected="tab === sv" @click="tab = sv"
      >{{ tt(label[0], label[1]) }}</button>
    </div>

    <form class="o-search" @submit.prevent="search">
      <input v-model="kw" class="input" :placeholder="i18n.t('orders.searchPh')" maxlength="20" autocomplete="off">
      <button class="btn btn-secondary btn-sm" type="submit">{{ i18n.t('orders.search') }}</button>
      <button v-if="kw" type="button" class="btn btn-ghost btn-sm" @click="kw = ''; search()">{{ i18n.t('orders.clear') }}</button>
    </form>

    <div v-if="loading" style="display:grid;gap:8px">
      <div v-for="i in 5" :key="i" class="skeleton" style="height:46px;border-radius:12px" />
    </div>

    <template v-else>
      <div v-if="failed" class="card" style="padding:30px;text-align:center;color:var(--gray)">
        {{ tt('Could not load your orders —', '订单加载失败，') }}<a href="javascript:void(0)" style="color:var(--plum)" @click="load">{{ tt('retry', '重试') }}</a>
      </div>
      <div v-else-if="orders.length" style="display:grid;gap:8px">
        <div v-for="o in orders" :key="o.order_no" class="card ocard" :data-no="o.order_no">
          <div class="ocard-row">
            <router-link class="ocard-info" :to="{ path: '/account/orders/detail', query: { no: o.order_no } }">
              <span class="ocard-no">{{ o.order_no }}</span>
              <span class="ocard-sub">
                {{ fmt(o.placed_at) }}<span v-if="[3, 4, 5].includes(o.status) && SHIP[o.shipping_status]">{{ tt(SHIP[o.shipping_status][0], SHIP[o.shipping_status][1]) }}</span>
              </span>
            </router-link>
            <div class="ocard-side">
              <span class="tag" :class="statusTag(o.status)">{{ statusLabel(o.status) }}</span>
              <b class="ocard-amt">{{ money(o.grand_total) }}</b>
              <template v-if="o.status === 0">
                <button class="btn btn-primary btn-sm" :class="{ loading: payingNo === o.order_no }" :disabled="payingNo === o.order_no" @click="pay(o)">{{ tt('Pay now', '去支付') }}</button>
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
          <span style="font-size:12.5px;color:var(--gray)">{{ tt(`Page ${page} / ${pages} · ${total} orders`, `第 ${page} / ${pages} 页 · 共 ${total} 单`) }}</span>
          <button class="btn btn-secondary btn-sm" :disabled="page >= pages" @click="go(page + 1)">{{ tt('Next →', '下一页 →') }}</button>
        </div>
      </div>
      <div v-else class="card" style="padding:30px;text-align:center;color:var(--gray)">
        {{ kw.trim() ? i18n.t('orders.searchNone', kw.trim()) : tt('No orders in this tab yet.', '该状态下暂无订单。') }}
        <div v-if="!kw.trim()" style="margin-top:10px"><router-link class="btn btn-secondary btn-sm" to="/account/orders">{{ tt('View all orders', '查看全部订单') }}</router-link></div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 状态筛选：分段式胶囊（白底轨道 + rose-pale 选中药丸），单行横滑 */
.o-tabs { display: flex; gap: 4px; margin-bottom: 14px; padding: 4px; background: #fff; border: 1px solid var(--gray-light); border-radius: 12px; overflow-x: auto; scrollbar-width: none; -ms-overflow-style: none; box-shadow: 0 1px 2px rgba(31,27,30,.04); }
.o-tabs::-webkit-scrollbar { display: none; }
.o-tab { flex: none; padding: 7px 14px; font-size: 13px; font-weight: 600; color: var(--gray); background: none; border-radius: 999px; white-space: nowrap; cursor: pointer; transition: color .15s, background .15s; }
.o-tab:hover { color: var(--plum); }
.o-tab.on { color: var(--plum); background: var(--rose-pale); box-shadow: inset 0 0 0 1px var(--rose-light); }
.o-search { display: flex; gap: 8px; margin-bottom: 14px; }
.o-search .input { flex: 1; height: 38px; padding: 0 12px; }

/* 订单卡：单行横排（单号 · 时间 … 状态/金额/操作），左侧品牌渐变饰条 + hover 微浮起 */
.ocard { position: relative; overflow: hidden; padding: 10px 16px 10px 18px; transition: border-color .15s, box-shadow .2s ease-out, transform .15s ease-out; }
.ocard::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: linear-gradient(180deg, var(--rose), var(--plum)); opacity: .7; }
.ocard:hover { border-color: var(--rose); box-shadow: 0 6px 18px rgba(31,27,30,.08); transform: translateY(-1px); }
.ocard-row { display: flex; justify-content: space-between; gap: 10px; flex-wrap: nowrap; align-items: center; white-space: nowrap; }
.ocard-info { display: flex; align-items: baseline; gap: 10px; min-width: 0; overflow: hidden; }
.ocard-info:hover .ocard-no { color: var(--plum); text-decoration: underline; text-underline-offset: 3px; }
.ocard-no { flex: none; font-size: 13px; font-weight: 700; letter-spacing: .3px; font-variant-numeric: tabular-nums; transition: color .15s; }
.ocard-sub { font-size: 11.5px; color: var(--gray); line-height: 1.4; overflow: hidden; text-overflow: ellipsis; }
.ocard-side { display: flex; gap: 8px; align-items: center; flex-wrap: nowrap; flex: none; }
.ocard-amt { font-size: 13.5px; font-weight: 800; color: var(--plum); font-variant-numeric: tabular-nums; }
@media (max-width: 640px) {
  .ocard { padding: 8px 12px 8px 15px; }
  .ocard-side .btn-sm { height: 30px; padding: 0 12px; font-size: 12px; }
}
</style>
