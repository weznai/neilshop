<script setup>
import { onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { money, dt, dDate } from '../composables/format'
import { useQuerySync } from '../composables/useQuerySync'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

/* 订阅盒管理：状态 tab + email 搜索 + 代操作（暂停/恢复/取消，复用用户侧状态机错误码）
 * Subscription.status 实测值域：1生效 2已暂停 5已取消（service_subscriptions.STATUS_TEXT） */
const subs = ref([])
const total = ref(0)
const pages = ref(1)          /* 直接消费响应 pages 字段 */
const SIZE = 20
const loaded = ref(false)
const loadErr = ref(false)
const errMsg = ref('')        /* 最近一次加载失败信息（空态 sub / 横幅文案） */
const rowBusy = ref(0)        /* 按行隔离：正在操作的行 id（0=空闲），仅该行按钮 loading */

/* 筛选/分页 URL 同步：status '' 全部 / 1 活跃 / 2 暂停 / 5 已取消 */
const st = reactive({ status: '', q: '', page: 1 })
useQuerySync(st, { nums: ['page'], defaults: { status: '', q: '', page: 1 } })
if (!['', '1', '2', '5'].includes(st.status)) st.status = ''

const TABS = [['', '全部'], ['1', '活跃'], ['2', '暂停'], ['5', '已取消']]
/* 状态 tag 视觉：1 绿（生效）/ 2 黄（暂停）/ 5 红（取消），文案直显后端 status_text */
const stCls = (s) => (s === 1 ? 'tag-paid' : s === 2 ? 'tag-pending' : 'tag-error')

/* 取消原因：后端 cancel_reason 为 1-4 枚举 int（无文案表，前端自定展示） */
const CANCEL_REASONS = { 1: '频率太频繁', 2: '暂时不需要', 3: '价格因素', 4: '其他' }

async function load(p = 1) {
  /* 刷新保留旧数据，骨架只在首载出现 */
  loadErr.value = false
  errMsg.value = ''
  try {
    const params = new URLSearchParams({ page: p, size: SIZE })
    if (st.status !== '') params.set('status', st.status)
    const s = st.q.trim()
    if (s) params.set('q', s)   /* 后端已支持 q 服务端搜索（邮箱），无需本地兜底 */
    const d = await req('GET', '/api/admin/member/subscriptions?' + params)
    subs.value = d.items || []
    total.value = d.total ?? 0
    pages.value = Math.max(1, d.pages ?? 1)
    st.page = d.page || p
  } catch (e) {
    loadErr.value = true
    errMsg.value = e.message || ''
    toast('订阅列表加载失败：' + (e.message || ''), 'error')
  }
  loaded.value = true
}
onMounted(() => load(st.page))

function setTab(v) { if (st.status !== v) { st.status = v; load(1) } }
function search() { load(1) }
/* 空态文案：任一筛选生效→未匹配，否则暂无 */
const filtered = () => st.q.trim() !== '' || st.status !== ''

/* ===== 代操作：暂停（可选恢复日期）/ 恢复 / 取消（可选原因枚举），409/404 toast 展示 detail 原串加中文前缀 ===== */
const target = ref(null)      /* 当前操作的行 */
const pauseDlg = ref(false)   /* 暂停：手写 modal（date 输入不适用 ConfirmDialog 文本 reason 槽） */
const pauseResumeAt = ref('')
const resumeDlg = ref(false)
const cancelDlg = ref(false)
const cancelReason = ref('')  /* 枚举 int 字符串，提交转 int；空=不传 */
const actBusy = ref(false)

/* 操作后回填：以单条响应就地更新行（失败不动），再静默重拉修正 total/pages */
function patchRow(r) {
  subs.value = subs.value.map((x) => (x.id === r.id ? { ...x, ...r } : x))
}
async function refreshQuiet() {
  try { await load(st.page) } catch (_) { /* 已有成功 toast，静默 */ }
}

function openPause(r) { target.value = r; pauseResumeAt.value = r.resume_at ? String(r.resume_at).slice(0, 10) : ''; pauseDlg.value = true }
async function pauseConfirm() {
  if (actBusy.value || !target.value) return
  actBusy.value = true
  rowBusy.value = target.value.id
  try {
    const body = {}
    if (pauseResumeAt.value) body.resume_at = pauseResumeAt.value   /* date → 后端 datetime 解析为当日 00:00 */
    const r = await req('POST', `/api/admin/member/subscriptions/${target.value.id}/pause`, body)
    patchRow(r)
    toast(`已暂停 #${r.id}，状态：${r.status_text}`, 'success')
    pauseDlg.value = false
    refreshQuiet()
  } catch (e) {
    toast('暂停失败：' + (e.data?.detail || e.message), 'error')
  } finally { actBusy.value = false; rowBusy.value = 0 }
}

function openResume(r) { target.value = r; resumeDlg.value = true }
async function resumeConfirm() {
  if (actBusy.value || !target.value) return
  actBusy.value = true
  rowBusy.value = target.value.id
  try {
    const r = await req('POST', `/api/admin/member/subscriptions/${target.value.id}/resume`)
    patchRow(r)
    toast(`已恢复 #${r.id}，下一期 ${dt(r.next_billing_at) || '—'}`, 'success')
    resumeDlg.value = false
    refreshQuiet()
  } catch (e) {
    toast('恢复失败：' + (e.data?.detail || e.message), 'error')
  } finally { actBusy.value = false; rowBusy.value = 0 }
}

function openCancel(r) { target.value = r; cancelReason.value = ''; cancelDlg.value = true }
async function cancelConfirm() {
  if (actBusy.value || !target.value) return
  actBusy.value = true
  rowBusy.value = target.value.id
  try {
    const body = {}
    if (cancelReason.value) body.cancel_reason = Number(cancelReason.value)
    const r = await req('POST', `/api/admin/member/subscriptions/${target.value.id}/cancel`, body)
    patchRow(r)
    toast(`已取消 #${r.id}（不可恢复）`, 'success')
    cancelDlg.value = false
    refreshQuiet()
  } catch (e) {
    toast('取消失败：' + (e.data?.detail || e.message), 'error')
  } finally { actBusy.value = false; rowBusy.value = 0 }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">订阅管理</h1>
      <span class="page-sub">共 {{ total }} 条订阅</span>
    </div>
    <div class="filter-bar">
      <input v-model="st.q" class="input" style="width:220px" placeholder="搜订阅邮箱" @keydown.enter="search()">
      <button class="btn btn-secondary btn-sm" style="height:38px" @click="search()">搜索</button>
    </div>
  </div>

  <div class="otab">
    <button v-for="[v, label] in TABS" :key="v" :class="{ on: st.status === v }" style="background:none;border:none;cursor:pointer" @click="setTab(v)">{{ label }}</button>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px" />

  <!-- 首屏失败（无旧数据）：错误空态置顶，隐藏表格 -->
  <EmptyState v-else-if="loadErr && !subs.length" icon="⚠️" title="订阅列表加载失败" :sub="errMsg || '服务端可能未启动或会话已过期'">
    <template #action><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></template>
  </EmptyState>

  <div v-else class="card tbl-wrap">
    <!-- 刷新失败（有旧数据）：卡内顶部横幅，旧数据保留 -->
    <div v-if="loadErr" class="err-banner">
      <span>⚠️ 刷新失败：{{ errMsg || '网络异常，下方为旧数据' }}</span>
      <button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="padding:10px">订阅</th><th>方案</th><th>金额</th><th>状态</th>
        <th>下一期扣款</th><th>恢复时间</th><th>跳过至</th><th>创建时间</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="r in subs" :key="r.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:10px"><b>#{{ r.id }}</b><div style="font-size:11.5px;color:var(--gray)"><router-link v-if="r.email" :to="{ path: '/members', query: { q: r.email } }" style="color:var(--plum)">{{ r.email }}</router-link><template v-else>user#{{ r.user_id }}</template></div></td>
          <td>{{ r.plan_text || '—' }}<span v-if="r.style_mode" style="font-size:11.5px;color:var(--gray)"> · {{ r.style_mode === 2 ? '盲盒惊喜' : '自选' }}</span></td>
          <td style="white-space:nowrap">{{ r.price_cents != null ? money(r.price_cents) : '—' }}</td>
          <td><span class="tag" :class="stCls(r.status)">{{ r.status_text || r.status }}</span></td>
          <td style="color:var(--gray);white-space:nowrap">{{ dt(r.next_billing_at) || '—' }}</td>
          <td style="color:var(--gray);white-space:nowrap">{{ r.resume_at ? dt(r.resume_at) : '—' }}</td>
          <td style="color:var(--gray);white-space:nowrap">{{ r.skip_until ? '跳过至 ' + dDate(r.skip_until) : '—' }}</td>
          <td style="color:var(--gray);white-space:nowrap">{{ dt(r.created_at) || '—' }}</td>
          <td style="text-align:right;white-space:nowrap">
            <template v-if="r.status === 1">
              <button class="btn btn-secondary btn-sm" :class="{ loading: rowBusy === r.id }" :disabled="rowBusy === r.id" @click="openPause(r)">⏸ 暂停</button>
              <button class="btn btn-ghost btn-sm" style="color:var(--error)" :class="{ loading: rowBusy === r.id }" :disabled="rowBusy === r.id" @click="openCancel(r)">✕ 取消</button>
            </template>
            <button v-else-if="r.status === 2" class="btn btn-primary btn-sm" :class="{ loading: rowBusy === r.id }" :disabled="rowBusy === r.id" @click="openResume(r)">▶ 恢复</button>
            <span v-else style="color:var(--gray);font-size:12px">{{ r.cancel_reason ? '原因：' + (CANCEL_REASONS[r.cancel_reason] || r.cancel_reason) : '—' }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <EmptyState v-if="!subs.length" :icon="filtered() ? '🔍' : '📦'" :title="filtered() ? '未找到匹配的订阅' : '暂无订阅'" :sub="filtered() ? '试试调整或清除筛选' : '用户订阅 Nail Club 后将显示在这里'" />
    <Pagination embed :page="st.page" :pages="pages" :total="total" unit="条" @go="load" />
  </div>

  <!-- 暂停弹窗：可选恢复日期（date 输入，手写 modal 承载） -->
  <div v-if="pauseDlg" class="modal open" @click.self="!actBusy && (pauseDlg = false)">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="!actBusy && (pauseDlg = false)">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">⏸ 暂停订阅 #{{ target?.id }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:14px">
        暂停期间不扣款、不发货；恢复时间仅作记录备忘（到期不会自动恢复，需手动恢复）。
      </p>
      <div class="field">
        <label>恢复时间（可选）</label>
        <input v-model="pauseResumeAt" class="input" type="date">
      </div>
      <button class="btn btn-primary btn-block" style="margin-top:12px" :class="{ loading: actBusy }" :disabled="actBusy" @click="pauseConfirm">{{ actBusy ? '提交中…' : '确认暂停' }}</button>
    </div>
  </div>

  <!-- 恢复确认 -->
  <ConfirmDialog
    :open="resumeDlg" title="恢复订阅" :body="`确认恢复 #${target?.id}（${target?.email || ''}）？恢复后将继续按周期扣款发货${target?.resume_at ? '，原定恢复时间 ' + dt(target.resume_at) + ' 将被清除' : ''}。`"
    confirm-text="确认恢复" :busy="actBusy" @confirm="resumeConfirm" @close="resumeDlg = false"
  />

  <!-- 取消确认：原因枚举 int（1-4），可选 -->
  <div v-if="cancelDlg" class="modal open" @click.self="!actBusy && (cancelDlg = false)">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" @click="!actBusy && (cancelDlg = false)">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">✕ 取消订阅 #{{ target?.id }}</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:14px">
        取消后订阅终止、不再扣款，<b style="color:var(--error)">操作不可恢复</b>；如需再次订阅须由用户重新下单。
      </p>
      <div class="field">
        <label>取消原因（可选）</label>
        <select v-model="cancelReason" class="input">
          <option value="">不指定</option>
          <option v-for="(txt, v) in CANCEL_REASONS" :key="v" :value="String(v)">{{ v }} · {{ txt }}</option>
        </select>
      </div>
      <button class="btn btn-danger btn-block" style="margin-top:12px" :class="{ loading: actBusy }" :disabled="actBusy" @click="cancelConfirm">{{ actBusy ? '提交中…' : '确认取消（不可恢复）' }}</button>
    </div>
  </div>
</template>

<style scoped>
/* 刷新失败横幅：pale-error 底 + error 字，圆角，卡内顶部 */
.err-banner{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 14px;margin:12px 12px 0;background:var(--pale-error);color:var(--error);border-radius:10px;font-size:12.5px}
</style>
