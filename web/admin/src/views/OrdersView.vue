<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'

const items = ref([])
const total = ref(0)
const pages = ref(1)
const page = ref(1)
const perPage = ref(20)
const status = ref(null)
const q = ref('')
const loaded = ref(false)
const refreshing = ref(false)
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

async function load() {
  /* 筛选/翻页保留旧数据不清空，骨架只在首次出现 */
  refreshing.value = true
  /* 后端支持可选 per_page（钳制 10-100），分页以响应 pages/total 为准 */
  const params = { page: page.value, per_page: perPage.value }
  if (status.value != null) params.status = status.value
  if (q.value.trim()) params.q = q.value.trim()
  try {
    const d = await req('GET', '/api/admin/trade/orders?' + new URLSearchParams(params))
    items.value = d.items || []
    total.value = d.total ?? 0
    pages.value = d.pages ?? 1
  } catch (e) { toast('加载失败：' + (e.message || ''), 'error') }
  loaded.value = true
  refreshing.value = false
}
onMounted(load)

function tab(sv) { status.value = sv; page.value = 1; load() }
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const time = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso)
  const p = (x) => String(x).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const shipDlg = ref(null) /* {order_no} */
const carrier = ref('USPS')
const tracking = ref('')
async function ship(o) { shipDlg.value = o; tracking.value = ''; carrier.value = 'USPS' }
async function shipConfirm() {
  const o = shipDlg.value
  if (!tracking.value.trim()) { toast('请填写物流单号', 'error'); return }
  try {
    await req('POST', `/api/admin/trade/orders/${o.order_no}/ship`, { carrier: carrier.value, tracking_no: tracking.value.trim() })
    toast(`${o.order_no} 已发货 ✓`, 'success')
    shipDlg.value = null
    load()
  } catch (e) { toast('发货失败：' + (e.data?.detail || e.message), 'error') }
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
    const first = await req('GET', '/api/admin/trade/orders?' + new URLSearchParams(params))
    const all = [...(first.items || [])]
    const totalMatch = first.total ?? all.length
    const maxPage = Math.min(Math.ceil(totalMatch / EXPORT_PER_PAGE) || 1, EXPORT_MAX_PAGES)
    for (let p = 2; p <= maxPage; p++) {
      params.page = p
      const d = await req('GET', '/api/admin/trade/orders?' + new URLSearchParams(params))
      all.push(...(d.items || []))
    }
    if (Math.ceil(totalMatch / EXPORT_PER_PAGE) > EXPORT_MAX_PAGES) {
      toast(`匹配结果超过 ${EXPORT_MAX_PAGES * EXPORT_PER_PAGE} 单，仅导出前 ${all.length} 单`, 'error')
    }
    /* CSV 转义：含逗号/引号/换行的字段包引号并双写引号 */
    const cell = (v) => {
      const s = String(v ?? '')
      return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
    }
    const rows = [['订单号', '邮箱', '金额', '状态', '履约', '下单时间', '支付时间'],
      ...all.map((o) => [o.order_no, o.email, money(o.grand_total), OSTATUS[o.status]?.[0], SHSTATUS[o.shipping_status]?.[0], o.placed_at, o.paid_at || ''])]
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
      <h1 style="font-size:22px">订单管理
        <span v-if="refreshing" style="font-size:12px;color:var(--gray);font-weight:400;margin-left:6px">⟳ 刷新中…</span>
      </h1>
      <span style="font-size:12.5px;color:var(--gray)">共 {{ total }} 单<template v-if="statusLabel"> · 筛选：{{ statusLabel }}</template><template v-if="q.trim()"> · 关键词“{{ q.trim() }}”</template></span>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <select v-model.number="perPage" class="input" style="width:auto;height:36px;font-size:13px" @change="page = 1; load()">
        <option :value="20">20 条/页</option>
        <option :value="50">50 条/页</option>
        <option :value="100">100 条/页</option>
      </select>
      <input v-model="q" class="input" style="width:220px" placeholder="搜订单号 / 邮箱" @keydown.enter="page = 1; load()">
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

  <div v-if="!loaded" class="card skeleton" style="min-height:280px" />

  <div v-else class="card tbl-wrap">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">订单号</th><th>客户</th><th>金额</th><th>状态</th><th>履约</th><th>下单时间</th><th>支付时间</th><th style="text-align:right">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="o in items" :key="o.order_no" style="border-top:1px solid var(--gray-light)">
          <td style="padding:11px 10px"><b>{{ o.order_no }}</b></td>
          <td>{{ esc(o.email) }}</td>
          <td><b style="color:var(--plum)">{{ money(o.grand_total) }}</b></td>
          <td><span class="tag" :class="OSTATUS[o.status]?.[1]">{{ OSTATUS[o.status]?.[0] }}</span></td>
          <td><span class="tag" :class="SHSTATUS[o.shipping_status]?.[1] || 'tag-pending'" :title="'shipping_status: ' + o.shipping_status">{{ SHSTATUS[o.shipping_status]?.[0] || '—' }}</span></td>
          <td style="color:var(--gray)">{{ time(o.placed_at) }}</td>
          <td style="color:var(--gray)">{{ time(o.paid_at) }}</td>
          <td style="text-align:right;white-space:nowrap">
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/order-detail', query: { no: o.order_no } }">详情</router-link>
            <button v-if="o.status === 1 || o.status === 2" class="btn btn-primary btn-sm" style="margin-left:6px" @click="ship(o)">📦 发货</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="!items.length" style="text-align:center;color:var(--gray);padding:32px 0">
      <div style="font-size:28px;margin-bottom:6px">📭</div>该状态下暂无订单，试试其他筛选或搜索词
    </div>
  </div>

  <div v-if="pages > 1" style="display:flex;justify-content:center;gap:8px;margin-top:16px;align-items:center">
    <button class="btn btn-secondary btn-sm" :disabled="page <= 1" @click="page--; load()">←</button>
    <span style="font-size:13px;color:var(--gray)">第 {{ page }} / {{ pages }} 页</span>
    <button class="btn btn-secondary btn-sm" :disabled="page >= pages" @click="page++; load()">→</button>
  </div>

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
      <button class="btn btn-primary btn-block" style="margin-top:12px" @click="shipConfirm">确认发货</button>
    </div>
  </div>
</template>
