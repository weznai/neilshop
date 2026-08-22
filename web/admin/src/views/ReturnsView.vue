<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { money, dt } from '../composables/format'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const rmas = ref([])
const exch = ref([])
const loaded = ref(false)
/* RmaStatus 真值：0申请 1已批准 2标签已发 3在途 4已收货 5已退款 6已拒绝 7部分退款
 * 后台流转：approve 0→2（发退货标签）· receive 1/2/3→4（收货回补库存）· refund 4→5 */
const RSTATUS = {
  0: ['待审核', 'tag-pending'], 1: ['已批准', 'tag-paid'], 2: ['标签已发', 'tag-paid'],
  3: ['退货运送中', 'tag-pending'], 4: ['已收货', 'tag-ship'], 5: ['已退款', 'tag-done'],
  6: ['已拒绝', 'tag-error'], 7: ['部分退款', 'tag-done'],
}
/* RmaReason 真值（models/fulfill.py）：1尺码 2质量 3不喜欢 4损坏 5发错 6其他 */
const RMA_REASON = { 1: '尺码不合', 2: '质量问题', 3: '不喜欢', 4: '损坏', 5: '发错货', 6: '其他' }
const reasonLabel = (r) => RMA_REASON[r.reason] || r.reason_detail || '—'
/* Exchange 真值：0申请 1已批准待重发 2待买家补差价 3已重发 4已完成 5已拒绝
 * approve 0→(diff>0?2:1) · mark-paid 2→1 · ship 1→3 · complete 3→4 · reject 0→5 */
const ESTATUS = {
  0: ['待审核', 'tag-pending'], 1: ['已批准·待重发', 'tag-paid'], 2: ['待买家付差价', 'tag-pending'],
  3: ['已重发', 'tag-ship'], 4: ['已完成', 'tag-done'], 5: ['已拒绝', 'tag-error'],
}

/* URL 同步：tab 主档位 + rs/es 两列表状态筛选（存 tab key 字符串）+ rp/ep 两分页 + 共用搜索词 q */
const state = reactive({ tab: 'rma', rs: 'all', es: 'all', rp: 1, ep: 1, q: '' })
useQuerySync(state, { nums: ['rp', 'ep'], defaults: { tab: 'rma', rs: 'all', es: 'all', rp: 1, ep: 1, q: '' } })
const tab = computed(() => (state.tab === 'exch' ? 'exch' : 'rma'))

/* 刷新指示：并发计数（tab/筛选只刷单列表，load 刷两个），对齐订单页「⟳ 刷新中…」 */
const loadCnt = ref(0)
const refreshing = computed(() => loadCnt.value > 0)

/* RMA 状态筛选 + 服务端分页（page/per_page=20，响应含 total/pages）
 * 后端 status 仅支持单值（router_admin list_rmas 为 Optional[int]，已核对不支持逗号）：
 * 「待收货」= 标签已发(2)+在途(3) 拆两次请求各拉前 100 合并，前端分页；>100 截断时 toast 提示 */
const RMA_PER_PAGE = 20
const rmaPages = ref(1)
const rmaTotal = ref(0)
const RTABS = [
  ['all', '全部', null], ['s0', '待审核', [0]], ['s23', '待收货', [2, 3]],
  ['s4', '已收货', [4]], ['s5', '已退款', [5]], ['s6', '已拒绝', [6]], ['s7', '部分退款', [7]],
]
/* 高亮按 key 字符串比较（修数组引用比较 R9），筛选值由 key 派生避免双份状态 */
const rmaFilter = computed(() => RTABS.find(([k]) => k === state.rs)?.[2] ?? null)
async function loadRmas() {
  loadCnt.value++
  const f = rmaFilter.value
  try {
    if (!f || f.length === 1) {
      const params = { page: state.rp, per_page: RMA_PER_PAGE }
      if (f) params.status = f[0]
      if (state.q.trim()) params.q = state.q.trim()
      const d = await req('GET', '/api/admin/trade/rmas?' + new URLSearchParams(params))
      rmas.value = d.items || []
      rmaTotal.value = d.total ?? 0
      rmaPages.value = d.pages ?? 1
    } else {
      const qp = { per_page: 100 }
      if (state.q.trim()) qp.q = state.q.trim()
      const res = await Promise.all(
        f.map((s) => req('GET', '/api/admin/trade/rmas?' + new URLSearchParams({ ...qp, status: s }))),
      )
      const all = res
        .flatMap((d) => d.items || [])
        .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
      /* 任意一状态超过 100 条被截断 → 提示改用单状态筛选 */
      if (res.some((d) => (d.total ?? 0) > (d.items || []).length)) {
        toast('「待收货」某状态超过 100 条，仅显示最近 100 条；建议按状态细分筛选查看', 'error')
      }
      rmaTotal.value = all.length
      rmaPages.value = Math.max(1, Math.ceil(all.length / RMA_PER_PAGE))
      rmas.value = all.slice((state.rp - 1) * RMA_PER_PAGE, state.rp * RMA_PER_PAGE)
    }
  } catch (e) { rmas.value = []; rmaTotal.value = 0; rmaPages.value = 1; toast('退货列表加载失败：' + (e.message || ''), 'error') }
  loadCnt.value--
}
function rmaTab(k) { state.rs = k; state.rp = 1; loadRmas() }

/* 换货状态筛选 + 分页（后端支持 status/page/size，size=50） */
const exPages = ref(1)
const exTotal = ref(0)
const ETABS = [
  ['all', '全部', null], ['s0', '待审核', 0], ['s2', '待付差价', 2], ['s1', '待重发', 1],
  ['s3', '已重发', 3], ['s4', '已完成', 4], ['s5', '已拒绝', 5],
]
const exFilter = computed(() => ETABS.find(([k]) => k === state.es)?.[2] ?? null)
async function loadExch() {
  loadCnt.value++
  const params = { page: state.ep, size: 50 }
  if (exFilter.value != null) params.status = exFilter.value
  if (state.q.trim()) params.q = state.q.trim()
  try {
    const d = await req('GET', '/api/admin/trade/exchanges?' + new URLSearchParams(params))
    exch.value = d.items || []
    exTotal.value = d.total ?? 0
    exPages.value = d.pages ?? 1
  } catch (e) {
    exch.value = []; exTotal.value = 0; exPages.value = 1
    toast('换货列表加载失败：' + (e.message || ''), 'error')
  }
  loadCnt.value--
}
function exTab(k) { state.es = k; state.ep = 1; loadExch() }

async function load() { await Promise.all([loadRmas(), loadExch()]) }
onMounted(async () => { await load(); loaded.value = true })

/* 顶栏搜索：q 两 tab 共用（分别传给各自请求），回车/按钮触发并重置两列表页码 */
function search() { state.rp = 1; state.ep = 1; load() }

/* CSV 导出：仅导出当前 tab 当前筛选（状态+关键词）下全部页；转义/BOM 写法照抄 OrdersView */
const exporting = ref(false)
const EXPORT_MAX_PAGES = 20
const csvCell = (v) => {
  const s = String(v ?? '')
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}
/* 循环翻页拉全量：按首页 total 重算页数；size 为该接口单页条数（rma per_page=100 / exch size=50） */
async function fetchAll(url, params, size) {
  const first = await req('GET', url + '?' + new URLSearchParams(params))
  const all = [...(first.items || [])]
  const totalMatch = first.total ?? all.length
  const maxPage = Math.min(Math.ceil(totalMatch / size) || 1, EXPORT_MAX_PAGES)
  for (let p = 2; p <= maxPage; p++) {
    params.page = p
    const d = await req('GET', url + '?' + new URLSearchParams(params))
    all.push(...(d.items || []))
  }
  return { all, overflow: Math.ceil(totalMatch / size) > EXPORT_MAX_PAGES }
}
async function exportCsv() {
  if (exporting.value) return
  exporting.value = true
  try {
    const kw = state.q.trim()
    let all = [], overflow = false
    if (tab.value === 'rma') {
      const f = rmaFilter.value
      if (f && f.length > 1) {
        /* 「待收货」组合筛选：两状态各拉前 100 合并（与列表口径一致，超 100 截断提示） */
        const qp = { per_page: 100 }
        if (kw) qp.q = kw
        const res = await Promise.all(f.map((s) => req('GET', '/api/admin/trade/rmas?' + new URLSearchParams({ ...qp, status: s }))))
        all = res.flatMap((d) => d.items || []).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
        overflow = res.some((d) => (d.total ?? 0) > (d.items || []).length)
      } else {
        const params = { page: 1, per_page: 100 }
        if (f) params.status = f[0]
        if (kw) params.q = kw
        const r = await fetchAll('/api/admin/trade/rmas', params, 100)
        all = r.all; overflow = r.overflow
      }
    } else {
      const params = { page: 1, size: 50 }
      if (exFilter.value != null) params.status = exFilter.value
      if (kw) params.q = kw
      const r = await fetchAll('/api/admin/trade/exchanges', params, 50)
      all = r.all; overflow = r.overflow
    }
    if (overflow) toast('匹配结果过多，仅导出前 ' + all.length + ' 条', 'error')
    const rows = [['单号', '订单号', '邮箱', '状态', '金额', '原因', '创建时间'],
      ...all.map((r) => tab.value === 'rma'
        ? [r.rma_no, r.order_no, r.email, RSTATUS[r.status]?.[0], money(r.refund_amount), reasonLabel(r), dt(r.created_at)]
        : [r.exchange_no, r.order_no, r.email, ESTATUS[r.status]?.[0], r.price_diff ? money(r.price_diff) : '', '', dt(r.created_at)])]
    const csv = rows.map((r) => r.map(csvCell).join(',')).join('\n')
    const label = (tab.value === 'rma' ? RTABS.find(([k]) => k === state.rs)?.[1] : ETABS.find(([k]) => k === state.es)?.[1]) || '全部'
    const url = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${tab.value === 'rma' ? 'rmas' : 'exchanges'}-${label}-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast('已导出 ' + all.length + ' 条 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  exporting.value = false
}

/* 统一确认弹窗（替代原生 confirm）：pending 记录待发请求；refund 危险态、reject 需填拒绝原因 */
const cfm = reactive({ open: false, title: '', body: '', danger: false, reasonLabel: '', reasonPlaceholder: '', confirmText: '确认', pending: null })
const submitting = ref(false)
function askRma(r, action) {
  let title = '', body = `退货单 ${r.rma_no}`, confirmText = '确认', danger = false
  if (action === 'approve') { title = '批准退货'; body += ' · 将向客户发送退货标签邮件'; confirmText = '批准' }
  else if (action === 'receive') { title = '确认收货'; body += ` · 将回补库存 ×${r.qty}` }
  else if (action === 'refund') {
    title = '执行退款'; danger = true; confirmText = '确认退款'
    body = `退款金额 ${money(r.refund_amount)} · 退货单号 ${r.rma_no} · 将回补库存，操作不可撤销`
  }
  cfm.title = title; cfm.body = body; cfm.danger = danger
  cfm.reasonLabel = ''; cfm.reasonPlaceholder = ''; cfm.confirmText = confirmText
  cfm.pending = { kind: 'rma', no: r.rma_no, action, label: title }
  cfm.open = true
}
function askExch(x, action) {
  let title = '', confirmText = '确认'
  if (action === 'approve') { title = '批准换货'; confirmText = '批准' }
  else if (action === 'mark-paid') { title = '标记已付差价'; confirmText = '标记' }
  else if (action === 'complete') { title = '完成换货'; confirmText = '完成' }
  else if (action === 'reject') { title = '拒绝换货'; confirmText = '确认拒绝' }
  cfm.title = title; cfm.body = `换货单 ${x.exchange_no}`; cfm.danger = false
  /* reject 走原因输入模式：confirm 回调把 reason 放进请求 body（ExchangeRejectRequest） */
  cfm.reasonLabel = action === 'reject' ? '拒绝原因' : ''
  cfm.reasonPlaceholder = action === 'reject' ? '如：库存不足 / 不符合换货政策' : ''
  cfm.confirmText = confirmText
  cfm.pending = { kind: 'exch', no: x.exchange_no, action, label: title }
  cfm.open = true
}
async function doConfirm(reason) {
  if (submitting.value || !cfm.pending) return
  submitting.value = true
  const { kind, no, action, label } = cfm.pending
  try {
    const url = `/api/admin/trade/${kind === 'rma' ? 'rmas' : 'exchanges'}/${no}/${action}`
    await req('POST', url, action === 'reject' ? { reason } : undefined)
    toast(`${label} ✓`, 'success')
    cfm.open = false
    load()
  } catch (e) { toast(`${label}失败：` + (e.data?.detail || e.message), 'error') }
  submitting.value = false
}

/* 换货重发弹窗：ShipRequest 需 carrier + tracking_no */
const shipDlg = ref(null)
const exCarrier = ref('USPS')
const exTracking = ref('')
const shipSubmitting = ref(false)
function exShip(x) { shipDlg.value = x; exTracking.value = ''; exCarrier.value = 'USPS' }
async function exShipConfirm() {
  if (shipSubmitting.value) return
  if (!exTracking.value.trim()) { toast('请填写物流单号', 'error'); return }
  shipSubmitting.value = true
  try {
    await req('POST', `/api/admin/trade/exchanges/${shipDlg.value.exchange_no}/ship`, {
      carrier: exCarrier.value, tracking_no: exTracking.value.trim(),
    })
    toast(`${shipDlg.value.exchange_no} 已重发 ✓`, 'success')
    shipDlg.value = null
    load()
  } catch (e) { toast('重发失败：' + (e.data?.detail || e.message), 'error') }
  shipSubmitting.value = false
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">退换货处理
        <span v-if="refreshing" style="font-size:12px;color:var(--gray);font-weight:400;margin-left:6px">⟳ 刷新中…</span>
      </h1>
      <span class="page-sub">RMA {{ rmaTotal }} · 换货 {{ exTotal }}<template v-if="state.q.trim()"> · 关键词“{{ state.q.trim() }}”</template></span>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <input v-model="state.q" class="input" style="width:220px" placeholder="退货单/订单号/邮箱" @keydown.enter="search">
      <button class="btn btn-secondary" @click="search">搜索</button>
      <button class="btn btn-secondary" :disabled="exporting" @click="exportCsv">{{ exporting ? '导出中…' : '⌄ 导出 CSV' }}</button>
    </div>
  </div>

  <div class="otab">
    <button
      v-for="[k, label] in [['rma', '退货 RMA'], ['exch', '换货']]"
      :key="k"
      :class="{ on: tab === k }"
      style="background:none;border:none;cursor:pointer"
      @click="state.tab = k"
    >{{ label }}</button>
  </div>

  <div v-if="tab === 'rma'" class="otab" style="flex-wrap:wrap">
    <button
      v-for="[k, label] in RTABS" :key="k"
      :class="{ on: state.rs === k }"
      style="background:none;border:none;cursor:pointer"
      @click="rmaTab(k)"
    >{{ label }}</button>
  </div>
  <div v-else class="otab" style="flex-wrap:wrap">
    <button
      v-for="[k, label] in ETABS" :key="k"
      :class="{ on: state.es === k }"
      style="background:none;border:none;cursor:pointer"
      @click="exTab(k)"
    >{{ label }}</button>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px" />

  <template v-else>
    <div class="card tbl-wrap">
      <table v-if="tab === 'rma'" style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">RMA</th><th>订单</th><th>客户</th><th>商品 / 原因</th><th>退款额</th><th>状态</th><th style="text-align:right">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in rmas" :key="r.rma_no" style="border-top:1px solid var(--gray-light)">
            <td style="padding:11px 10px">
              <b>{{ r.rma_no }}</b>
              <div style="color:var(--gray);font-size:11.5px">{{ dt(r.created_at) || '—' }} 申请</div>
            </td>
            <td><router-link class="ono" :to="{ path: '/order-detail', query: { no: r.order_no } }">{{ r.order_no }}</router-link></td>
            <td style="color:var(--gray)">{{ r.email }}</td>
            <td style="max-width:240px">
              <b>{{ r.item_title }}</b> ×{{ r.qty }}
              <div style="color:var(--gray);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="reasonLabel(r)">{{ reasonLabel(r) }}</div>
            </td>
            <td><b style="color:var(--plum)">{{ money(r.refund_amount) }}</b></td>
            <td><span class="tag" :class="RSTATUS[r.status]?.[1]">{{ RSTATUS[r.status]?.[0] || '—' }}</span></td>
            <td style="text-align:right;white-space:nowrap">
              <button v-if="r.status === 0" class="btn btn-primary btn-sm" @click="askRma(r, 'approve')">批准</button>
              <button v-if="[1, 2, 3].includes(r.status)" class="btn btn-secondary btn-sm" @click="askRma(r, 'receive')">收货</button>
              <button v-if="r.status === 4" class="btn btn-primary btn-sm" @click="askRma(r, 'refund')">退款</button>
            </td>
          </tr>
        </tbody>
      </table>

      <table v-else style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">换货单</th><th>订单</th><th>客户</th><th>商品</th><th>换为</th><th>差价</th><th>状态</th><th style="text-align:right">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="x in exch" :key="x.exchange_no" style="border-top:1px solid var(--gray-light)">
            <td style="padding:11px 10px">
              <b>{{ x.exchange_no }}</b>
              <div style="color:var(--gray);font-size:11.5px">{{ dt(x.created_at) || '—' }} 申请</div>
            </td>
            <td><router-link class="ono" :to="{ path: '/order-detail', query: { no: x.order_no } }">{{ x.order_no }}</router-link></td>
            <td style="color:var(--gray)">{{ x.email }}</td>
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="x.item?.title">{{ x.item?.title || '—' }}</td>
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="x.new_variant?.title">{{ x.new_variant?.title || '—' }}</td>
            <td>
              <b v-if="x.price_diff > 0" style="color:var(--error)">+{{ money(x.price_diff) }}</b>
              <b v-else-if="x.price_diff < 0" style="color:var(--success)">−{{ money(-x.price_diff) }}</b>
              <span v-else style="color:var(--gray)">—</span>
            </td>
            <td><span class="tag" :class="ESTATUS[x.status]?.[1]">{{ ESTATUS[x.status]?.[0] || '—' }}</span></td>
            <td style="text-align:right;white-space:nowrap">
              <template v-if="x.status === 0">
                <button class="btn btn-primary btn-sm" @click="askExch(x, 'approve')">批准</button>
                <button class="btn btn-ghost btn-sm" style="color:var(--error);margin-left:4px" @click="askExch(x, 'reject')">拒绝</button>
              </template>
              <button v-if="x.status === 2" class="btn btn-secondary btn-sm" @click="askExch(x, 'mark-paid')">已付差价</button>
              <button v-if="x.status === 1" class="btn btn-primary btn-sm" @click="exShip(x)">📦 重发</button>
              <button v-if="x.status === 3" class="btn btn-secondary btn-sm" @click="askExch(x, 'complete')">完成</button>
            </td>
          </tr>
        </tbody>
      </table>

      <EmptyState v-if="tab === 'rma' ? !rmas.length : !exch.length" icon="📭" :title="'暂无' + (tab === 'rma' ? '退货' : '换货') + '申请'" />
      <!-- 换货分页：卡内贴表下缘 -->
      <Pagination v-if="tab === 'exch'" embed :page="state.ep" :pages="exPages" :total="exTotal" unit="条" @go="state.ep = $event; loadExch()" />
    </div>

    <!-- 退货分页：卡片下方居中（与订单列表形态一致） -->
    <Pagination v-if="tab === 'rma'" :page="state.rp" :pages="rmaPages" :total="rmaTotal" unit="条" @go="state.rp = $event; loadRmas()" />
  </template>

  <!-- 换货重发弹窗 -->
  <div v-if="shipDlg" class="modal open" @click.self="shipDlg = null">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="shipDlg = null">×</button>
      <div class="dhead"><h3 class="dtitle">📦 重发 {{ shipDlg.exchange_no }}</h3></div>
      <p style="font-size:13px;color:var(--gray);margin-bottom:14px">
        发出新变体并扣库存：{{ shipDlg.new_variant?.title || (shipDlg.new_variant ? '#' + shipDlg.new_variant.id : '（变体已删除）') }}
      </p>
      <div class="field">
        <label>承运商</label>
        <select v-model="exCarrier" class="input">
          <option>USPS</option><option>UPS</option><option>FedEx</option><option>DHL</option>
        </select>
      </div>
      <div class="field">
        <label>物流单号</label>
        <input v-model="exTracking" class="input" placeholder="9400…">
      </div>
      <button class="btn btn-primary btn-block" style="margin-top:12px" :disabled="shipSubmitting" @click="exShipConfirm">{{ shipSubmitting ? '重发中…' : '确认重发' }}</button>
    </div>
  </div>

  <!-- 写操作统一确认弹窗 -->
  <ConfirmDialog
    :open="cfm.open"
    :title="cfm.title"
    :body="cfm.body"
    :danger="cfm.danger"
    :confirm-text="cfm.confirmText"
    :reason-label="cfm.reasonLabel"
    :reason-placeholder="cfm.reasonPlaceholder"
    :busy="submitting"
    @confirm="doConfirm"
    @close="cfm.open = false"
  />
</template>

<style scoped>
/* 订单号深链：plum 色 hover 下划线 */
.ono{color:var(--ink);text-decoration:none}
.ono:hover{color:var(--plum);text-decoration:underline}
</style>
