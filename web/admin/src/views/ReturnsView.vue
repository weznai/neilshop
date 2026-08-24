<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'
import { money, dt } from '../composables/format'
import { csvCell, downloadCsv } from '../composables/exportCsv'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { RMA_STATUS, ESTATUS, RMA_REASON, RMA_ERR, EXCH_ERR, mapErr } from '../constants/trade'

const session = useSessionStore()
const rmas = ref([])
const exch = ref([])
const loaded = ref(false)
/* 列表加载失败态：保留旧数据不清空，空列表时渲染「加载失败+重试」空态（做法同 OrdersView） */
const rmaErr = ref('')
const exErr = ref('')
/* 批准响应携带的退货标签链接（列表接口不回传 label_url）：本地暂存供行内展示，刷新页面后失效 */
const rmaLabels = ref({})
/* 状态映射统一走 constants/trade.js：RMA_STATUS 退货 / ESTATUS 换货 / RMA_REASON 原因
 * 后台流转：approve 0→2（生成退货标签）· reject 0→6 · receive 1/2/3→4（收货回补库存）
 * · refund 4→5（按折算额全退）/ 4→7（自定义金额部分退款） */
const reasonLabel = (r) => RMA_REASON[r.reason] || '—'

/* URL 同步：tab 主档位 + rs/es 两列表状态筛选（存 tab key 字符串）+ rp/ep 两分页
 * q 拆出同步态为本地 ref：输入不逐字符 router.replace，仅搜索触发/回车时写回 URL */
const state = reactive({ tab: 'rma', rs: 'all', es: 'all', rp: 1, ep: 1 })
useQuerySync(state, { nums: ['rp', 'ep'], defaults: { tab: 'rma', rs: 'all', es: 'all', rp: 1, ep: 1 }, onPop: () => load() })
const tab = computed(() => (state.tab === 'exch' ? 'exch' : 'rma'))
const route = useRoute()
const router = useRouter()
const q = ref(typeof route.query.q === 'string' ? route.query.q : '')

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
  ['s4', '已收货', [4]], ['s7', '部分退款', [7]], ['s5', '已退款', [5]], ['s6', '已拒绝', [6]],
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
      if (q.value.trim()) params.q = q.value.trim()
      const d = await req('GET', '/api/admin/trade/rmas?' + new URLSearchParams(params))
      rmas.value = d.items || []
      rmaTotal.value = d.total ?? 0
      rmaPages.value = d.pages ?? 1
    } else {
      const qp = { per_page: 100 }
      if (q.value.trim()) qp.q = q.value.trim()
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
    rmaErr.value = ''
    /* 页码越界钳制：筛选/数据收缩后当前页超出 → 回第 1 页重拉一次 */
    if (state.rp > rmaPages.value && rmaPages.value >= 1) {
      loadCnt.value--
      state.rp = 1
      loadRmas()
      return
    }
  } catch (e) { rmaErr.value = e.message || '加载失败'; toast('退货列表加载失败：' + (e.message || ''), 'error') }
  loadCnt.value--
}
function rmaTab(k) { state.rs = k; state.rp = 1; loadRmas() }

/* 换货状态筛选 + 分页（后端支持 status/page/size，与 RMA 统一每页 20） */
const exPages = ref(1)
const exTotal = ref(0)
const ETABS = [
  ['all', '全部', null], ['s0', '待审核', 0], ['s2', '待付差价', 2], ['s1', '待重发', 1],
  ['s3', '已重发', 3], ['s4', '已完成', 4], ['s5', '已拒绝', 5],
]
const exFilter = computed(() => ETABS.find(([k]) => k === state.es)?.[2] ?? null)
async function loadExch() {
  loadCnt.value++
  const params = { page: state.ep, size: 20 }
  if (exFilter.value != null) params.status = exFilter.value
  if (q.value.trim()) params.q = q.value.trim()
  try {
    const d = await req('GET', '/api/admin/trade/exchanges?' + new URLSearchParams(params))
    exch.value = d.items || []
    exTotal.value = d.total ?? 0
    exPages.value = d.pages ?? 1
    exErr.value = ''
    /* 页码越界钳制：回第 1 页重拉一次 */
    if (state.ep > exPages.value && exPages.value >= 1) {
      loadCnt.value--
      state.ep = 1
      loadExch()
      return
    }
  } catch (e) {
    exErr.value = e.message || '加载失败'
    toast('换货列表加载失败：' + (e.message || ''), 'error')
  }
  loadCnt.value--
}
function exTab(k) { state.es = k; state.ep = 1; loadExch() }

async function load() { await Promise.all([loadRmas(), loadExch()]) }
onMounted(async () => { await load(); loaded.value = true })

/* 手动刷新 ⟳ / tab 切换：轻量重载当前 tab 目标列表（保留旧数据不清空） */
function refresh() { tab.value === 'rma' ? loadRmas() : loadExch() }
watch(tab, () => refresh())

/* 顶栏搜索：q 两 tab 共用（分别传给各自请求），回车/按钮触发并重置两列表页码；此时才写回 URL 同步态。
 * 一次性 replace 写入 q 并同批清掉 rp/ep 页码键：若先突变 state 页码，useQuerySync 的 deep watcher 会在
 * 本次导航落地前再发一次 replace（基于旧 query、不含新 q），把刚写入 URL 的 q 覆盖丢失（第 2+ 页搜索时必现） */
async function search() {
  const kw = q.value.trim()
  q.value = kw   /* 归一化输入与 URL/请求一致，同时防下方 q-watcher 重复触发 load */
  const hadPageKeys = route.query.rp !== undefined || route.query.ep !== undefined
  if ((route.query.q || '') !== kw || hadPageKeys) {
    await router.replace({ query: { ...route.query, q: kw || undefined, rp: undefined, ep: undefined } })
  }
  /* 页码键被清除时 useQuerySync 的 onPop 已触发重载（下方手动回落为 no-op），否则手动重载 */
  state.rp = 1
  state.ep = 1
  if (!hadPageKeys) load()
}
/* 浏览器回退/前进：q 变化只同步回本地 ref 并重载（不触发导航）。页码键由 useQuerySync 的
 * query-watcher 先行回落默认（其 watch 创建早于本处，同批 flush 先执行），故此处统一只发一次 load */
watch(() => route.query.q, (v) => {
  if (route.name !== 'returns') return   /* 已离开本页（卸载前最后一次 route 变更）：忽略 */
  const s = typeof v === 'string' ? v : ''
  if (s !== q.value) {
    q.value = s
    load()
  }
})
/* 空态文案：当前 tab 状态筛选或关键词生效→未匹配，否则暂无 */
const filtered = computed(() => q.value.trim() !== '' || (tab.value === 'rma' ? state.rs !== 'all' : state.es !== 'all'))

/* CSV 导出：仅导出当前 tab 当前筛选（状态+关键词）下全部页 */
const exporting = ref(false)
const EXPORT_MAX_PAGES = 20
/* 循环翻页拉全量：按首页 total 重算页数；size 为该接口单页条数（rma per_page=100 / exch size=100，后端上限 100） */
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
    const kw = q.value.trim()
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
      const params = { page: 1, size: 100 }
      if (ef != null) params.status = ef
      if (kw) params.q = kw
      const r = await fetchAll('/api/admin/trade/exchanges', params, 100)
      all = r.all; overflow = r.overflow
    }
    if (overflow) toast('匹配结果过多，仅导出前 ' + all.length + ' 条', 'error')
    const label = (curTab === 'rma' ? RTABS.find(([k]) => k === curRs)?.[1] : ETABS.find(([k]) => k === curEs)?.[1]) || '全部'
    downloadCsv({
      filename: `${curTab === 'rma' ? 'rmas' : 'exchanges'}-${label}-${new Date().toISOString().slice(0, 10)}`,
      headers: ['单号', '订单号', '邮箱', '状态', '金额', '原因', '创建时间'],
      rows: all.map((r) => curTab === 'rma'
        ? [r.rma_no, r.order_no, r.email, RMA_STATUS[r.status]?.label, r.refund_amount != null ? money(r.refund_amount) : '—', reasonLabel(r), dt(r.created_at)]
        : [r.exchange_no, r.order_no, r.email, ESTATUS[r.status]?.label, r.price_diff ? money(r.price_diff) : '', '', dt(r.created_at)]),
    })
    toast('已导出 ' + all.length + ' 条 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  exporting.value = false
}

/* 统一确认弹窗（替代原生 confirm）：pending 记录待发请求；reject 危险态且必填原因（reasonTextarea=多行） */
const cfm = reactive({ open: false, title: '', body: '', danger: false, reasonLabel: '', reasonPlaceholder: '', reasonTextarea: false, reasonRequired: false, confirmText: '确认', pending: null })
const submitting = ref(false)
function askRma(r, action) {
  let title = '', body = `退货单 ${r.rma_no}`, confirmText = '确认', danger = false
  let reasonLabel = '', reasonPlaceholder = ''
  if (action === 'approve') { title = '批准退货'; body += ' · 将为该申请生成退货标签'; confirmText = '批准' }
  else if (action === 'receive') { title = '确认收货'; body += ` · 将回补库存 ×${r.qty}` }
  else if (action === 'reject') {
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
  let title = '', confirmText = '确认', danger = false, body = `换货单 ${x.exchange_no}`
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
  else if (action === 'reject') { title = '拒绝换货'; danger = true; confirmText = '确认拒绝'; body += ' · 拒绝后该换货终止，不可恢复' }
  cfm.title = title; cfm.body = body; cfm.danger = danger
  /* reject 走原因输入模式（必填，textarea 多行）：confirm 回调把 reason 放进请求 body（ExchangeRejectRequest） */
  cfm.reasonLabel = action === 'reject' ? '拒绝原因' : ''
  cfm.reasonPlaceholder = action === 'reject' ? '必填，如：库存不足 / 不符合换货政策' : ''
  cfm.reasonTextarea = action === 'reject'
  cfm.reasonRequired = action === 'reject'
  cfm.confirmText = confirmText
  cfm.pending = { kind: 'exch', no: x.exchange_no, action, label: title }
  cfm.open = true
}
async function doConfirm(reason) {
  if (submitting.value || !cfm.pending) return
  /* 拒绝原因必填（RMA/换货同口径） */
  if (cfm.reasonRequired && !reason) { toast('请填写' + cfm.reasonLabel, 'error'); return }
  submitting.value = true
  const { kind, no, action, label } = cfm.pending
  try {
    const url = `/api/admin/trade/${kind === 'rma' ? 'rmas' : 'exchanges'}/${no}/${action}`
    const d = await req('POST', url, action === 'reject' ? { reason } : undefined)
    /* RMA 批准响应携带退货标签链接（列表接口不回传）：暂存本地供行内链接 + toast 提示 */
    if (kind === 'rma' && action === 'approve' && d?.label_url) {
      rmaLabels.value[no] = d.label_url
      toast(`${label} ✓ 退货标签已生成`, 'success')
    } else {
      toast(`${label} ✓`, 'success')
    }
    cfm.open = false
    load()
  } catch (e) { toast(`${label}失败：` + (mapErr(e.data?.detail, kind === 'rma' ? RMA_ERR : EXCH_ERR) || e.data?.detail || e.message), 'error') }
  submitting.value = false
}

/* RMA 退款弹窗（独立于统一确认弹窗：需可选金额输入）：refund_amount 为后端折算额；
 * 金额留空=按折算额全退（status→5，不携带 amount_cents）；填值换算为分提交 → 部分退款（status→7） */
const refundDlg = ref(null)
const refundAmt = ref('')
const refunding = ref(false)
function askRefund(r) { refundDlg.value = r; refundAmt.value = '' }
async function doRefund() {
  const r = refundDlg.value
  if (!r || refunding.value) return
  let body
  const s = String(refundAmt.value).trim()
  if (s !== '') {
    const v = Number(s)
    /* 拦截 $0.00x：四舍五入到分后不足 1 分直接前端提示（与提交换算口径一致） */
    if (!(v > 0) || Math.round(v * 100) < 1) { toast('退款金额至少 0.01', 'error'); return }
    /* 折算额未知（理论上退款态必已折算）时禁用手填，防盲提交 */
    if (r.refund_amount == null || Math.round(v * 100) > r.refund_amount) { toast('超出可退额度', 'error'); return }
    body = { amount_cents: Math.round(v * 100) }
  }
  refunding.value = true
  try {
    const d = await req('POST', `/api/admin/trade/rmas/${r.rma_no}/refund`, body)
    toast(d?.partial ? `部分退款 ${money(d.refund_amount)} ✓（折算额 ${money(r.refund_amount)}）` : '退款完成 ✓', 'success')
    refundDlg.value = null
    load()
  } catch (e) {
    /* 409 invalid refund amount 优先 mapErr(RMA_ERR)；键未就绪时精确串兜底翻译 */
    toast('退款失败：' + (mapErr(e.data?.detail, RMA_ERR)
      || (e.data?.detail === 'invalid refund amount' ? '退款金额超出可退额度' : '')
      || e.data?.detail || e.message), 'error')
  }
  refunding.value = false
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
      <span class="page-sub">RMA {{ rmaTotal }} · 换货 {{ exTotal }}<template v-if="q.trim()"> · 关键词“{{ q.trim() }}”</template></span>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <button class="btn btn-secondary" :disabled="refreshing" @click="refresh">⟳ 刷新</button>
      <input v-model="q" class="input js-search" style="width:220px" placeholder="退货单/订单号/邮箱" @keydown.enter="search">
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
              <!-- 退货标签链接：仅批准时暂存于本地（列表接口不回传 label_url），刷新页面后消失 -->
              <a v-if="rmaLabels[r.rma_no]" class="btn btn-secondary btn-sm" style="display:inline-block;margin-top:5px" :href="rmaLabels[r.rma_no]" target="_blank" rel="noopener">🖨 退货标签</a>
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
              <button v-if="r.status === 0 && session.hasPerm('rma:manage')" class="btn btn-primary btn-sm" @click="askRma(r, 'approve')">批准</button>
              <button v-if="r.status === 0 && session.hasPerm('rma:manage')" class="btn btn-ghost btn-sm" style="color:var(--error);margin-left:4px" @click="askRma(r, 'reject')">拒绝</button>
              <button v-if="[1, 2, 3].includes(r.status) && session.hasPerm('rma:receive')" class="btn btn-secondary btn-sm" @click="askRma(r, 'receive')">收货</button>
              <button v-if="r.status === 4 && session.hasPerm('trade:refund')" class="btn btn-danger btn-sm" @click="askRefund(r)">退款</button>
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
              <!-- 关联单据提示：列表行仅回传 shipment_id（无差价支付字段），有则显示重发单小标签 -->
              <div v-if="x.shipment_id" style="margin-top:5px"><span class="tag tag-ship" style="font-size:11px;padding:1px 7px">重发单已建</span></div>
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
              <template v-if="x.status === 0 && session.hasPerm('rma:manage')">
                <button class="btn btn-primary btn-sm" @click="askExch(x, 'approve')">批准</button>
                <button class="btn btn-ghost btn-sm" style="color:var(--error);margin-left:4px" @click="askExch(x, 'reject')">拒绝</button>
              </template>
              <button v-if="x.status === 2 && session.hasPerm('trade:refund')" class="btn btn-secondary btn-sm" @click="askExch(x, 'mark-paid')">已付差价</button>
              <button v-if="x.status === 1 && session.hasPerm('trade:ship')" class="btn btn-primary btn-sm" @click="exShip(x)">📦 重发</button>
              <button v-if="x.status === 3 && session.hasPerm('rma:manage')" class="btn btn-secondary btn-sm" @click="askExch(x, 'complete')">完成</button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 加载失败空态：列表为空且本次加载失败 → 保留失败态 + 重试（有旧数据仍走 toast 提示） -->
      <EmptyState
        v-if="tab === 'rma' ? !rmas.length && rmaErr : !exch.length && exErr"
        icon="⚠️" title="加载失败" :sub="tab === 'rma' ? rmaErr : exErr"
      >
        <template #action><button class="btn btn-secondary btn-sm" @click="refresh">重试</button></template>
      </EmptyState>
      <EmptyState
        v-else-if="tab === 'rma' ? !rmas.length : !exch.length"
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
  <div v-if="shipDlg" class="modal open" @click.self="!shipSubmitting && (shipDlg = null)">
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

  <!-- RMA 退款弹窗（金额可调：留空=按折算额全退，填值=部分退款） -->
  <div v-if="refundDlg" class="modal open" @click.self="!refunding && (refundDlg = null)">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" :disabled="refunding" @click="!refunding && (refundDlg = null)">×</button>
      <div class="dhead"><h3 class="dtitle">💸 执行退款 {{ refundDlg.rma_no }}</h3></div>
      <p style="font-size:13px;color:var(--gray);margin-bottom:14px">
        退款按订单实付比例折算（含税/运费/折扣分摊）· 本次退款
        <b v-if="refundDlg.refund_amount != null" style="color:var(--plum)">{{ money(refundDlg.refund_amount) }}</b>
        <template v-if="refundDlg.unit_price != null"> · 参考值 {{ money(refundDlg.unit_price * refundDlg.qty) }}</template>
        · 将回补库存，操作不可撤销
      </p>
      <div class="field">
        <label>退款金额（美元，可选）</label>
        <input v-model="refundAmt" class="input" type="number" min="0" step="0.01" :placeholder="refundDlg.refund_amount != null ? '留空 = 按折算额 ' + money(refundDlg.refund_amount) + ' 全额退款' : '留空 = 按折算额全额退款'">
        <p style="font-size:11.5px;color:var(--gray);margin-top:6px">填写小于折算额的金额将执行部分退款；超出折算额将被拒绝。</p>
      </div>
      <button class="btn btn-danger btn-block" style="margin-top:12px" :disabled="refunding" @click="doRefund">{{ refunding ? '退款中…' : '确认退款' }}</button>
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
    :reason-textarea="cfm.reasonTextarea"
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
