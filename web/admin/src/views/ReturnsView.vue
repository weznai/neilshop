<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import EmptyState from '../components/EmptyState.vue'

const route = useRoute()
const rmas = ref([])
const exch = ref([])
const tab = ref('rma')
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

/* RMA 状态筛选 + 服务端分页（page/per_page=20，响应含 total/pages）
 * 后端 status 仅支持单值（router_admin list_rmas 为 Optional[int]，已核对不支持逗号）：
 * 「待收货」= 标签已发(2)+在途(3) 拆两次请求各拉前 100 合并，前端分页；>100 截断时 toast 提示 */
const rmaFilter = ref(null) /* null=全部，否则为状态数组 */
const RMA_PER_PAGE = 20
const rmaPage = ref(1)
const rmaPages = ref(1)
const rmaTotal = ref(0)
const RTABS = [
  ['all', '全部', null], ['s0', '待审核', [0]], ['s23', '待收货', [2, 3]],
  ['s4', '已收货', [4]], ['s5', '已退款', [5]], ['s6', '已拒绝', [6]], ['s7', '部分退款', [7]],
]
async function loadRmas() {
  const f = rmaFilter.value
  try {
    if (!f || f.length === 1) {
      const params = { page: rmaPage.value, per_page: RMA_PER_PAGE }
      if (f) params.status = f[0]
      const d = await req('GET', '/api/admin/trade/rmas?' + new URLSearchParams(params))
      rmas.value = d.items || []
      rmaTotal.value = d.total ?? 0
      rmaPages.value = d.pages ?? 1
    } else {
      const res = await Promise.all(
        f.map((s) => req('GET', '/api/admin/trade/rmas?status=' + s + '&per_page=100')),
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
      rmas.value = all.slice((rmaPage.value - 1) * RMA_PER_PAGE, rmaPage.value * RMA_PER_PAGE)
    }
  } catch (e) { rmas.value = []; rmaTotal.value = 0; rmaPages.value = 1; toast('退货列表加载失败：' + (e.message || ''), 'error') }
}
function rmaTab(sv) { rmaFilter.value = sv; rmaPage.value = 1; loadRmas() }

/* 换货状态筛选 + 分页（后端支持 status/page/size，size=50） */
const exFilter = ref(null)
const exPage = ref(1)
const exPages = ref(1)
const exTotal = ref(0)
const ETABS = [
  ['all', '全部', null], ['s0', '待审核', 0], ['s2', '待付差价', 2], ['s1', '待重发', 1],
  ['s3', '已重发', 3], ['s4', '已完成', 4], ['s5', '已拒绝', 5],
]
async function loadExch() {
  const params = { page: exPage.value, size: 50 }
  if (exFilter.value != null) params.status = exFilter.value
  try {
    const d = await req('GET', '/api/admin/trade/exchanges?' + new URLSearchParams(params))
    exch.value = d.items || []
    exTotal.value = d.total ?? 0
    exPages.value = d.pages ?? 1
  } catch (e) {
    exch.value = []; exTotal.value = 0; exPages.value = 1
    toast('换货列表加载失败：' + (e.message || ''), 'error')
  }
}
function exTab(sv) { exFilter.value = sv; exPage.value = 1; loadExch() }

async function load() { await Promise.all([loadRmas(), loadExch()]) }
/* 深链支持：/returns?tab=rma|exch（dashboard 待审退货入口用） */
onMounted(async () => {
  if (route.query.tab === 'rma' || route.query.tab === 'exch') tab.value = route.query.tab
  await load()
  loaded.value = true
})

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const time = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  const p = (x) => String(x).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function rmaAct(r, action, label) {
  if (!confirm(`${label} ${r.rma_no}？`)) return
  try {
    await req('POST', `/api/admin/trade/rmas/${r.rma_no}/${action}`)
    toast(`${label} ✓`, 'success')
    load()
  } catch (e) { toast(`${label}失败：` + (e.data?.detail || e.message), 'error') }
}
async function exchAct(x, action, label, body) {
  if (!confirm(`${label} ${x.exchange_no}？`)) return
  try {
    await req('POST', `/api/admin/trade/exchanges/${x.exchange_no}/${action}`, body)
    toast(`${label} ✓`, 'success')
    load()
  } catch (e) { toast(`${label}失败：` + (e.data?.detail || e.message), 'error') }
}

/* 换货重发弹窗：ShipRequest 需 carrier + tracking_no */
const shipDlg = ref(null)
const exCarrier = ref('USPS')
const exTracking = ref('')
function exShip(x) { shipDlg.value = x; exTracking.value = ''; exCarrier.value = 'USPS' }
async function exShipConfirm() {
  if (!exTracking.value.trim()) { toast('请填写物流单号', 'error'); return }
  try {
    await req('POST', `/api/admin/trade/exchanges/${shipDlg.value.exchange_no}/ship`, {
      carrier: exCarrier.value, tracking_no: exTracking.value.trim(),
    })
    toast(`${shipDlg.value.exchange_no} 已重发 ✓`, 'success')
    shipDlg.value = null
    load()
  } catch (e) { toast('重发失败：' + (e.data?.detail || e.message), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">退换货处理</h1>
      <span style="font-size:12.5px;color:var(--gray)">RMA {{ rmaTotal }} · 换货 {{ exTotal }}</span>
    </div>
  </div>

  <div class="otab">
    <button
      v-for="[k, label] in [['rma', '退货 RMA'], ['exch', '换货']]"
      :key="k"
      :class="{ on: tab === k }"
      style="background:none;border:none;cursor:pointer"
      @click="tab = k"
    >{{ label }}</button>
  </div>

  <div v-if="tab === 'rma'" class="otab" style="flex-wrap:wrap">
    <button
      v-for="[k, label, sv] in RTABS" :key="k"
      :class="{ on: (rmaFilter || null) === sv }"
      style="background:none;border:none;cursor:pointer"
      @click="rmaTab(sv)"
    >{{ label }}</button>
  </div>
  <div v-else class="otab" style="flex-wrap:wrap">
    <button
      v-for="[k, label, sv] in ETABS" :key="k"
      :class="{ on: exFilter === sv }"
      style="background:none;border:none;cursor:pointer"
      @click="exTab(sv)"
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
              <div style="color:var(--gray);font-size:11.5px">{{ time(r.created_at) }} 申请</div>
            </td>
            <td>{{ r.order_no }}</td>
            <td style="color:var(--gray)">{{ r.email }}</td>
            <td style="max-width:240px">
              <b>{{ r.item_title }}</b> ×{{ r.qty }}
              <div style="color:var(--gray);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="reasonLabel(r)">{{ reasonLabel(r) }}</div>
            </td>
            <td><b style="color:var(--plum)">{{ money(r.refund_amount) }}</b></td>
            <td><span class="tag" :class="RSTATUS[r.status]?.[1]">{{ RSTATUS[r.status]?.[0] || '—' }}</span></td>
            <td style="text-align:right;white-space:nowrap">
              <button v-if="r.status === 0" class="btn btn-primary btn-sm" @click="rmaAct(r, 'approve', '批准退货（将向客户发送退货标签邮件）')">批准</button>
              <button v-if="[1, 2, 3].includes(r.status)" class="btn btn-secondary btn-sm" @click="rmaAct(r, 'receive', `确认收货（将回补库存 ×${r.qty}）`)">收货</button>
              <button v-if="r.status === 4" class="btn btn-primary btn-sm" @click="rmaAct(r, 'refund', '执行退款（金额按订单实付比例折算）')">退款</button>
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
              <div style="color:var(--gray);font-size:11.5px">{{ time(x.created_at) }} 申请</div>
            </td>
            <td>{{ x.order_no }}</td>
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
                <button class="btn btn-primary btn-sm" @click="exchAct(x, 'approve', '批准换货')">批准</button>
                <button class="btn btn-ghost btn-sm" style="color:var(--error);margin-left:4px" @click="exchAct(x, 'reject', '拒绝')">拒绝</button>
              </template>
              <button v-if="x.status === 2" class="btn btn-secondary btn-sm" @click="exchAct(x, 'mark-paid', '标记已付差价')">已付差价</button>
              <button v-if="x.status === 1" class="btn btn-primary btn-sm" @click="exShip(x)">📦 重发</button>
              <button v-if="x.status === 3" class="btn btn-secondary btn-sm" @click="exchAct(x, 'complete', '完成')">完成</button>
            </td>
          </tr>
        </tbody>
      </table>

      <EmptyState v-if="tab === 'rma' ? !rmas.length : !exch.length" icon="📭" :title="'暂无' + (tab === 'rma' ? '退货' : '换货') + '申请'" />
    </div>

    <div v-if="tab === 'rma' && rmaPages > 1" style="display:flex;justify-content:center;gap:8px;margin-top:16px;align-items:center">
      <button class="btn btn-secondary btn-sm" :disabled="rmaPage <= 1" @click="rmaPage--; loadRmas()">←</button>
      <span style="font-size:13px;color:var(--gray)">第 {{ rmaPage }} / {{ rmaPages }} 页 · 共 {{ rmaTotal }} 条</span>
      <button class="btn btn-secondary btn-sm" :disabled="rmaPage >= rmaPages" @click="rmaPage++; loadRmas()">→</button>
    </div>

    <div v-if="tab === 'exch' && exPages > 1" style="display:flex;justify-content:center;gap:8px;margin-top:16px;align-items:center">
      <button class="btn btn-secondary btn-sm" :disabled="exPage <= 1" @click="exPage--; loadExch()">←</button>
      <span style="font-size:13px;color:var(--gray)">第 {{ exPage }} / {{ exPages }} 页 · 共 {{ exTotal }} 条</span>
      <button class="btn btn-secondary btn-sm" :disabled="exPage >= exPages" @click="exPage++; loadExch()">→</button>
    </div>
  </template>

  <!-- 换货重发弹窗 -->
  <div v-if="shipDlg" class="modal open" @click.self="shipDlg = null">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="shipDlg = null">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">📦 重发 {{ shipDlg.exchange_no }}</h3>
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
      <button class="btn btn-primary btn-block" style="margin-top:12px" @click="exShipConfirm">确认重发</button>
    </div>
  </div>
</template>
