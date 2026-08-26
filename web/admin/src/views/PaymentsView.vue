<script setup>
/* 支付流水：双 tab = 支付记录（payments 跨订单全局）/ 回调事件（webhook_events 原文）
 * GET /api/admin/trade/payments · /api/admin/trade/webhook-events（trade:read）
 * 范式对齐 OpsQueuesView：tab/分页入 URL、各槽独立数据 + 竞态保护 + CSV 导出 */
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { money, dt } from '../composables/format'
import { downloadCsv, fetchAllPages } from '../composables/exportCsv'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import { PAY } from '../constants/trade'

const SIZE = 20
const TABS = [
  ['pay', '支付记录'],
  ['hook', '回调事件'],
]

/* tab/分页入 URL（单 page 共用，切 tab 镜像对应槽页码）；筛选为页内状态不污染 URL */
const st = reactive({ tab: 'pay', page: 1 })
useQuerySync(st, { nums: ['page'], defaults: { tab: 'pay', page: 1 }, onPop: () => load(st.page) })
if (!TABS.some(([k]) => k === st.tab)) st.tab = 'pay'

const slot = () => ({ items: [], total: 0, pages: 1, loaded: false, err: '' })
const d = reactive({ pay: slot(), hook: slot() })
const slotPages = reactive({ pay: 1, hook: 1 })
const slotSeq = reactive({ pay: 0, hook: 0 })

async function fetchSlot(key, url, p = 1) {
  const s = d[key]
  const token = ++slotSeq[key]
  s.err = ''
  try {
    const r = await req('GET', url)
    if (token !== slotSeq[key]) return
    s.items = r.items || []
    s.total = r.total ?? 0
    s.pages = Math.max(1, r.pages ?? 1)
    slotPages[key] = r.page || p
    if (key === st.tab) st.page = slotPages[key]
  } catch (e) {
    if (token !== slotSeq[key]) return
    s.err = e.message || ''
    toast('列表加载失败：' + (e.message || ''), 'error')
  }
  s.loaded = true
}

/* ===== tab=pay 支付记录 ===== */
/* 状态筛选：key → status 查询值（待审核组合 0,2 与后端 CSV 口径一致） */
const PTABS = [
  ['all', '全部', null], ['s1', '支付成功', '1'], ['s0', '待支付', '0'],
  ['s2', '支付失败', '2'], ['s4', '部分退款', '4'], ['s3', '已退款', '3'],
]
const pf = reactive({ status: 'all', provider: '', q: '', from: '', to: '' })
const pfKey = computed(() => PTABS.find(([k]) => k === pf.status)?.[2] ?? null)
const PROVIDER_META = {
  stripe: { label: 'Stripe', color: '#635BFF' },
  paypal: { label: 'PayPal', color: '#003087' },
  mock: { label: 'Mock', color: '#8A6D1B' },
}
const provStyle = (p) => {
  const c = PROVIDER_META[p]?.color || '#7A6A70'
  return { background: c + '14', color: c, border: '1px solid ' + c + '30' }
}
const provLabel = (p) => PROVIDER_META[p]?.label || (p || '—')

function payUrl(p, size = SIZE) {
  const params = new URLSearchParams({ page: p, per_page: size })
  if (pfKey.value != null) params.set('status', pfKey.value)
  if (pf.provider) params.set('provider', pf.provider)
  if (pf.q.trim()) params.set('q', pf.q.trim())
  if (pf.from) params.set('date_from', pf.from)
  if (pf.to) params.set('date_to', pf.to)
  return '/api/admin/trade/payments?' + params
}
function loadPay(p = 1) { return fetchSlot('pay', payUrl(p), p) }
function payStatusTab(k) { pf.status = k; loadPay(1) }
function applyPay() { loadPay(1) }
function resetPay() {
  Object.assign(pf, { status: 'all', provider: '', q: '', from: '', to: '' })
  loadPay(1)
}
const payFiltered = computed(() => pf.status !== 'all' || !!pf.provider || !!pf.q.trim() || !!pf.from || !!pf.to)

/* 金额合计（当前页成功口径提示用不做，CSV 导出全量口径） */
const payExporting = ref(false)
async function exportPay() {
  if (payExporting.value) return
  payExporting.value = true
  try {
    const { all, truncated } = await fetchAllPages((p) => req('GET', payUrl(p, 100)), { pageSize: 100, maxPages: 20 })
    if (truncated) toast('匹配结果过多，仅导出前 ' + all.length + ' 条', 'error')
    downloadCsv({
      filename: 'payments_' + new Date().toISOString().slice(0, 10).replace(/-/g, ''),
      headers: ['时间', '订单号', '客户邮箱', '通道', '金额', '已退金额', '状态', '通道单号', '失败原因'],
      rows: all.map((r) => [dt(r.created_at), r.order_no, r.email, provLabel(r.provider),
        money(r.amount), money(r.refunded_amount || 0), PAY[r.status]?.label ?? r.status,
        r.payment_intent || '', r.failure_reason || '']),
    })
    toast('已导出 ' + all.length + ' 条 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  payExporting.value = false
}

/* ===== tab=hook 回调事件 ===== */
/* WebhookEvent.status：0待处理 1成功 2不可恢复已跳过 */
const WSTATUS = {
  0: { label: '待处理', cls: 'tag-pending' },
  1: { label: '处理成功', cls: 'tag-paid' },
  2: { label: '已跳过', cls: 'tag-error' },
}
const SOURCE_META = { stripe: 'Stripe', paypal: 'PayPal', mock: 'Mock' }
/* 常见事件类型输入联想（含 PayPal 归一化前的原始类型；未映射类型原样展示） */
const WTYPES = [
  'payment_intent.succeeded', 'payment_intent.payment_failed', 'payment_intent.canceled',
  'charge.refunded', 'charge.dispute.created', 'checkout.session.completed',
  'PAYMENT.CAPTURE.COMPLETED', 'PAYMENT.CAPTURE.REFUNDED', 'PAYMENT.CAPTURE.REVERSED',
]
const hf = reactive({ status: '', source: '', type: '', q: '', from: '', to: '' })
function hookUrl(p, size = SIZE) {
  const params = new URLSearchParams({ page: p, per_page: size })
  if (hf.status !== '') params.set('status', hf.status)
  if (hf.source) params.set('source', hf.source)
  if (hf.type.trim()) params.set('type', hf.type.trim())
  if (hf.q.trim()) params.set('q', hf.q.trim())
  if (hf.from) params.set('date_from', hf.from)
  if (hf.to) params.set('date_to', hf.to)
  return '/api/admin/trade/webhook-events?' + params
}
function loadHook(p = 1) { return fetchSlot('hook', hookUrl(p), p) }
function applyHook() { loadHook(1) }
function resetHook() {
  Object.assign(hf, { status: '', source: '', type: '', q: '', from: '', to: '' })
  loadHook(1)
}
const hookFiltered = computed(() => hf.status !== '' || !!hf.source || !!hf.type.trim() || !!hf.q.trim() || !!hf.from || !!hf.to)

/* payload 已归一化 {type, data:{payment_intent, amount, metadata:{order_no}}}：
 * 提取关联订单/单号/金额供行内展示（异常形态安全取值） */
const hookOrder = (w) => w.payload?.data?.metadata?.order_no || ''
const hookIntent = (w) => w.payload?.data?.payment_intent || ''
const hookAmount = (w) => {
  const a = w.payload?.data?.amount
  return Number.isFinite(a) ? money(a) : ''
}
const typeTone = (t) => {
  if (!t) return 'tag-done'
  if (t.includes('succeeded') || t.includes('COMPLETED')) return 'tag-paid'
  if (t.includes('failed') || t.includes('canceled') || t.includes('dispute') || t.includes('REVERSED')) return 'tag-error'
  if (t.includes('refunded') || t.includes('REFUNDED')) return 'tag-ship'
  return 'tag-done'
}
const payloadFull = (w) => {
  try { return typeof w.payload === 'string' ? w.payload : JSON.stringify(w.payload, null, 2) } catch (_) { return String(w.payload) }
}

const hookExporting = ref(false)
async function exportHook() {
  if (hookExporting.value) return
  hookExporting.value = true
  try {
    const { all, truncated } = await fetchAllPages((p) => req('GET', hookUrl(p, 100)), { pageSize: 100, maxPages: 20 })
    if (truncated) toast('匹配结果过多，仅导出前 ' + all.length + ' 条', 'error')
    downloadCsv({
      filename: 'webhook_events_' + new Date().toISOString().slice(0, 10).replace(/-/g, ''),
      headers: ['到达时间', '来源', '事件类型', '事件ID', '关联订单', '金额', '处理状态', '处理时间'],
      rows: all.map((w) => [dt(w.created_at), SOURCE_META[w.source] || w.source, w.type, w.event_id,
        hookOrder(w), hookAmount(w), WSTATUS[w.status]?.label ?? w.status, dt(w.processed_at) || '']),
    })
    toast('已导出 ' + all.length + ' 条 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  hookExporting.value = false
}

function load(p = 1) { return st.tab === 'hook' ? loadHook(p) : loadPay(p) }
function setTab(k) {
  if (st.tab === k) return
  st.tab = k
  st.page = slotPages[k]
  load(st.page)
}
onMounted(() => { loadPay(st.page); if (st.tab === 'hook') loadHook(st.page) })
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">支付流水</h1>
      <span class="page-sub">支付记录 / 通道回调事件（幂等去重原文）</span>
    </div>
  </div>

  <div class="otab">
    <button v-for="[k, label] in TABS" :key="k" :class="{ on: st.tab === k }" style="background:none;border:none;cursor:pointer" @click="setTab(k)">{{ label }}</button>
  </div>

  <!-- ===== tab=pay 支付记录 ===== -->
  <div v-if="st.tab === 'pay'">
    <div v-if="!d.pay.loaded" class="card skeleton" style="min-height:280px" />
    <EmptyState v-else-if="d.pay.err && !d.pay.items.length" icon="⚠️" title="支付记录加载失败" :sub="d.pay.err">
      <template #action><button class="btn btn-secondary btn-sm" @click="loadPay(st.page)">重试</button></template>
    </EmptyState>
    <div v-else class="card tbl-wrap">
      <div v-if="d.pay.err" class="err-banner"><span>⚠️ 刷新失败：{{ d.pay.err }}</span><button class="btn btn-secondary btn-sm" @click="loadPay(st.page)">重试</button></div>

      <!-- 状态快捷筛选 + 精确筛选 + 导出 -->
      <div class="filter-bar" style="padding:12px 14px;border-bottom:1px solid var(--gray-light);flex-wrap:wrap">
        <button v-for="[k, label] in PTABS" :key="k" class="ftab" :class="{ on: pf.status === k }" @click="payStatusTab(k)">{{ label }}</button>
        <span style="flex:1"></span>
        <select v-model="pf.provider" class="input" style="width:110px;height:32px" @change="applyPay">
          <option value="">全部通道</option>
          <option value="stripe">Stripe</option>
          <option value="paypal">PayPal</option>
          <option value="mock">Mock</option>
        </select>
        <input v-model="pf.q" class="input" style="width:180px;height:32px" placeholder="订单号 / 邮箱 / 通道单号" @keydown.enter="applyPay">
        <input v-model="pf.from" class="input" style="width:140px;height:32px" type="date" @change="applyPay">
        <span style="color:var(--gray);align-self:center">至</span>
        <input v-model="pf.to" class="input" style="width:140px;height:32px" type="date" @change="applyPay">
        <button class="btn btn-secondary btn-sm" style="height:32px" @click="applyPay">筛选</button>
        <button class="btn btn-ghost btn-sm" style="height:32px" @click="resetPay">重置</button>
        <button class="btn btn-secondary btn-sm" style="height:32px" :disabled="payExporting" @click="exportPay">{{ payExporting ? '导出中…' : '⬇ CSV' }}</button>
      </div>

      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">时间</th><th>订单</th><th>客户</th><th>通道</th><th>金额</th><th>已退</th><th>状态</th><th>通道单号</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in d.pay.items" :key="r.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:10px;white-space:nowrap;color:var(--gray)">{{ dt(r.created_at) || '—' }}</td>
            <td style="white-space:nowrap"><router-link class="ono" :to="{ path: '/order-detail', query: { no: r.order_no } }">{{ r.order_no }}</router-link></td>
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="r.email">{{ r.email }}</td>
            <td><span class="prov-badge" :style="provStyle(r.provider)">{{ provLabel(r.provider) }}</span></td>
            <td style="white-space:nowrap"><b>{{ money(r.amount) }}</b></td>
            <td style="white-space:nowrap;color:var(--gray)">{{ r.refunded_amount ? money(r.refunded_amount) : '—' }}</td>
            <td>
              <span class="tag" :class="PAY[r.status]?.cls">{{ PAY[r.status]?.label ?? r.status }}</span>
              <div v-if="r.failure_reason" style="font-size:11px;color:var(--gray);margin-top:3px;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="r.failure_reason">{{ r.failure_reason }}</div>
            </td>
            <td style="font-family:monospace;font-size:11.5px;color:var(--gray);max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="r.payment_intent">{{ r.payment_intent || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!d.pay.items.length" :icon="payFiltered ? '🔍' : '💳'" :title="payFiltered ? '未找到匹配的支付记录' : '暂无支付记录'" :sub="payFiltered ? '试试调整或清除筛选' : '用户发起支付后，每一笔支付意图都会记录在这里'" />
      <Pagination embed :page="st.page" :pages="d.pay.pages" :total="d.pay.total" unit="笔" @go="loadPay" />
    </div>
  </div>

  <!-- ===== tab=hook 回调事件 ===== -->
  <div v-if="st.tab === 'hook'">
    <div v-if="!d.hook.loaded" class="card skeleton" style="min-height:280px" />
    <EmptyState v-else-if="d.hook.err && !d.hook.items.length" icon="⚠️" title="回调事件加载失败" :sub="d.hook.err">
      <template #action><button class="btn btn-secondary btn-sm" @click="loadHook(st.page)">重试</button></template>
    </EmptyState>
    <div v-else class="card tbl-wrap">
      <div v-if="d.hook.err" class="err-banner"><span>⚠️ 刷新失败：{{ d.hook.err }}</span><button class="btn btn-secondary btn-sm" @click="loadHook(st.page)">重试</button></div>

      <div class="filter-bar" style="padding:12px 14px;border-bottom:1px solid var(--gray-light);flex-wrap:wrap">
        <select v-model="hf.status" class="input" style="width:110px;height:32px" @change="applyHook">
          <option value="">全部状态</option>
          <option value="0">待处理</option>
          <option value="1">处理成功</option>
          <option value="2">已跳过</option>
        </select>
        <select v-model="hf.source" class="input" style="width:110px;height:32px" @change="applyHook">
          <option value="">全部来源</option>
          <option value="stripe">Stripe</option>
          <option value="paypal">PayPal</option>
          <option value="mock">Mock</option>
        </select>
        <input v-model="hf.type" class="input" style="width:200px;height:32px" list="hook-types" placeholder="事件类型（精确）" @keydown.enter="applyHook">
        <datalist id="hook-types">
          <option v-for="t in WTYPES" :key="t" :value="t"></option>
        </datalist>
        <input v-model="hf.q" class="input" style="width:170px;height:32px" placeholder="事件ID / 类型" @keydown.enter="applyHook">
        <input v-model="hf.from" class="input" style="width:140px;height:32px" type="date" @change="applyHook">
        <span style="color:var(--gray);align-self:center">至</span>
        <input v-model="hf.to" class="input" style="width:140px;height:32px" type="date" @change="applyHook">
        <button class="btn btn-secondary btn-sm" style="height:32px" @click="applyHook">筛选</button>
        <button class="btn btn-ghost btn-sm" style="height:32px" @click="resetHook">重置</button>
        <button class="btn btn-secondary btn-sm" style="height:32px" :disabled="hookExporting" @click="exportHook">{{ hookExporting ? '导出中…' : '⬇ CSV' }}</button>
      </div>

      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">到达时间</th><th>来源</th><th>事件类型</th><th>关联订单</th><th>金额</th><th>状态</th><th>处理时间</th><th>事件ID</th>
        </tr></thead>
        <tbody>
          <tr v-for="w in d.hook.items" :key="w.event_id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:10px;white-space:nowrap;color:var(--gray)">{{ dt(w.created_at) || '—' }}</td>
            <td><span class="prov-badge" :style="provStyle(w.source)">{{ SOURCE_META[w.source] || w.source }}</span></td>
            <td style="max-width:210px">
              <span class="tag" :class="typeTone(w.type)" style="font-size:11.5px">{{ w.type }}</span>
              <details style="margin-top:3px">
                <summary style="cursor:pointer;color:var(--gray);font-size:11px;user-select:none">载荷原文</summary>
                <pre style="margin-top:6px;background:#F6F4F5;border-radius:8px;padding:10px;font-size:11.5px;line-height:1.6;max-height:260px;overflow:auto">{{ payloadFull(w) }}</pre>
              </details>
            </td>
            <td style="white-space:nowrap">
              <router-link v-if="hookOrder(w)" class="ono" :to="{ path: '/order-detail', query: { no: hookOrder(w) } }">{{ hookOrder(w) }}</router-link>
              <span v-else style="color:var(--gray)" :title="hookIntent(w) || ''">{{ hookIntent(w) ? '按单号定位' : '—' }}</span>
            </td>
            <td style="white-space:nowrap">{{ hookAmount(w) || '—' }}</td>
            <td><span class="tag" :class="WSTATUS[w.status]?.cls">{{ WSTATUS[w.status]?.label ?? w.status }}</span></td>
            <td style="white-space:nowrap;color:var(--gray)">{{ dt(w.processed_at) || '—' }}</td>
            <td style="font-family:monospace;font-size:11.5px;color:var(--gray);max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="w.event_id">{{ w.event_id }}</td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!d.hook.items.length" :icon="hookFiltered ? '🔍' : '🔔'" :title="hookFiltered ? '未找到匹配的回调事件' : '暂无回调事件'" :sub="hookFiltered ? '试试调整或清除筛选' : 'Stripe / PayPal 的支付回调（含重试与跳过）都会记录在这里'" />
      <Pagination embed :page="st.page" :pages="d.hook.pages" :total="d.hook.total" unit="条" @go="loadHook" />
    </div>
  </div>
</template>

<style scoped>
/* 通道徽标：按通道品牌色浅底（对齐 LogsView 实体徽标做法） */
.prov-badge{display:inline-block;font-size:11px;font-weight:600;border-radius:999px;padding:2px 10px;white-space:nowrap}
/* 状态快捷筛选小页签（对齐各列表卡内 ftab 样式） */
.ftab{border:1.5px solid var(--gray-light);background:#fff;color:var(--gray);border-radius:999px;
  padding:5px 13px;font-size:12.5px;font-weight:600;cursor:pointer;transition:all .15s}
.ftab:hover{border-color:var(--rose);color:var(--plum)}
.ftab.on{background:var(--plum);border-color:var(--plum);color:#fff}
.err-banner{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 14px;margin:12px 12px 0;background:var(--pale-error);color:var(--error);border-radius:10px;font-size:12.5px}
</style>
