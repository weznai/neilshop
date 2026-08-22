<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import { dt } from '../composables/format'

const route = useRoute()
const router = useRouter()
const items = ref([])
const total = ref(0)
const pages = ref(1)
const page = ref(1)
const perPage = ref(20)
const status = ref(null)
const q = ref('')
/* 时间范围筛选：date input 原生值即 YYYY-MM-DD，直传后端 date_from/date_to */
const dateFrom = ref('')
const dateTo = ref('')
const loaded = ref(false)
const refreshing = ref(false)
/* O2 错误空态：首载失败且无数据时表格区渲染「加载失败+重试」；有旧数据仍走 toast 提示 */
const loadErr = ref('')
/* OrderStatus 真值：0待付 1已付 2履约中 3已发货 4已送达 5已完成 8已取消 9已退款(全额) */
const OSTATUS = {
  0: ['待支付', 'tag-pending'], 1: ['已支付', 'tag-paid'], 2: ['备货中', 'tag-pending'],
  3: ['已发货', 'tag-ship'], 4: ['已送达', 'tag-ship'], 5: ['已完成', 'tag-done'],
  8: ['已取消', 'tag-error'], 9: ['已退款', 'tag-error'],
}
/* ShipmentStatus（履约列，列表已返回 shipping_status）：0待打单 1已打单待拣货 2待交接 3运输中 4送达 5异常 6面单作废 */
const SHSTATUS = {
  0: ['待打单', 'tag-pending'], 1: ['待拣货', 'tag-pending'], 2: ['待交接', 'tag-pending'],
  3: ['运输中', 'tag-ship'], 4: ['已送达', 'tag-done'], 5: ['异常', 'tag-error'], 6: ['面单作废', 'tag-error'],
}
const TABS = [
  ['all', '全部', null], ['s0', '待支付', 0], ['s1', '已支付', 1], ['s2', '备货中', 2],
  ['s3', '已发货', 3], ['s4', '已送达', 4], ['s5', '已完成', 5], ['s8', '已取消', 8], ['s9', '已退款', 9],
]
const statusLabel = computed(() => (status.value == null ? '' : OSTATUS[status.value]?.[0] || ''))

/* URL 筛选同步：初始化读 route.query（dashboard 深链 ?status=1 等），变化 router.replace（可分享/可回退） */
function initFromQuery() {
  const rq = route.query
  if (typeof rq.q === 'string') q.value = rq.q
  /* 日期仅接受合法 YYYY-MM-DD，脏 query 不回填 */
  if (/^\d{4}-\d{2}-\d{2}$/.test(rq.date_from || '')) dateFrom.value = rq.date_from
  if (/^\d{4}-\d{2}-\d{2}$/.test(rq.date_to || '')) dateTo.value = rq.date_to
  if (rq.status !== undefined && rq.status !== '') {
    const n = Number(rq.status)
    if (OSTATUS[n]) status.value = n
  }
  const p = parseInt(rq.page, 10)
  if (Number.isInteger(p) && p >= 1) page.value = p
  const pp = parseInt(rq.per_page, 10)
  if ([20, 50, 100].includes(pp)) perPage.value = pp
  /* sort 白名单校验，脏 query 不回填 */
  if (SORTABLE.includes(rq.sort)) sort.value = rq.sort
}
function syncUrl() {
  const query = {}
  if (q.value.trim()) query.q = q.value.trim()
  if (dateFrom.value) query.date_from = dateFrom.value
  if (dateTo.value) query.date_to = dateTo.value
  if (status.value != null) query.status = status.value
  if (page.value > 1) query.page = page.value
  if (perPage.value !== 20) query.per_page = perPage.value
  if (sort.value) query.sort = sort.value
  if (JSON.stringify(query) !== JSON.stringify(route.query)) router.replace({ query })
}

async function load() {
  /* 筛选/翻页保留旧数据不清空，骨架只在首次出现；勾选随列表刷新清空（防跨页误发货） */
  refreshing.value = true
  selected.value = []
  /* 后端支持可选 per_page（钳制 10-100），分页以响应 pages/total 为准 */
  const params = { page: page.value, per_page: perPage.value }
  if (status.value != null) params.status = status.value
  if (q.value.trim()) params.q = q.value.trim()
  if (dateFrom.value) params.date_from = dateFrom.value
  if (dateTo.value) params.date_to = dateTo.value
  if (sort.value) params.sort = sort.value
  try {
    const d = await req('GET', '/api/admin/trade/orders?' + new URLSearchParams(params))
    items.value = d.items || []
    total.value = d.total ?? 0
    pages.value = d.pages ?? 1
    loadErr.value = ''
    syncUrl()
  } catch (e) {
    loadErr.value = e.message || '加载失败'
    toast('加载失败：' + (e.message || ''), 'error')
  }
  loaded.value = true
  refreshing.value = false
}
onMounted(() => { initFromQuery(); load() })

function tab(sv) { status.value = sv; page.value = 1; load() }
function clearDates() { dateFrom.value = ''; dateTo.value = ''; page.value = 1; load() }
function clearSearch() { q.value = ''; page.value = 1; load() }
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
/* 时间统一走 format.js 的 dt（补 Z 修时区） */

/* 服务端排序：sort 直传后端（placed_at/total，- 前缀降序），三态循环（无 → 升 → 降 → 无），切换重置页码 */
const SORTABLE = ['placed_at', '-placed_at', 'total', '-total']
const sort = ref('')
function sortBy(k) {
  sort.value = sort.value === k ? '-' + k : (sort.value === '-' + k ? '' : k)
  page.value = 1
  load()
}
const sortInd = (k) => (sort.value === k ? '▲' : sort.value === '-' + k ? '▼' : '')

const shipDlg = ref(null) /* {order_no} */
const carrier = ref('USPS')
const tracking = ref('')
async function ship(o) { shipDlg.value = o; tracking.value = ''; carrier.value = 'USPS' }
/* 提交防抖：请求期间按钮 busy+disabled，双击不会重复 POST */
const shipSubmitting = ref(false)
async function shipConfirm() {
  if (shipSubmitting.value) return
  const o = shipDlg.value
  if (!tracking.value.trim()) { toast('请填写物流单号', 'error'); return }
  shipSubmitting.value = true
  try {
    await req('POST', `/api/admin/trade/orders/${o.order_no}/ship`, { carrier: carrier.value, tracking_no: tracking.value.trim() })
    toast(`${o.order_no} 已发货 ✓`, 'success')
    shipDlg.value = null
    load()
  } catch (e) { toast('发货失败：' + (e.data?.detail || e.message), 'error') }
  shipSubmitting.value = false
}

/* 行内取消订单：仅 status=0 可取消，409 时转后端语义文案 */
const cancelDlg = ref(null) /* {order_no} */
const cancelSubmitting = ref(false)
async function cancelConfirm() {
  if (cancelSubmitting.value) return
  const o = cancelDlg.value
  cancelSubmitting.value = true
  try {
    await req('POST', `/api/admin/trade/orders/${o.order_no}/cancel`)
    toast(`${o.order_no} 已取消`, 'success')
    cancelDlg.value = null
    load() /* 刷新当前页 */
  } catch (e) {
    toast(e.status === 409 ? '仅待支付订单可取消' : '取消失败：' + (e.data?.detail || e.message), 'error')
  }
  cancelSubmitting.value = false
}

/* 批量发货勾选：selected 按勾选顺序存 order_no（与单号行一一对应），仅 status 1/2 可勾，load() 时清空 */
const selected = ref([])
const shippable = computed(() => items.value.filter((o) => o.status === 1 || o.status === 2))
const allChecked = computed(() => shippable.value.length > 0 && shippable.value.every((o) => selected.value.includes(o.order_no)))
const someChecked = computed(() => shippable.value.some((o) => selected.value.includes(o.order_no)))
function toggleAll() {
  const nos = shippable.value.map((o) => o.order_no)
  selected.value = nos.every((n) => selected.value.includes(n))
    ? selected.value.filter((n) => !nos.includes(n))
    : [...selected.value, ...nos.filter((n) => !selected.value.includes(n))]
}
function toggleOne(no, checked) {
  selected.value = checked ? [...selected.value, no] : selected.value.filter((n) => n !== no)
}
/* 批量发货弹窗：textarea 每行一个单号，行序对应勾选序 */
const batchDlg = ref(false)
const batchCarrier = ref('USPS')
const batchTrackings = ref('')
const batchSubmitting = ref(false)
function openBatchShip() { batchCarrier.value = 'USPS'; batchTrackings.value = ''; batchDlg.value = true }
async function batchShipConfirm() {
  if (batchSubmitting.value) return
  const nos = [...selected.value]
  const lines = batchTrackings.value.split('\n').map((s) => s.trim()).filter(Boolean)
  if (lines.length !== nos.length) { toast(`物流单号 ${lines.length} 行，与勾选 ${nos.length} 单不一致`, 'error'); return }
  batchSubmitting.value = true
  /* 逐单串行 POST，单笔失败不中断，最终汇总成功/失败数 */
  let ok = 0, fail = 0
  for (let i = 0; i < nos.length; i++) {
    try {
      await req('POST', `/api/admin/trade/orders/${nos[i]}/ship`, { carrier: batchCarrier.value, tracking_no: lines[i] })
      ok++
    } catch (_) { fail++ }
  }
  batchSubmitting.value = false
  batchDlg.value = false
  toast(`成功 ${ok} 单，失败 ${fail} 单`, fail > 0 ? 'error' : 'success')
  load()
}

const exporting = ref(false)
/* CSV 导出：per_page=100 循环拉全量，页数按 total/100 重算；上限 50 页（5000 单）防滥用 */
const EXPORT_PER_PAGE = 100
const EXPORT_MAX_PAGES = 50
async function exportCsv() {
  if (exporting.value) return
  exporting.value = true
  try {
    const params = { page: 1, per_page: EXPORT_PER_PAGE }
    if (status.value != null) params.status = status.value
    if (q.value.trim()) params.q = q.value.trim()
    if (dateFrom.value) params.date_from = dateFrom.value
    if (dateTo.value) params.date_to = dateTo.value
    if (sort.value) params.sort = sort.value
    const first = await req('GET', '/api/admin/trade/orders?' + new URLSearchParams(params))
    const all = [...(first.items || [])]
    const totalMatch = first.total ?? all.length
    const maxPage = Math.min(Math.ceil(totalMatch / EXPORT_PER_PAGE) || 1, EXPORT_MAX_PAGES)
    /* 第 2 页起每 5 页一批 Promise.all 并发（批间 await 控压，结果按页序拼接） */
    for (let s = 2; s <= maxPage; s += 5) {
      const end = Math.min(s + 4, maxPage)
      const batch = await Promise.all(
        Array.from({ length: end - s + 1 }, (_, i) =>
          req('GET', '/api/admin/trade/orders?' + new URLSearchParams({ ...params, page: s + i })))
      )
      for (const d of batch) all.push(...(d.items || []))
    }
    if (Math.ceil(totalMatch / EXPORT_PER_PAGE) > EXPORT_MAX_PAGES) {
      toast(`匹配结果超过 ${EXPORT_MAX_PAGES * EXPORT_PER_PAGE} 单，仅导出前 ${all.length} 单`, 'error')
    }
    /* CSV 转义：含逗号/引号/换行的字段包引号并双写引号 */
    const cell = (v) => {
      const s = String(v ?? '')
      return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
    }
    const rows = [['订单号', '邮箱', '金额', '状态', '履约', '下单时间', '支付时间', '留言'],
      ...all.map((o) => [o.order_no, o.email, money(o.grand_total), OSTATUS[o.status]?.[0], SHSTATUS[o.shipping_status]?.[0], dt(o.placed_at), o.paid_at ? dt(o.paid_at) : '', o.note || ''])]
    const csv = rows.map((r) => r.map(cell).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `orders-${statusLabel.value || '全部'}-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast('已导出 ' + all.length + ' 单 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  exporting.value = false
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">订单管理
        <span v-if="refreshing" style="font-size:12px;color:var(--gray);font-weight:400;margin-left:6px">⟳ 刷新中…</span>
      </h1>
      <span class="page-sub">共 {{ total }} 单<template v-if="statusLabel"> · 筛选：{{ statusLabel }}</template><template v-if="dateFrom || dateTo"> · {{ dateFrom || '…' }} ~ {{ dateTo || '…' }}</template><template v-if="q.trim()"> · 关键词“{{ q.trim() }}”</template></span>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <span style="font-size:12px;color:var(--gray)">每页</span>
      <select v-model.number="perPage" class="input" aria-label="每页条数" style="width:auto;height:36px;font-size:13px" @change="page = 1; load()">
        <option :value="20">20 条/页</option>
        <option :value="50">50 条/页</option>
        <option :value="100">100 条/页</option>
      </select>
      <div style="position:relative">
        <input v-model="q" class="input" style="width:220px;padding-right:30px" placeholder="搜订单号 / 邮箱" @keydown.enter="page = 1; load()">
        <button v-if="q" type="button" class="q-clear" aria-label="清空搜索" @click="clearSearch">×</button>
      </div>
      <button class="btn btn-secondary" @click="page = 1; load()">搜索</button>
      <button class="btn btn-secondary" :disabled="exporting" @click="exportCsv">{{ exporting ? '导出中…' : '⬇ CSV' }}</button>
    </div>
  </div>

  <div class="otab" style="flex-wrap:wrap">
    <button
      v-for="[k, label, sv] in TABS" :key="k"
      :class="{ on: status === sv }"
      style="background:none;border:none;cursor:pointer"
      @click="tab(sv)"
    >{{ label }}</button>
  </div>

  <!-- 时间范围筛选卡 -->
  <div class="card filter-bar" style="padding:14px 16px;margin-bottom:14px;align-items:flex-end">
    <div class="field" style="margin:0">
      <label>下单起</label>
      <input v-model="dateFrom" class="input" style="width:160px" type="date" @change="page = 1; load()">
    </div>
    <div class="field" style="margin:0">
      <label>下单止</label>
      <input v-model="dateTo" class="input" style="width:160px" type="date" @change="page = 1; load()">
    </div>
    <button v-if="dateFrom && dateTo" class="btn btn-ghost btn-sm" style="height:36px" @click="clearDates">清空</button>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px" />

  <div v-else class="card tbl-wrap">
    <div class="dhead">
      <h3 class="dtitle">订单列表</h3>
      <!-- 批量操作条：勾选后出现 -->
      <div v-if="selected.length" style="display:flex;align-items:center;gap:8px;font-size:13px;white-space:nowrap">
        已选 <b style="color:var(--plum)">{{ selected.length }}</b> 单
        <button class="btn btn-primary btn-sm" @click="openBatchShip">📦 批量发货</button>
        <button class="btn btn-secondary btn-sm" @click="selected = []">取消选择</button>
      </div>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="text-align:left;color:var(--gray)">
          <th style="width:32px;padding:10px" title="全选本页可发货订单（已支付/备货中）"><input type="checkbox" style="cursor:pointer" :checked="allChecked" :indeterminate.prop="someChecked && !allChecked" @change="toggleAll"></th>
          <th style="padding:10px">订单号</th><th>客户</th><th>留言</th>
          <th class="sortable" title="点击排序" @click="sortBy('total')">金额<span v-if="sortInd('total')" class="sort-ind">{{ sortInd('total') }}</span></th>
          <th>状态</th><th>履约</th>
          <th class="sortable" title="点击排序" @click="sortBy('placed_at')">下单时间<span v-if="sortInd('placed_at')" class="sort-ind">{{ sortInd('placed_at') }}</span></th>
          <th>支付时间</th>
          <th style="text-align:right">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="o in items" :key="o.order_no" style="border-top:1px solid var(--gray-light)">
          <td style="padding:11px 10px"><input type="checkbox" style="cursor:pointer" :checked="selected.includes(o.order_no)" :disabled="o.status !== 1 && o.status !== 2" @change="toggleOne(o.order_no, $event.target.checked)"></td>
          <td><b>{{ o.order_no }}</b></td>
          <td>{{ esc(o.email) }}</td>
          <td style="max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--gray)" :title="o.note || ''">{{ o.note ? esc(o.note) : '—' }}</td>
          <td><b style="color:var(--plum)">{{ money(o.grand_total) }}</b></td>
          <td><span class="tag" :class="OSTATUS[o.status]?.[1]">{{ OSTATUS[o.status]?.[0] }}</span></td>
          <td><span class="tag" :class="SHSTATUS[o.shipping_status]?.[1] || 'tag-pending'" :title="'shipping_status: ' + o.shipping_status">{{ SHSTATUS[o.shipping_status]?.[0] || '—' }}</span></td>
          <td style="color:var(--gray)">{{ dt(o.placed_at) || '—' }}</td>
          <td style="color:var(--gray)">{{ dt(o.paid_at) || '—' }}</td>
          <td style="text-align:right;white-space:nowrap">
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/order-detail', query: { no: o.order_no } }">详情</router-link>
            <button v-if="o.status === 1 || o.status === 2" class="btn btn-primary btn-sm" style="margin-left:6px" @click="ship(o)">📦 发货</button>
            <button v-if="o.status === 0" class="btn btn-ghost btn-sm row-cancel" style="margin-left:6px" @click="cancelDlg = o">取消</button>
          </td>
        </tr>
      </tbody>
    </table>
    <EmptyState v-if="!items.length && loadErr" icon="⚠️" title="加载失败" :sub="loadErr">
      <template #action><button class="btn btn-secondary btn-sm" @click="load">重试</button></template>
    </EmptyState>
    <EmptyState v-else-if="!items.length" icon="📭" title="该状态下暂无订单" sub="试试其他筛选或搜索词" />
  </div>

  <Pagination v-if="loaded" :page="page" :pages="pages" :total="total" unit="单" @go="page = $event; load()" />

  <!-- 发货弹窗 -->
  <div v-if="shipDlg" class="modal open" @click.self="shipDlg = null">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="shipDlg = null">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">📦 发货 {{ shipDlg.order_no }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:14px">发货后扣库存并向客户发送物流邮件。</p>
      <div class="field">
        <label>承运商</label>
        <select v-model="carrier" class="input">
          <option>USPS</option><option>UPS</option><option>FedEx</option><option>DHL</option>
        </select>
      </div>
      <div class="field">
        <label>物流单号</label>
        <input v-model="tracking" class="input" placeholder="9400…">
      </div>
      <button class="btn btn-primary btn-block" style="margin-top:12px" :disabled="shipSubmitting" @click="shipConfirm">{{ shipSubmitting ? '发货中…' : '确认发货' }}</button>
    </div>
  </div>

  <!-- 批量发货弹窗：单号行序对应勾选序 -->
  <div v-if="batchDlg" class="modal open" @click.self="!batchSubmitting && (batchDlg = false)">
    <div class="modal-box" style="max-width:480px">
      <button class="modal-x" @click="!batchSubmitting && (batchDlg = false)">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">📦 批量发货 · 已选 {{ selected.length }} 单</h3>
      <p style="font-size:12px;color:var(--gray);margin-bottom:14px;word-break:break-all">勾选顺序：{{ selected.join(' → ') }}</p>
      <div class="field">
        <label>承运商（全部单共用）</label>
        <select v-model="batchCarrier" class="input">
          <option>USPS</option><option>UPS</option><option>FedEx</option><option>DHL</option>
        </select>
      </div>
      <div class="field">
        <label>物流单号（每行一个）</label>
        <textarea v-model="batchTrackings" class="input" style="height:auto;min-height:120px;padding:10px 14px;resize:vertical;font-family:inherit" :placeholder="'每行一个单号，顺序对应勾选顺序，共 ' + selected.length + ' 行'"></textarea>
      </div>
      <button class="btn btn-primary btn-block" style="margin-top:12px" :disabled="batchSubmitting" @click="batchShipConfirm">{{ batchSubmitting ? '发货中…' : '确认发货' }}</button>
    </div>
  </div>

  <!-- 取消订单确认弹窗 -->
  <ConfirmDialog
    :open="!!cancelDlg"
    title="取消订单"
    :body="`取消订单 ${cancelDlg?.order_no}，仅待支付可取消，不可恢复`"
    confirm-text="确认取消"
    danger
    :busy="cancelSubmitting"
    @confirm="cancelConfirm"
    @close="cancelDlg = null"
  />
</template>

<style scoped>
/* 行内取消按钮：红字 ghost（悬停浅红，同详情页危险操作） */
.row-cancel{color:var(--error)}
.row-cancel:hover{background:var(--pale-error)}
/* 搜索框清空钮：悬浮输入框右侧 */
.q-clear{position:absolute;right:8px;top:50%;transform:translateY(-50%);width:17px;height:17px;border:none;border-radius:50%;background:var(--gray-light);color:#fff;font-size:11px;line-height:1;cursor:pointer;padding:0}
.q-clear:hover{background:var(--gray)}
</style>
