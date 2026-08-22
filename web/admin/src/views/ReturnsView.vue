<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { money, dt } from '../composables/format'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { RMA_STATUS, ESTATUS, RMA_REASON, RMA_ERR, EXCH_ERR, mapErr } from '../constants/trade'

const rmas = ref([])
const exch = ref([])
const loaded = ref(false)
/* 状态映射统一走 constants/trade.js：RMA_STATUS 退货 / ESTATUS 换货 / RMA_REASON 原因
 * 后台流转：approve 0→2（生成退货标签）· reject 0→6 · receive 1/2/3→4（收货回补库存）· refund 4→5 */
const reasonLabel = (r) => RMA_REASON[r.reason] || '—'

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
  ['s4', '已收货', [4]], ['s5', '已退款', [5]], ['s6', '已拒绝', [6]],
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
    /* 页码越界钳制：筛选/数据收缩后当前页超出 → 回第 1 页重拉一次 */
    if (state.rp > rmaPages.value && rmaPages.value >= 1) {
      loadCnt.value--
      state.rp = 1
      loadRmas()
      return
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
    /* 页码越界钳制：回第 1 页重拉一次 */
    if (state.ep > exPages.value && exPages.value >= 1) {
      loadCnt.value--
      state.ep = 1
      loadExch()
      return
    }
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
/* 空态文案：当前 tab 状态筛选或关键词生效→未匹配，否则暂无 */
const filtered = computed(() => state.q.trim() !== '' || (tab.value === 'rma' ? state.rs !== 'all' : state.es !== 'all'))

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
    /* 固化当前 tab/筛选快照：全部 await 完成后行内容与文件名仍按导出发起时的口径生成 */
    const curTab = tab.value
    const curRs = state.rs
    const curEs = state.es
    const rf = curTab === 'rma' ? (RTABS.find(([k]) => k === curRs)?.[2] ?? null) : null
    const ef = curTab === 'exch' ? (ETABS.find(([k]) => k === curEs)?.[2] ?? null) : null
    const kw = state.q.trim()
    let all = [], overflow = false
    if (curTab === 'rma') {
      if (rf && rf.length > 1) {
        /* 「待收货」组合筛选：两状态各拉前 100 合并（与列表口径一致，超 100 截断提示） */
        const qp = { per_page: 100 }
        if (kw) qp.q = kw
        const res = await Promise.all(rf.map((s) => req('GET', '/api/admin/trade/rmas?' + new URLSearchParams({ ...qp, status: s }))))
        all = res.flatMap((d) => d.items || []).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
        overflow = res.some((d) => (d.total ?? 0) > (d.items || []).length)
      } else {
        const params = { page: 1, per_page: 100 }
        if (rf) params.status = rf[0]
        if (kw) params.q = kw
        const r = await fetchAll('/api/admin/trade/rmas', params, 100)
        all = r.all; overflow = r.overflow
      }
    } else {
      const params = { page: 1, size: 50 }
      if (ef != null) params.status = ef
      if (kw) params.q = kw
      const r = await fetchAll('/api/admin/trade/exchanges', params, 50)
      all = r.all; overflow = r.overflow
    }
    if (overflow) toast('匹配结果过多，仅导出前 ' + all.length + ' 条', 'error')
    const rows = [['单号', '订单号', '邮箱', '状态', '金额', '原因', '创建时间'],
      ...all.map((r) => curTab === 'rma'
        ? [r.rma_no, r.order_no, r.email, RMA_STATUS[r.status]?.label, r.refund_amount != null ? money(r.refund_amount) : '—', reasonLabel(r), dt(r.created_at)]
        : [r.exchange_no, r.order_no, r.email, ESTATUS[r.status]?.label, r.price_diff ? money(r.price_diff) : '', '', dt(r.created_at)])]
    const csv = rows.map((r) => r.map(csvCell).join(',')).join('\n')
    const label = (curTab === 'rma' ? RTABS.find(([k]) => k === curRs)?.[1] : ETABS.find(([k]) => k === curEs)?.[1]) || '全部'
    const url = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${curTab === 'rma' ? 'rmas' : 'exchanges'}-${label}-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast('已导出 ' + all.length + ' 条 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  exporting.value = false
}

/* 统一确认弹窗（替代原生 confirm）：pending 记录待发请求；refund/reject 危险态，reject 需填拒绝原因 */
const cfm = reactive({ open: false, title: '', body: '', danger: false, reasonLabel: '', reasonPlaceholder: '', reasonRequired: false, confirmText: '确认', pending: null })
const submitting = ref(false)
function askRma(r, action) {
  let title = '', body = `退货单 ${r.rma_no}`, confirmText = '确认', danger = false
  let reasonLabel = '', reasonPlaceholder = ''
  if (action === 'approve') { title = '批准退货'; body += ' · 将为该申请生成退货标签'; confirmText = '批准' }
  else if (action === 'receive') { title = '确认收货'; body += ` · 将回补库存 ×${r.qty}` }
  else if (action === 'refund') {
    title = '执行退款'; danger = true; confirmText = '确认退款'
    /* refund_amount 按订单实付比例折算，审核前可能为 null（未折算） */
    body += ' · 退款按订单实付比例折算（含税/运费/折扣分摊）'
    if (r.refund_amount != null) body += ` · 本次退款 ${money(r.refund_amount)}`
    if (r.unit_price != null) body += ` · 参考值 ${money(r.unit_price * r.qty)}`
    body += ' · 将回补库存，操作不可撤销'
  } else if (action === 'reject') {
    title = '拒绝退货'; danger = true; confirmText = '确认拒绝'
    body += ' · 拒绝后该申请终止，不可恢复'
    reasonLabel = '拒绝原因'; reasonPlaceholder = '必填，如：超出售后期限 / 不符合退货政策'
  }
  cfm.title = title; cfm.body = body; cfm.danger = danger
  cfm.reasonLabel = reasonLabel; cfm.reasonPlaceholder = reasonPlaceholder
  cfm.reasonRequired = action === 'reject'
  cfm.confirmText = confirmText
  cfm.pending = { kind: 'rma', no: r.rma_no, action, label: title }
  cfm.open = true
}
function askExch(x, action) {
  let title = '', confirmText = '确认', body = `换货单 ${x.exchange_no}`
  if (action === 'approve') {
    title = '批准换货'; confirmText = '批准'
    /* 按差价提示流向：>0 买家补差 / <0 退买家差价 / =0 无差价 */
    const d = x.price_diff || 0
    body += d > 0 ? ` · 买家需补差价 ${money(d)}` : d < 0 ? ` · 将退买家差价 ${money(-d)}` : ' · 无差价'
  } else if (action === 'mark-paid') {
    title = '标记已付差价'; confirmText = '标记'
    if (x.price_diff > 0) body += ` · 应付差价 ${money(x.price_diff)}`
  }
  else if (action === 'complete') { title = '完成换货'; confirmText = '完成' }
  else if (action === 'reject') { title = '拒绝换货'; confirmText = '确认拒绝' }
  cfm.title = title; cfm.body = body; cfm.danger = false
  /* reject 走原因输入模式：confirm 回调把 reason 放进请求 body（ExchangeRejectRequest） */
  cfm.reasonLabel = action === 'reject' ? '拒绝原因' : ''
  cfm.reasonPlaceholder = action === 'reject' ? '如：库存不足 / 不符合换货政策' : ''
  cfm.reasonRequired = false
  cfm.confirmText = confirmText
  cfm.pending = { kind: 'exch', no: x.exchange_no, action, label: title }
  cfm.open = true
}
async function doConfirm(reason) {
  if (submitting.value || !cfm.pending) return
  /* RMA 拒绝原因必填 */
  if (cfm.reasonRequired && !reason) { toast('请填写' + cfm.reasonLabel, 'error'); return }
  submitting.value = true
  const { kind, no, action, label } = cfm.pending
  try {
    const url = `/api/admin/trade/${kind === 'rma' ? 'rmas' : 'exchanges'}/${no}/${action}`
    await req('POST', url, action === 'reject' ? { reason } : undefined)
    toast(`${label} ✓`, 'success')
    cfm.open = false
    load()
  } catch (e) { toast(`${label}失败：` + (mapErr(e.data?.detail, kind === 'rma' ? RMA_ERR : EXCH_ERR) || e.data?.detail || e.message), 'error') }
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
  } catch (e) { toast('重发失败：' + (mapErr(e.data?.detail, EXCH_ERR) || e.data?.detail || e.message), 'error') }
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

  <!-- 次级状态筛选：pill 形态（避免与主 tab 相邻双边框） -->
  <div v-if="tab === 'rma'" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
    <button
      v-for="[k, label] in RTABS" :key="k"
      class="mtab" :class="{ on: state.rs === k }"
      @click="rmaTab(k)"
    >{{ label }}</button>
  </div>
  <div v-else style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
    <button
      v-for="[k, label] in ETABS" :key="k"
      class="mtab" :class="{ on: state.es === k }"
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
            <td>
              <b v-if="r.refund_amount != null" style="color:var(--plum)">{{ money(r.refund_amount) }}</b>
              <span v-else style="color:var(--gray)" title="退款额按订单实付比例折算，审核后生成">—</span>
            </td>
            <td><span class="tag" :class="RMA_STATUS[r.status]?.cls">{{ RMA_STATUS[r.status]?.label || '—' }}</span></td>
            <td style="text-align:right;white-space:nowrap">
              <button v-if="r.status === 0" class="btn btn-primary btn-sm" @click="askRma(r, 'approve')">批准</button>
              <button v-if="r.status === 0" class="btn btn-danger btn-sm" style="margin-left:4px" @click="askRma(r, 'reject')">拒绝</button>
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
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="x.item?.title">{{ x.item?.title || '—' }}<span v-if="x.qty"> ×{{ x.qty }}</span></td>
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="x.new_variant?.title">{{ x.new_variant?.title || '—' }}</td>
            <td>
              <b v-if="x.price_diff > 0" style="color:var(--error)">+{{ money(x.price_diff) }}</b>
              <b v-else-if="x.price_diff < 0" style="color:var(--success)">−{{ money(-x.price_diff) }}</b>
              <span v-else style="color:var(--gray)">—</span>
            </td>
            <td><span class="tag" :class="ESTATUS[x.status]?.cls">{{ ESTATUS[x.status]?.label || '—' }}</span></td>
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

      <EmptyState
        v-if="tab === 'rma' ? !rmas.length : !exch.length"
        :icon="filtered ? '🔍' : '📭'"
        :title="filtered ? '未找到匹配的' + (tab === 'rma' ? '退货' : '换货') : '暂无' + (tab === 'rma' ? '退货' : '换货') + '申请'"
        :sub="filtered ? '试试调整或清除筛选' : '客户提交后将显示在这里'"
      />
      <!-- 分页统一：两 tab 均卡内底部居中（带分割线） -->
      <div v-if="tab === 'rma' && rmaPages > 1" class="pg-slot">
        <Pagination :page="state.rp" :pages="rmaPages" :total="rmaTotal" unit="条" @go="state.rp = $event; loadRmas()" />
      </div>
      <div v-else-if="tab === 'exch' && exPages > 1" class="pg-slot">
        <Pagination :page="state.ep" :pages="exPages" :total="exTotal" unit="条" @go="state.ep = $event; loadExch()" />
      </div>
    </div>
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
/* 分页槽：卡内贴底居中（带上分割线） */
.pg-slot{display:flex;justify-content:center;padding:12px 10px;border-top:1px solid var(--gray-light)}
.pg-slot :deep(.pg){margin-top:0}
</style>
