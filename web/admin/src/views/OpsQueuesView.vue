<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { money, dt } from '../composables/format'
import { useQuerySync } from '../composables/useQuerySync'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

/* 运营队列四合一：弃购找回 / 对账历史 / GDPR 数据请求 / 营销名单（Newsletter + 到货通知）
 * 范式对齐 MembersView/TicketsView：卡内表格 + EmptyState + Pagination embed（直接消费响应 pages 字段） */
const SIZE = 20
const TABS = [
  ['abandoned', '弃购找回'],
  ['reconcile', '对账历史'],
  ['gdpr', 'GDPR 数据请求'],
  ['lists', '营销名单'],
]

/* tab/分页入 URL（单 page 共用，tab 切换重置页码）；其余筛选为页内状态不污染 URL */
const st = reactive({ tab: 'abandoned', page: 1 })
useQuerySync(st, { nums: ['page'], defaults: { tab: 'abandoned', page: 1 } })
if (!TABS.some(([k]) => k === st.tab)) st.tab = 'abandoned'

/* 各数据槽独立：items/total/pages/loaded/err（err 非空→空态置顶 + 卡内横幅） */
const slot = () => ({ items: [], total: 0, pages: 1, loaded: false, err: '' })
const d = reactive({ abandoned: slot(), reconcile: slot(), gdpr: slot(), nl: slot(), sn: slot() })

/* 对账 ReconciliationDaily.status：0平 1差异告警 2已处理（models/reconcile.py） */
const RC_STATUS = {
  0: { label: '平', cls: 'tag-done' },
  1: { label: '差异告警', cls: 'tag-error' },
  2: { label: '已处理', cls: 'tag-ship' },
}

/* 通用拉取：写回对应槽（pages 直消费），失败记 err 不清旧数据 */
async function fetchSlot(key, url) {
  const s = d[key]
  s.err = ''
  try {
    const r = await req('GET', url)
    s.items = r.items || []
    s.total = r.total ?? 0
    s.pages = Math.max(1, r.pages ?? 1)
    st.page = r.page || st.page
  } catch (e) {
    s.err = e.message || ''
    toast('列表加载失败：' + (e.message || ''), 'error')
  }
  s.loaded = true
}

/* ===== tab=abandoned 弃购 ===== */
function loadAbandoned(p = 1) {
  return fetchSlot('abandoned', `/api/admin/ops/abandoned-carts?page=${p}&size=${SIZE}`)
}

/* ===== tab=reconcile 对账：date_from/date_to 直传 YYYY-MM-DD ===== */
const rcFrom = ref('')
const rcTo = ref('')
function loadReconcile(p = 1) {
  const params = new URLSearchParams({ page: p, size: SIZE })
  if (rcFrom.value) params.set('date_from', rcFrom.value)
  if (rcTo.value) params.set('date_to', rcTo.value)
  return fetchSlot('reconcile', '/api/admin/ops/reconciliations?' + params)
}
function resetRcRange() { rcFrom.value = ''; rcTo.value = ''; loadReconcile(1) }

/* ===== tab=gdpr：type 1导出 2删除；status 0待处理 1已完成 2已驳回 ===== */
const gType = ref('')
const gStatus = ref('')
function loadGdpr(p = 1) {
  const params = new URLSearchParams({ page: p, size: SIZE })
  if (gType.value !== '') params.set('type', gType.value)
  if (gStatus.value !== '') params.set('status', gStatus.value)
  return fetchSlot('gdpr', '/api/admin/ops/data-requests?' + params)
}
function setGdprFilter() { loadGdpr(1) }

/* 待处理行操作：立即执行（danger，删除类文案强调匿名化不可恢复）/ 驳回 */
const gdprTarget = ref(null)
const execDlg = ref(false)
const rejDlg = ref(false)
const gdprBusy = ref(false)
function openExec(r) { gdprTarget.value = r; execDlg.value = true }
function openRej(r) { gdprTarget.value = r; rejDlg.value = true }
async function execConfirm() {
  if (gdprBusy.value || !gdprTarget.value) return
  gdprBusy.value = true
  try {
    const r = await req('POST', `/api/admin/ops/data-requests/${gdprTarget.value.id}/execute`)
    toast(r.anonymized ? `#${r.id} 已执行：用户数据已匿名化（不可恢复）` : `#${r.id} 已标记完成`, 'success')
    execDlg.value = false
    loadGdpr(st.page)
  } catch (e) {
    toast('执行失败：' + (e.data?.detail || e.message), 'error')
  } finally { gdprBusy.value = false }
}
async function rejConfirm() {
  if (gdprBusy.value || !gdprTarget.value) return
  gdprBusy.value = true
  try {
    const r = await req('POST', `/api/admin/ops/data-requests/${gdprTarget.value.id}/reject`)
    toast(`#${r.id} 已驳回`, 'success')
    rejDlg.value = false
    loadGdpr(st.page)
  } catch (e) {
    toast('驳回失败：' + (e.data?.detail || e.message), 'error')
  } finally { gdprBusy.value = false }
}

/* ===== tab=lists：二级切换 nl Newsletter / sn 到货通知 ===== */
const sub = ref('nl')
const nlQ = ref('')       /* Newsletter email 模糊（服务端 q） */
const snQ = ref('')       /* 到货通知 email：后端无 q，本地兜底过滤当前页 */
const snProd = ref('')    /* product_id 服务端筛选（可选） */
const snVar = ref('')     /* variant_id 服务端筛选（可选） */
function loadNl(p = 1) {
  const params = new URLSearchParams({ page: p, size: SIZE })
  const s = nlQ.value.trim()
  if (s) params.set('q', s)
  return fetchSlot('nl', '/api/admin/ops/newsletters?' + params)
}
function loadSn(p = 1) {
  const params = new URLSearchParams({ page: p, size: SIZE })
  if (snProd.value.trim()) params.set('product_id', snProd.value.trim())
  if (snVar.value.trim()) params.set('variant_id', snVar.value.trim())
  return fetchSlot('sn', '/api/admin/catalog/stock-notifies?' + params)
}
/* sn 本地 email 过滤（不动 total/pages，仅页内筛选） */
const snRows = computed(() => {
  const s = snQ.value.trim().toLowerCase()
  if (!s) return d.sn.items
  return d.sn.items.filter((r) => (r.email || '').toLowerCase().includes(s))
})

/* ===== 调度：lists tab 映射到 nl/sn 槽；tab/二级切换均重置页码 ===== */
const curKey = computed(() => (st.tab === 'lists' ? (sub.value === 'sn' ? 'sn' : 'nl') : st.tab))
const cur = computed(() => d[curKey.value])
function load(p = 1) {
  const fn = { abandoned: loadAbandoned, reconcile: loadReconcile, gdpr: loadGdpr, nl: loadNl, sn: loadSn }[curKey.value]
  return fn(p)
}
function setTab(k) { if (st.tab !== k) { st.tab = k; st.page = 1; load(1) } }
function setSub(k) { if (sub.value !== k) { sub.value = k; st.page = 1; load(1) } }
onMounted(() => load(st.page))
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">运营队列</h1>
      <span class="page-sub">弃购找回 / 每日对账 / GDPR 数据请求 / 营销名单</span>
    </div>
  </div>

  <div class="otab">
    <button v-for="[k, label] in TABS" :key="k" :class="{ on: st.tab === k }" style="background:none;border:none;cursor:pointer" @click="setTab(k)">{{ label }}</button>
  </div>

  <!-- ===== tab=abandoned 弃购找回 ===== -->
  <div v-if="st.tab === 'abandoned'">
    <div v-if="!d.abandoned.loaded" class="card skeleton" style="min-height:280px" />
    <EmptyState v-else-if="d.abandoned.err && !d.abandoned.items.length" icon="⚠️" title="弃购队列加载失败" :sub="d.abandoned.err">
      <template #action><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></template>
    </EmptyState>
    <div v-else class="card tbl-wrap">
      <div v-if="d.abandoned.err" class="err-banner"><span>⚠️ 刷新失败：{{ d.abandoned.err }}</span><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">客户邮箱</th><th>商品数</th><th>总件数</th><th>金额</th><th>最后活跃</th><th>搁置天数</th>
        </tr></thead>
        <tbody>
          <tr v-for="c in d.abandoned.items" :key="c.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:10px"><b>{{ c.email || '—' }}</b><div style="font-size:11.5px;color:var(--gray)">cart #{{ c.id }}</div></td>
            <td>{{ c.items_count ?? 0 }}</td>
            <td>{{ c.total_qty ?? 0 }}</td>
            <td style="white-space:nowrap">{{ money(c.amount_cents) }}</td>
            <td style="color:var(--gray);white-space:nowrap">{{ dt(c.updated_at) || '—' }}</td>
            <td><span class="tag" :class="(c.days_ago ?? 0) >= 7 ? 'tag-error' : 'tag-pending'">{{ c.days_ago ?? '—' }} 天</span></td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!d.abandoned.items.length" icon="🛒" title="暂无弃购 cart" sub="超 1 小时未结算且有商品的购物车将显示在这里" />
      <Pagination embed :page="st.page" :pages="d.abandoned.pages" :total="d.abandoned.total" unit="个" @go="load" />
    </div>
  </div>

  <!-- ===== tab=reconcile 对账历史 ===== -->
  <div v-else-if="st.tab === 'reconcile'">
    <div v-if="!d.reconcile.loaded" class="card skeleton" style="min-height:280px" />
    <EmptyState v-else-if="d.reconcile.err && !d.reconcile.items.length" icon="⚠️" title="对账历史加载失败" :sub="d.reconcile.err">
      <template #action><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></template>
    </EmptyState>
    <div v-else class="card tbl-wrap">
      <div v-if="d.reconcile.err" class="err-banner"><span>⚠️ 刷新失败：{{ d.reconcile.err }}</span><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></div>
      <div class="filter-bar" style="padding:12px 14px;border-bottom:1px solid var(--gray-light)">
        <input v-model="rcFrom" class="input" type="date" style="width:auto;height:38px;font-size:13px" title="起始日期（含）">
        <span style="color:var(--gray);font-size:12.5px">至</span>
        <input v-model="rcTo" class="input" type="date" style="width:auto;height:38px;font-size:13px" title="截止日期（含）">
        <button class="btn btn-secondary btn-sm" style="height:38px" @click="loadReconcile(1)">查询</button>
        <button class="btn btn-ghost btn-sm" style="height:38px" @click="resetRcRange">清空范围</button>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">对账日期</th><th>支付总额</th><th>订单总额</th><th>支付差异</th><th>退款差异</th><th>积分差异</th><th>状态</th><th>核对时间</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in d.reconcile.items" :key="r.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:10px;white-space:nowrap"><b>{{ String(r.reconcile_date || '').slice(0, 10) || '—' }}</b></td>
            <td style="white-space:nowrap">{{ money(r.payments_gross) }}</td>
            <td style="white-space:nowrap">{{ money(r.orders_paid_total) }}</td>
            <td><span class="tag" :class="r.diff_payment ? 'tag-error' : 'tag-done'">{{ money(r.diff_payment) }}</span></td>
            <td><span class="tag" :class="r.diff_refund ? 'tag-error' : 'tag-done'">{{ money(r.diff_refund) }}</span></td>
            <td><span class="tag" :class="r.diff_points ? 'tag-error' : 'tag-done'">{{ (r.diff_points ?? 0).toLocaleString() }}</span></td>
            <td><span class="tag" :class="RC_STATUS[r.status]?.cls || 'tag-pending'">{{ RC_STATUS[r.status]?.label ?? r.status }}</span></td>
            <td style="color:var(--gray);white-space:nowrap">{{ dt(r.checked_at) || '—' }}</td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!d.reconcile.items.length" icon="🧮" title="暂无对账记录" sub="每日定时对账完成后将显示在这里" />
      <Pagination embed :page="st.page" :pages="d.reconcile.pages" :total="d.reconcile.total" unit="天" @go="loadReconcile" />
    </div>
  </div>

  <!-- ===== tab=gdpr 数据请求 ===== -->
  <div v-else-if="st.tab === 'gdpr'">
    <div v-if="!d.gdpr.loaded" class="card skeleton" style="min-height:280px" />
    <EmptyState v-else-if="d.gdpr.err && !d.gdpr.items.length" icon="⚠️" title="数据请求加载失败" :sub="d.gdpr.err">
      <template #action><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></template>
    </EmptyState>
    <div v-else class="card tbl-wrap">
      <div v-if="d.gdpr.err" class="err-banner"><span>⚠️ 刷新失败：{{ d.gdpr.err }}</span><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></div>
      <div class="filter-bar" style="padding:12px 14px;border-bottom:1px solid var(--gray-light)">
        <select v-model="gType" class="input" style="width:auto;height:38px;font-size:13px" @change="setGdprFilter()">
          <option value="">全部类型</option><option value="1">导出</option><option value="2">删除</option>
        </select>
        <select v-model="gStatus" class="input" style="width:auto;height:38px;font-size:13px" @change="setGdprFilter()">
          <option value="">全部状态</option><option value="0">待处理</option><option value="1">已完成</option><option value="2">已驳回</option>
        </select>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">用户</th><th>类型</th><th>状态</th><th>申请时间</th><th>计划执行</th><th>完成时间</th><th style="text-align:right">操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in d.gdpr.items" :key="r.id" style="border-top:1px solid var(--gray-light)">
            <td style="padding:10px"><b>{{ r.email || 'user#' + r.user_id }}</b><div style="font-size:11.5px;color:var(--gray)">#{{ r.id }}</div></td>
            <td><span class="tag" :class="r.type === 2 ? 'tag-error' : 'tag-ship'">{{ r.type_text || r.type }}</span></td>
            <td><span class="tag" :class="r.status === 0 ? 'tag-pending' : r.status === 1 ? 'tag-done' : 'tag-error'">{{ r.status_text || r.status }}</span></td>
            <td style="color:var(--gray);white-space:nowrap">{{ dt(r.created_at) || '—' }}</td>
            <td style="color:var(--gray);white-space:nowrap">{{ dt(r.scheduled_at) || '—' }}</td>
            <td style="color:var(--gray);white-space:nowrap">{{ dt(r.fulfilled_at) || '—' }}</td>
            <td style="text-align:right;white-space:nowrap">
              <template v-if="r.status === 0">
                <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="openExec(r)">{{ r.type === 2 ? '⚠️ 立即执行' : '立即执行' }}</button>
                <button class="btn btn-secondary btn-sm" @click="openRej(r)">驳回</button>
              </template>
              <span v-else style="color:var(--gray);font-size:12px">—</span>
            </td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!d.gdpr.items.length" icon="🗂" title="暂无数据请求" sub="用户发起的导出/删除个人数据申请将显示在这里" />
      <Pagination embed :page="st.page" :pages="d.gdpr.pages" :total="d.gdpr.total" unit="条" @go="loadGdpr" />
    </div>
  </div>

  <!-- ===== tab=lists 营销名单（Newsletter / 到货通知 二级切换） ===== -->
  <template v-else>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
      <button class="mtab" :class="{ on: sub === 'nl' }" @click="setSub('nl')">Newsletter</button>
      <button class="mtab" :class="{ on: sub === 'sn' }" @click="setSub('sn')">到货通知</button>
    </div>

    <!-- Newsletter 订阅者 -->
    <div v-if="sub === 'nl'">
      <div v-if="!d.nl.loaded" class="card skeleton" style="min-height:280px" />
      <EmptyState v-else-if="d.nl.err && !d.nl.items.length" icon="⚠️" title="Newsletter 加载失败" :sub="d.nl.err">
        <template #action><button class="btn btn-secondary btn-sm" @click="loadNl(st.page)">重试</button></template>
      </EmptyState>
      <div v-else class="card tbl-wrap">
        <div v-if="d.nl.err" class="err-banner"><span>⚠️ 刷新失败：{{ d.nl.err }}</span><button class="btn btn-secondary btn-sm" @click="loadNl(st.page)">重试</button></div>
        <div class="filter-bar" style="padding:12px 14px;border-bottom:1px solid var(--gray-light)">
          <input v-model="nlQ" class="input" style="width:220px" placeholder="搜订阅邮箱" @keydown.enter="loadNl(1)">
          <button class="btn btn-secondary btn-sm" style="height:38px" @click="loadNl(1)">搜索</button>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="text-align:left;color:var(--gray)">
            <th style="padding:10px">邮箱</th><th>来源</th><th>Klaviyo 同步</th><th>订阅时间</th>
          </tr></thead>
          <tbody>
            <tr v-for="(n, i) in d.nl.items" :key="n.email || i" style="border-top:1px solid var(--gray-light)">
              <td style="padding:10px"><b>{{ n.email }}</b></td>
              <td>{{ n.source || '—' }}</td>
              <td><span class="tag" :class="n.klaviyo_synced ? 'tag-done' : 'tag-pending'">{{ n.klaviyo_synced ? '已同步' : '未同步' }}</span></td>
              <td style="color:var(--gray);white-space:nowrap">{{ dt(n.created_at) || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-if="!d.nl.items.length" :icon="nlQ.trim() ? '🔍' : '✉️'" :title="nlQ.trim() ? '未找到匹配的订阅' : '暂无 Newsletter 订阅'" :sub="nlQ.trim() ? '试试调整或清除搜索' : '页脚/结账页订阅的用户将显示在这里'" />
        <Pagination embed :page="st.page" :pages="d.nl.pages" :total="d.nl.total" unit="位" @go="loadNl" />
      </div>
    </div>

    <!-- 到货通知登记 -->
    <div v-else>
      <div v-if="!d.sn.loaded" class="card skeleton" style="min-height:280px" />
      <EmptyState v-else-if="d.sn.err && !d.sn.items.length" icon="⚠️" title="到货通知加载失败" :sub="d.sn.err">
        <template #action><button class="btn btn-secondary btn-sm" @click="loadSn(st.page)">重试</button></template>
      </EmptyState>
      <div v-else class="card tbl-wrap">
        <div v-if="d.sn.err" class="err-banner"><span>⚠️ 刷新失败：{{ d.sn.err }}</span><button class="btn btn-secondary btn-sm" @click="loadSn(st.page)">重试</button></div>
        <div class="filter-bar" style="padding:12px 14px;border-bottom:1px solid var(--gray-light)">
          <input v-model="snQ" class="input" style="width:200px" placeholder="搜登记邮箱（本页）">
          <input v-model="snProd" class="input" type="number" min="1" style="width:130px" placeholder="商品 ID" @keydown.enter="loadSn(1)">
          <input v-model="snVar" class="input" type="number" min="1" style="width:130px" placeholder="变体 ID" @keydown.enter="loadSn(1)">
          <button class="btn btn-secondary btn-sm" style="height:38px" @click="loadSn(1)">筛选</button>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="text-align:left;color:var(--gray)">
            <th style="padding:10px">邮箱</th><th>SKU</th><th>商品</th><th>通知状态</th><th>登记时间</th>
          </tr></thead>
          <tbody>
            <tr v-for="r in snRows" :key="r.id" style="border-top:1px solid var(--gray-light)">
              <td style="padding:10px"><b>{{ r.email }}</b></td>
              <td><code>{{ r.variant?.sku || '—' }}</code></td>
              <td><router-link :to="{ path: '/product-edit', query: { id: r.product?.id } }" style="color:var(--plum)">{{ r.product?.title || '#' + r.product?.id || '—' }}</router-link></td>
              <td><span class="tag" :class="r.notified_at ? 'tag-done' : 'tag-pending'">{{ r.notified_at ? '已通知 ' + dt(r.notified_at) : '待补货' }}</span></td>
              <td style="color:var(--gray);white-space:nowrap">{{ dt(r.created_at) || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-if="!snRows.length" icon="🔔" title="暂无到货通知" sub="缺货商品的到货提醒登记将显示在这里" />
        <Pagination embed :page="st.page" :pages="d.sn.pages" :total="d.sn.total" unit="条" @go="loadSn" />
      </div>
    </div>
  </template>

  <!-- 立即执行确认（删除类强调匿名化不可恢复） -->
  <ConfirmDialog
    :open="execDlg" title="立即执行数据请求" danger confirm-text="确认执行" :busy="gdprBusy"
    :body="gdprTarget?.type === 2
      ? `确认立即执行 #${gdprTarget?.id}（${gdprTarget?.email || ''}）的删除请求？用户数据将被匿名化（订单脱敏、账号不可复原），操作不可恢复！`
      : `确认立即执行 #${gdprTarget?.id}（${gdprTarget?.email || ''}）的导出请求？执行后该请求将标记为已完成。`"
    @confirm="execConfirm" @close="execDlg = false"
  />

  <!-- 驳回确认 -->
  <ConfirmDialog
    :open="rejDlg" title="驳回数据请求" :body="`确认驳回 #${gdprTarget?.id}（${gdprTarget?.email || ''}）？驳回后用户需重新发起申请。`"
    confirm-text="确认驳回" :busy="gdprBusy" @confirm="rejConfirm" @close="rejDlg = false"
  />
</template>

<style scoped>
/* 刷新失败横幅：pale-error 底 + error 字，圆角，卡内顶部 */
.err-banner{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 14px;margin:12px 12px 0;background:var(--pale-error);color:var(--error);border-radius:10px;font-size:12.5px}
</style>
