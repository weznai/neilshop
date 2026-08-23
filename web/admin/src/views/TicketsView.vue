<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'
import { dt } from '../composables/format'
import { useQuerySync } from '../composables/useQuerySync'
import { TSTATUS, TICKET_ERR, mapErr } from '../constants/trade'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const session = useSessionStore()
const tickets = ref([])
const total = ref(0)
const SIZE = 50
const loaded = ref(false)
const loadErr = ref(false)
const errMsg = ref('')       /* 最近一次加载失败信息（空态 sub / 横幅文案） */

/* 筛选 URL 同步：tab/q/priority/cat/mine/page 回填与写回（priority '0'=仅紧急；cat ''=全部分类；mine '1'=我的工单） */
const st = reactive({ tab: 'all', q: '', priority: '', cat: '', mine: '', page: 1 })
useQuerySync(st, { nums: ['page'], defaults: { tab: 'all', priority: '', cat: '', mine: '', page: 1 } })

/* 状态映射统一走 constants/trade.js（TSTATUS）
 * 状态机：0 新工单 → 1 处理中（回复后）→ 2 等待客户 / 3 已解决 → 4 已关闭（带 close_reason） */
/* TicketCategory 1-6（core/enums.py）；priority 0=紧急 1=普通（models/support.py，列表按紧急在前排序） */
const CATEGORY = { 1: '物流', 2: '质量', 3: '退换', 4: '账户', 5: '售前', 6: '其他' }
const TABS = [
  ['all', '全部', null],
  ['new', '新工单', 0],
  ['processing', '处理中', 1],
  ['wait', '等待客户', 2],
  ['closed', '已关', '3,4'],
]

const active = ref(null)      /* 列表行 */
const thread = ref(null)      /* {messages: [{sender, content, created_at}]} */
const reply = ref('')
const busy = ref(false)
const closeDlg = ref(false)
const threadBox = ref(null)   /* 线程滚动容器（回复成功后跟随拉底） */

/* 后端错误码 → 中文（invalid_status_transition 等），无匹配回退原始 detail/message */
const terr = (e) => mapErr(e.data?.detail, TICKET_ERR) || e.data?.detail || e.message

/* 仅 status===4（已关闭）锁定操作；1 可转等待客户/已解决，3 走「确认关闭」3→4 */
const isClosed = computed(() => !!active.value && active.value.status === 4)
const isResolved = computed(() => !!active.value && active.value.status === 3)
/* 响应含 total/page/size（无 pages），页数由 total 折算 */
const pages = computed(() => Math.max(1, Math.ceil(total.value / SIZE)))

function buildUrl(status, p, size = SIZE) {
  const params = new URLSearchParams({ page: p, size })
  if (status !== null && status !== undefined) params.set('status', status)
  if (st.cat !== '') params.set('category', st.cat)
  if (st.priority !== '') params.set('priority', st.priority)
  if (st.mine === '1' && session.user?.id) params.set('assignee', session.user.id)
  const s = st.q.trim()
  if (s) params.set('q', s)
  return '/api/admin/ops/tickets?' + params
}

async function load(p = 1) {
  /* 刷新保留旧数据，骨架只在首载出现 */
  loadErr.value = false
  errMsg.value = ''
  try {
    /* 已关 tab 由后端组合状态 status=3,4 单请求返回 */
    const stt = TABS.find((t) => t[0] === st.tab)?.[2]
    const d = await req('GET', buildUrl(stt, p))
    tickets.value = d.items || []
    total.value = d.total ?? 0
    st.page = p
    /* 刷新后按 ticket_no 重绑 active 到新数组中的行（旧引用已与列表脱钩；被筛掉则清空） */
    if (active.value) active.value = tickets.value.find((t) => t.ticket_no === active.value.ticket_no) || null
  } catch (e) {
    loadErr.value = true
    errMsg.value = e.message || ''
    toast('工单列表加载失败：' + (e.message || ''), 'error')
  }
  loaded.value = true
}
onMounted(() => load(1))

function setTab(k) { if (st.tab !== k) { st.tab = k; load(1) } }
function setCat(v) { st.cat = v; load(1) }
function setMine(v) { st.mine = v; load(1) }
function togglePriority() { st.priority = st.priority === '0' ? '' : '0'; load(1) }
function search() { load(1) }
/* 列表空态文案：任一筛选（tab/仅紧急/分类/我的/搜索）生效→未匹配，否则暂无 */
const filtered = computed(() => st.tab !== 'all' || st.priority !== '' || st.cat !== '' || st.mine !== '' || st.q.trim() !== '')

/* 快捷回复模板：GET /api/support/templates（公开端点，支持 ?category= 过滤，返回 [{id,category,title,content}]） */
const templates = ref([])          /* 全量模板（当前工单分类无匹配时兜底显示） */
const templatesLoaded = ref(false)
const catTpl = reactive(new Map()) /* category → 模板列表（按分类缓存，避免来回切换重复请求） */
async function loadTemplates() {
  if (templatesLoaded.value) return
  try {
    templates.value = (await req('GET', '/api/support/templates')) || []
    templatesLoaded.value = true
  } catch (_) { /* 下拉里提示加载失败，可重选再试 */ }
}
/* 打开线程时按当前工单分类带参拉取（Map 按分类缓存）；返回项含 category 字段，二次过滤兜底 */
async function loadCatTemplates(cat) {
  if (catTpl.has(cat)) return
  try {
    const items = (await req('GET', '/api/support/templates?category=' + cat)) || []
    catTpl.set(cat, items.filter((x) => x.category === cat))
  } catch (_) { catTpl.set(cat, []) }   /* 失败置空缓存，下拉回退全量 */
}
/* 下拉数据源：当前工单分类模板优先，无匹配回退全量 */
const tplOptions = computed(() => {
  const c = active.value?.category
  const items = c ? catTpl.get(c) : null
  if (items && items.length) return items
  return templates.value
})
const tplLabel = computed(() => (!templatesLoaded.value && !tplOptions.value.length ? '加载快捷模板…' : tplOptions.value.length ? '快捷模板…' : '暂无模板'))
function applyTemplate(e) {
  const id = parseInt(e.target.value, 10)
  e.target.value = ''
  const t = tplOptions.value.find((x) => x.id === id)
  if (!t) return
  reply.value = reply.value.trim() ? reply.value.trim() + '\n' + t.content : t.content
}

/* 工单线程走用户侧查询接口：匿名路径需 ticket_no+email，与后台会话无关 → credentials:'omit' 不发 cookie */
async function openTicket(t) {
  /* 区分「同票刷新」（回复成功/⟳ 重拉，按替换前是否在底部跟随）与「切换工单」（强制拉底） */
  const same = !!active.value && active.value.ticket_no === t.ticket_no
  const prevCount = same ? (thread.value?.messages || []).length : 0
  /* 替换线程数据「前」测是否在底部：DOM 增长后再测「距底 <80px」会把本在底部、
   * 但新消息高于 80px 的用户误判为不在底部而不跟随 */
  const el = threadBox.value
  const wasBottom = !same || !el || el.scrollHeight - el.scrollTop - el.clientHeight < 80
  active.value = t
  thread.value = null
  loadAdmins()   /* 懒加载指派候选人（首次打开工单时拉取一次，缓存） */
  if (t.category) loadCatTemplates(t.category)   /* 预取该分类快捷模板（不阻塞线程加载） */
  const no = t.ticket_no   /* 竞态守卫：响应回来时已切换工单则丢弃 */
  try {
    const d = await req('GET', `/api/support/tickets?email=${encodeURIComponent(t.email)}&ticket_no=${encodeURIComponent(t.ticket_no)}`, undefined, { credentials: 'omit' })
    if (!active.value || active.value.ticket_no !== no) return
    const next = d.items?.[0] || { messages: [] }
    thread.value = next
    /* 切票 force；同票按 wasBottom（消息变少也视为 force） */
    scrollThread(!same || wasBottom || (next.messages || []).length < prevCount)
  } catch (e) {
    if (!active.value || active.value.ticket_no !== no) return
    thread.value = { messages: [], loadErr: true }
    toast('对话加载失败：' + (e.message || ''), 'error')
  }
}

/* 线程容器滚动：follow 由调用方在「替换线程数据前」测得的 wasBottom 传入（或强制 true）；
 * 上翻历史（follow=false）不拽回 */
function scrollThread(follow) {
  nextTick(() => {
    const el = threadBox.value
    if (!el || !follow) return
    el.scrollTop = el.scrollHeight
  })
}

async function send() {
  if (!reply.value.trim() || !active.value) return
  if (reply.value.length > 2000) { toast('回复内容过长（最多 2000 字）', 'error'); return }
  busy.value = true
  try {
    const t = await req('POST', `/api/admin/ops/tickets/${active.value.ticket_no}/reply`, { content: reply.value })
    reply.value = ''
    toast('回复已发送 ✓', 'success')
    Object.assign(active.value, t)   /* 同步右侧面板状态（0→1 处理中） */
    await openTicket(active.value)
    scrollThread(true)   /* 回复成功直接拉底（不依赖距底判定，新消息再高也跟随） */
    load(st.page)
  } catch (e) {
    /* 422 超长（pydantic 校验）识别为中文提示 */
    const det = JSON.stringify(e.data?.detail ?? e.message ?? '')
    toast('回复失败：' + (e.status === 422 && det.includes('2000') ? '回复内容过长（最多 2000 字）' : terr(e)), 'error')
  }
  finally { busy.value = false }
}

/* 状态流转：PUT /api/admin/support/tickets/{no}/status（2 等待客户 / 3 已解决；后端允许 1→2/3、2→3） */
async function setStatus(status) {
  busy.value = true
  try {
    const t = await req('PUT', `/api/admin/support/tickets/${active.value.ticket_no}/status`, { status })
    toast(status === 2 ? '已标记等待客户 ✓' : '已标记解决 ✓', 'success')
    Object.assign(active.value, t)
    load(st.page)
  } catch (e) { toast('操作失败：' + terr(e), 'error') }
  finally { busy.value = false }
}

/* 关闭工单：走专用端点 POST /ops/tickets/{no}/close（允许 0/1/2/3→4；PUT status=4 对新工单会 409）
 * ConfirmDialog danger + 关闭原因必填 */
function openClose() { closeDlg.value = true }
async function doClose(reason) {
  if (busy.value) return
  if (!reason) { toast('请填写关闭原因', 'error'); return }
  busy.value = true
  try {
    const t = await req('POST', `/api/admin/ops/tickets/${active.value.ticket_no}/close`, { close_reason: reason })
    toast('工单已关闭 ✓', 'success')
    closeDlg.value = false
    Object.assign(active.value, t)
    load(st.page)
  } catch (e) { toast('关闭失败：' + terr(e), 'error') }
  finally { busy.value = false }
}

/* 指派展示：优先 assignee_name（列表/详情新增），否则「#id」兜底 */
const assigneeText = (t) => t.assignee_admin_id
  ? (t.assignee_name || `#${t.assignee_admin_id}`)
  : '未指派'
/* 最后消息方文案（last_sender：1=客户 2=客服 3=系统，无消息 null） */
const SENDER_LABEL = { 1: '客户', 2: '客服', 3: '系统' }

/* CSV 导出：当前筛选（tab 状态/分类/仅紧急/我的/关键词）全量拉取，size=100 上限 2000 行 */
const exporting = ref(false)
const EXPORT_SIZE = 100
const EXPORT_MAX_ROWS = 2000
async function exportCsv() {
  if (exporting.value) return
  exporting.value = true
  try {
    /* 固化筛选快照（status/category/priority/mine/q 固化为常量逐页复用）：导出期间用户切换筛选不影响本次结果 */
    const snap = {
      status: TABS.find((t) => t[0] === st.tab)?.[2],
      cat: st.cat, priority: st.priority,
      assignee: st.mine === '1' ? (session.user?.id || null) : null,
      q: st.q.trim(),
    }
    const pageUrl = (p) => {
      const params = new URLSearchParams({ page: p, size: EXPORT_SIZE })
      if (snap.status !== null && snap.status !== undefined) params.set('status', snap.status)
      if (snap.cat !== '') params.set('category', snap.cat)
      if (snap.priority !== '') params.set('priority', snap.priority)
      if (snap.assignee) params.set('assignee', snap.assignee)
      if (snap.q) params.set('q', snap.q)
      return '/api/admin/ops/tickets?' + params
    }
    /* 按 ticket_no 去重：导出期间新插入的工单翻页可能重复出现 */
    const seen = new Set()
    const all = []
    const push = (arr) => { for (const t of arr || []) if (!seen.has(t.ticket_no)) { seen.add(t.ticket_no); all.push(t) } }
    const first = await req('GET', pageUrl(1))
    push(first.items)
    const totalMatch = first.total ?? all.length
    const maxPage = Math.min(Math.ceil(totalMatch / EXPORT_SIZE) || 1, Math.ceil(EXPORT_MAX_ROWS / EXPORT_SIZE))
    for (let p = 2; p <= maxPage && all.length < EXPORT_MAX_ROWS; p++) push((await req('GET', pageUrl(p))).items)
    if (all.length > EXPORT_MAX_ROWS) all.length = EXPORT_MAX_ROWS
    if (Math.ceil(totalMatch / EXPORT_SIZE) > maxPage || all.length >= EXPORT_MAX_ROWS) {
      toast('匹配结果过多，仅导出前 ' + all.length + ' 条', 'error')
    }
    /* CSV 转义：含逗号/引号/换行的字段包引号并双写引号 */
    const cell = (v) => {
      const s = String(v ?? '')
      return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
    }
    const rows = [['工单号', '主题', '邮箱', '分类', '状态', '优先级', '指派', '创建时间', '最后消息时间', '最后消息方'],
      ...all.map((t) => [t.ticket_no, t.subject, t.email, CATEGORY[t.category] || '其他', TSTATUS[t.status]?.label,
        t.priority === 0 ? '紧急' : '普通', assigneeText(t), dt(t.created_at),
        t.last_message_at ? dt(t.last_message_at) : '', t.last_sender != null ? (SENDER_LABEL[t.last_sender] || '—') : ''])]
    const csv = rows.map((r) => r.map(cell).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'tickets_' + new Date().toISOString().slice(0, 10).replace(/-/g, '') + '.csv'
    a.click()
    URL.revokeObjectURL(url)
    toast('已导出 ' + all.length + ' 张 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  exporting.value = false
}

/* 指派候选人：GET /ops/admins（role≥2 且启用的管理账号），首次打开工单时拉取一次缓存，失败下次重试 */
const admins = ref([])
const adminsLoaded = ref(false)
async function loadAdmins() {
  if (adminsLoaded.value) return
  try {
    admins.value = (await req('GET', '/api/admin/ops/admins')).items || []
    adminsLoaded.value = true
  } catch (_) { /* 失败保持空列表，指派下拉仅剩占位项 */ }
}
/* 指派给我：AssignIn 需 admin_id（取当前登录管理员 id），接入 busy 防重复提交 */
async function assignMe() {
  if (busy.value) return
  const adminId = session.user?.id
  if (!adminId) { toast('无法获取当前管理员 ID，请刷新页面重试', 'error'); return }
  busy.value = true
  try {
    const t = await req('POST', `/api/admin/ops/tickets/${active.value.ticket_no}/assign`, { admin_id: adminId })
    Object.assign(active.value, t)
    toast('已指派给你 ✓', 'success')
    load(st.page)
  } catch (e) { toast('指派失败：' + terr(e), 'error') }
  finally { busy.value = false }
}
/* 指派给其他管理员：下拉选择即提交（选项文案「姓名 email前缀」，当前指派人标记） */
async function assignTo(idStr) {
  if (busy.value) return
  const adminId = Number(idStr)
  if (!adminId || !active.value) return
  busy.value = true
  try {
    const t = await req('POST', `/api/admin/ops/tickets/${active.value.ticket_no}/assign`, { admin_id: adminId })
    Object.assign(active.value, t)
    toast('已指派给 ' + (admins.value.find((a) => a.id === adminId)?.name || '#' + adminId) + ' ✓', 'success')
    load(st.page)
  } catch (e) { toast('指派失败：' + terr(e), 'error') }
  finally { busy.value = false }
}

/* 重开工单：PUT status=1（后端支持 3→1 已解决重开 / 4→1 已关闭重开），成功后面板回到可回复态并刷新行 */
async function reopen() {
  if (busy.value || !active.value) return
  busy.value = true
  try {
    const t = await req('PUT', `/api/admin/support/tickets/${active.value.ticket_no}/status`, { status: 1 })
    toast('工单已重新打开 ✓', 'success')
    Object.assign(active.value, t)
    load(st.page)
  } catch (e) { toast('重开失败：' + terr(e), 'error') }
  finally { busy.value = false }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">客服工单</h1>
      <span class="page-sub">当前筛选共 {{ total }} 张工单</span>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <button class="btn btn-secondary" :disabled="exporting" @click="exportCsv">{{ exporting ? '导出中…' : '⬇ CSV' }}</button>
    </div>
  </div>

  <div class="filter-bar" style="margin-bottom:14px">
    <button v-for="[k, label] in TABS" :key="k" class="ttab" :class="{ on: st.tab === k }" @click="setTab(k)">{{ label }}</button>
    <span style="flex:1"></span>
    <button class="ttab" :class="{ on: st.priority === '0' }" title="只看紧急工单（priority=0）" @click="togglePriority">仅紧急</button>
    <select class="input" :value="st.cat" style="width:auto;height:38px;font-size:13px" @change="setCat($event.target.value)">
      <option value="">全部分类</option>
      <option v-for="(label, v) in CATEGORY" :key="v" :value="String(v)">{{ label }}</option>
    </select>
    <select class="input" :value="st.mine" style="width:auto;height:38px;font-size:13px" @change="setMine($event.target.value)">
      <option value="">全部工单</option>
      <option value="1">我的工单</option>
    </select>
    <input v-model="st.q" class="input" style="width:200px;height:38px" placeholder="邮箱 / 工单号 / 主题 / 订单号" @keydown.enter="search()">
    <button class="btn btn-secondary btn-sm" style="height:38px" @click="search()">搜索</button>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px;margin-bottom:14px" />

  <!-- 首屏失败（无旧数据）：错误空态置顶，隐藏列表 -->
  <EmptyState v-else-if="loadErr && !tickets.length" icon="⚠️" title="工单列表加载失败" :sub="errMsg || '服务端可能未启动或会话已过期'">
    <template #action><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></template>
  </EmptyState>

  <div v-else class="grid-2" style="align-items:start">
    <div class="card tbl-wrap">
      <!-- 刷新失败（有旧数据）：卡内顶部横幅，旧数据保留 -->
      <div v-if="loadErr" class="err-banner">
        <span>⚠️ 刷新失败：{{ errMsg || '网络异常，下方为旧数据' }}</span>
        <button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">工单号</th><th>主题</th><th>客户</th><th>首次回复</th><th>指派</th><th>状态</th></tr></thead>
        <tbody>
          <tr
            v-for="t in tickets" :key="t.ticket_no"
            style="border-top:1px solid var(--gray-light);cursor:pointer"
            :style="{ background: active && active.ticket_no === t.ticket_no ? 'var(--rose-pale)' : '' }"
            @click="openTicket(t)"
          >
            <td style="padding:11px 10px;white-space:nowrap">
              <b>{{ t.ticket_no }}</b>
              <span v-if="t.priority === 0" class="tag tag-error" style="margin-left:6px;font-size:10px">急</span>
            </td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="t.subject">
              {{ t.subject }}<span class="tag tag-cat" style="margin-left:6px;font-size:10px">{{ CATEGORY[t.category] || '其他' }}</span>
            </td>
            <td :title="t.email">{{ (t.email || '').split('@')[0] }}</td>
            <td>
              <span v-if="t.first_reply_at" class="tag tag-done">✓</span>
              <span v-else class="tag tag-pending">待回复</span>
            </td>
            <td>
              <span v-if="t.assignee_admin_id" class="tag tag-ship" :title="'#' + t.assignee_admin_id">{{ assigneeText(t) }}</span>
              <span v-else class="tag tag-pending">未指派</span>
            </td>
            <td>
              <span class="tag" :class="TSTATUS[t.status]?.cls">{{ TSTATUS[t.status]?.label }}</span>
              <!-- 最后消息：客户最后回复且处理中 → 蓝色提醒 tag；否则灰色小字时间（并入状态列省一列宽） -->
              <span v-if="t.last_sender === 1 && t.status === 1" class="tag tag-ship lm-tag" :title="'客户最后回复：' + (dt(t.last_message_at) || '—')">客户新回复</span>
              <div v-else-if="t.last_message_at" class="lm-time" :title="'最后消息：' + dt(t.last_message_at) + (t.last_sender != null ? '（' + (SENDER_LABEL[t.last_sender] || '—') + '）' : '')">{{ dt(t.last_message_at) }}</div>
            </td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!tickets.length" :icon="filtered ? '🔍' : '💬'" :title="filtered ? '未找到匹配的工单' : '暂无工单'" :sub="filtered ? '试试调整或清除筛选' : '客户提交工单后将显示在这里'" />
      <Pagination embed :page="st.page" :pages="pages" :total="total" unit="张" @go="load" />
    </div>

    <div class="card" style="padding:20px;position:sticky;top:16px">
      <EmptyState v-if="!active" icon="👈" title="选择一个工单查看对话" sub="点击左侧列表中的工单号或主题" />
      <template v-else>
        <div class="dhead">
          <div class="dtitle">{{ active.ticket_no }}</div>
          <span class="tag" :class="TSTATUS[active.status]?.cls">{{ TSTATUS[active.status]?.label }}</span>
        </div>
        <div class="page-sub" style="margin-bottom:12px">
          {{ active.subject }} · <router-link class="ono" :to="{ path: '/members', query: { q: active.email } }">{{ active.email }}</router-link><span v-if="active.order_no"> · 订单 <router-link class="ono" :to="{ path: '/order-detail', query: { no: active.order_no } }">{{ active.order_no }}</router-link></span> · 创建 {{ dt(active.created_at) }}
          <span v-if="active.assignee_admin_id"> · {{ assigneeText(active) }}</span>
        </div>

        <div class="dhead" style="margin-bottom:6px">
          <div class="dtitle">对话记录</div>
          <span v-if="thread" class="item-cnt">{{ (thread.messages || []).length }} 条</span>
          <span style="flex:1"></span>
          <button class="btn btn-secondary btn-sm" style="height:28px" title="重新拉取当前工单对话" @click="openTicket(active)">⟳ 刷新</button>
        </div>
        <div ref="threadBox" style="display:grid;gap:10px;max-height:320px;overflow-y:auto;margin-bottom:14px">
          <div v-if="!thread" style="color:var(--gray);font-size:13px;text-align:center;padding:20px 0">加载对话…</div>
          <template v-else>
            <template v-for="(m, i) in thread.messages || []" :key="i">
              <!-- 系统消息：居中灰色小条 -->
              <div v-if="m.sender === 3" class="sysmsg">{{ m.content }}<span class="sysmsg-time">{{ dt(m.created_at) }}</span></div>
              <div v-else
                   style="max-width:85%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.6;white-space:pre-wrap"
                   :style="{
                      background: m.sender === 1 ? 'var(--gray-light)' : 'var(--rose-pale)',
                      justifySelf: m.sender === 1 ? 'start' : 'end',
                    }">
                <div>{{ m.content }}</div>
                <div style="font-size:10.5px;color:var(--gray);margin-top:4px">{{ dt(m.created_at) }}</div>
              </div>
            </template>
            <div v-if="!(thread.messages || []).length && !thread.loadErr" class="empty-line" style="text-align:center">（无消息记录）</div>
            <div v-if="thread.loadErr" style="text-align:center;padding:10px 0">
              <div style="color:var(--error);font-size:13px;margin-bottom:8px">对话加载失败</div>
              <button class="btn btn-secondary btn-sm" @click="openTicket(active)">重试</button>
            </div>
          </template>
        </div>

        <div v-if="!isClosed">
          <div class="dtitle" style="margin-bottom:10px">回复工单</div>
          <div style="display:flex;gap:8px;margin-bottom:10px;align-items:center">
            <select class="input" style="height:34px;font-size:12.5px;flex:1" @focus="loadTemplates" @change="applyTemplate">
              <option value="">{{ tplLabel }}</option>
              <option v-for="t in tplOptions" :key="t.id" :value="t.id">{{ t.title }}</option>
            </select>
            <button class="btn btn-secondary btn-sm" style="height:34px" :disabled="busy" title="指派给当前登录管理员" @click="assignMe">指派给我</button>
            <select class="input" style="height:34px;font-size:12.5px;flex:1;min-width:130px" title="指派给其他管理员" :value="active.assignee_admin_id || ''" @change="assignTo($event.target.value)">
              <option value="" disabled>指派给…</option>
              <option v-for="a in admins" :key="a.id" :value="a.id">{{ a.name }} {{ (a.email || '').split('@')[0] }}{{ a.id === active.assignee_admin_id ? '（当前）' : '' }}</option>
            </select>
          </div>
          <textarea v-model="reply" class="input" rows="3" maxlength="2000" placeholder="输入回复…（Ctrl+Enter 发送）" style="margin-bottom:10px" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send"></textarea>
          <div v-if="reply.length >= 1800" style="font-size:11px;color:var(--gray);text-align:right;margin:-6px 0 8px">还可输入 {{ 2000 - reply.length }} 字</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn btn-primary" style="flex:1" :class="{ loading: busy }" :disabled="busy || !reply.trim()" @click="send">发送回复</button>
            <template v-if="active.status === 1">
              <button class="btn btn-secondary" :disabled="busy" title="处理中 → 等待客户（1→2）" @click="setStatus(2)">等待客户</button>
              <button class="btn btn-secondary" :disabled="busy" title="处理中 → 已解决（1→3）" @click="setStatus(3)">标记解决</button>
            </template>
            <button v-else-if="active.status === 2" class="btn btn-secondary" :disabled="busy" title="等待客户 → 已解决（2→3）" @click="setStatus(3)">标记解决</button>
            <button v-else-if="isResolved" class="btn btn-secondary" :disabled="busy" title="已解决 → 处理中（3→1）" @click="reopen">重新打开</button>
            <button class="btn btn-ghost" style="color:var(--error)" :disabled="busy" :title="isResolved ? '已解决 → 确认关闭（3→4）' : '关闭后可随时重新打开'" @click="openClose">{{ isResolved ? '确认关闭' : '关闭' }}</button>
          </div>
        </div>
        <div v-else style="padding:12px 14px;background:var(--gray-light);border-radius:10px;font-size:12.5px;color:var(--gray);text-align:center">
          🔒 工单已关闭<span v-if="active.closed_at"> · {{ dt(active.closed_at) }}</span>，不再接受回复
          <button class="btn btn-secondary btn-sm" style="margin-left:8px" :disabled="busy" title="已关闭 → 处理中（4→1）" @click="reopen">重新打开</button>
        </div>
      </template>
    </div>
  </div>

  <!-- 关闭工单确认：ConfirmDialog danger + 关闭原因必填（随 close_reason 提交到专用关单端点） -->
  <ConfirmDialog
    :open="closeDlg"
    title="关闭工单"
    :body="`关闭 ${active?.ticket_no} 后客户将无法继续回复，关闭后可随时重新打开；如问题未解决请改用回复。`"
    confirm-text="确认关闭"
    danger
    reason-label="关闭原因"
    reason-placeholder="必填，如：已解决 / 重复工单 / 无效工单"
    :busy="busy"
    @confirm="doClose"
    @close="closeDlg = false"
  />
</template>

<style scoped>
/* 刷新失败横幅：pale-error 底 + error 字，圆角，卡内顶部 */
.err-banner{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 14px;margin:12px 12px 0;background:var(--pale-error);color:var(--error);border-radius:10px;font-size:12.5px}
/* 订单号深链：plum 色 hover 下划线 */
.ono{color:var(--ink);text-decoration:none}
.ono:hover{color:var(--plum);text-decoration:underline}
/* 系统消息（sender=3）：居中灰色小条 */
.sysmsg{justify-self:center;max-width:90%;text-align:center;background:var(--gray-light);color:var(--gray);font-size:11.5px;line-height:1.5;padding:4px 12px;border-radius:999px;white-space:pre-wrap;word-break:break-all}
.sysmsg-time{margin-left:6px;font-size:10.5px;opacity:.85}
/* 最后消息（并入状态列）：客户新回复蓝色小 tag / 其余灰色时间小字 */
.lm-tag{margin-left:4px;font-size:10px;cursor:help}
.lm-time{font-size:10.5px;color:var(--gray);margin-top:2px;white-space:nowrap}
</style>
