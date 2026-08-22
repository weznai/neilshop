<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const session = useSessionStore()
const tickets = ref([])
const total = ref(0)
const page = ref(1)
const SIZE = 50
const loaded = ref(false)
const loadErr = ref(false)
const errMsg = ref('')       /* 最近一次加载失败信息（空态 sub / 横幅文案） */
const cat = ref('')            /* '' = 全部分类 */
const mine = ref('')           /* '' = 全部；'1' = 我的工单（assignee=当前管理员 id） */

/* 筛选 URL 同步：tab/q/priority 回填与写回（priority '0'=仅紧急） */
const st = reactive({ tab: 'all', q: '', priority: '' })
useQuerySync(st, { defaults: { tab: 'all', priority: '' } })

/* 状态机：0 新工单 → 1 处理中（回复后）→ 2 等待客户 / 3 已解决 → 4 已关闭（带 close_reason） */
const SSTATUS = { 0: ['新工单', 'tag-pending'], 1: ['处理中', 'tag-ship'], 2: ['等待客户', 'tag-pending'], 3: ['已解决', 'tag-paid'], 4: ['已关闭', 'tag-done'] }
/* TicketCategory 1-6（core/enums.py）；priority 0=紧急 1=普通（models/support.py，列表按紧急在前排序） */
const CATEGORY = { 1: '物流', 2: '质量', 3: '退换', 4: '账户', 5: '售前', 6: '其他' }
const TABS = [
  ['all', '全部', null],
  ['new', '新工单', 0],
  ['processing', '处理中', 1],
  ['wait', '等待客户', 2],
  ['closed', '已关', '3,4'],
]
/* CloseReason 枚举：1 解决 / 2 重复 / 3 无效 / 9 其他（status=4 时必传数字） */
const CLOSE_REASON = [[1, '已解决'], [2, '重复工单'], [3, '无效工单'], [9, '其他']]

const active = ref(null)      /* 列表行 */
const thread = ref(null)      /* {messages: [{sender, content, created_at}]} */
const reply = ref('')
const busy = ref(false)
const closeDlg = ref(false)
const closeReason = ref(1)
const closeBusy = ref(false)

/* 仅 status===4（已关闭）锁定操作；1 可转等待客户/已解决，3 走「确认关闭」3→4 */
const isClosed = computed(() => !!active.value && active.value.status === 4)
const isResolved = computed(() => !!active.value && active.value.status === 3)
/* 响应含 total/page/size（无 pages），页数由 total 折算 */
const pages = computed(() => Math.max(1, Math.ceil(total.value / SIZE)))

function buildUrl(status, p) {
  const params = new URLSearchParams({ page: p, size: SIZE })
  if (status !== null && status !== undefined) params.set('status', status)
  if (cat.value !== '') params.set('category', cat.value)
  if (st.priority !== '') params.set('priority', st.priority)
  if (mine.value === '1' && session.user?.id) params.set('assignee', session.user.id)
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
    page.value = p
  } catch (e) {
    loadErr.value = true
    errMsg.value = e.message || ''
    toast('工单列表加载失败：' + (e.message || ''), 'error')
  }
  loaded.value = true
}
onMounted(() => load(1))

function setTab(k) { if (st.tab !== k) { st.tab = k; load(1) } }
function setCat(v) { cat.value = v; load(1) }
function setMine(v) { mine.value = v; load(1) }
function togglePriority() { st.priority = st.priority === '0' ? '' : '0'; load(1) }
function search() { load(1) }
/* 列表空态文案：任一筛选（tab/仅紧急/分类/我的/搜索）生效→未匹配，否则暂无 */
const filtered = computed(() => st.tab !== 'all' || st.priority !== '' || cat.value !== '' || mine.value !== '' || st.q.trim() !== '')

/* 快捷回复模板：GET /api/support/templates（公开端点，支持 ?category= 过滤，返回 [{id,category,title,content}]） */
const templates = ref([])          /* 全量模板（当前工单分类无匹配时兜底显示） */
const templatesLoaded = ref(false)
const catTpl = ref(null)           /* { cat, items } 当前工单分类的模板缓存 */
async function loadTemplates() {
  if (templatesLoaded.value) return
  try {
    templates.value = (await req('GET', '/api/support/templates')) || []
    templatesLoaded.value = true
  } catch (_) { /* 下拉里提示加载失败，可重选再试 */ }
}
/* 打开线程时按当前工单分类带参拉取；返回项含 category 字段，二次过滤兜底 */
async function loadCatTemplates(cat) {
  if (catTpl.value?.cat === cat) return
  try {
    const items = (await req('GET', '/api/support/templates?category=' + cat)) || []
    catTpl.value = { cat, items: items.filter((x) => x.category === cat) }
  } catch (_) { catTpl.value = { cat, items: [] } }   /* 失败置空，下拉回退全量 */
}
/* 下拉数据源：当前工单分类模板优先，无匹配回退全量 */
const tplOptions = computed(() => {
  const c = active.value?.category
  if (c && catTpl.value?.cat === c && catTpl.value.items.length) return catTpl.value.items
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
  active.value = t
  thread.value = null
  if (t.category) loadCatTemplates(t.category)   /* 预取该分类快捷模板（不阻塞线程加载） */
  try {
    const d = await req('GET', `/api/support/tickets?email=${encodeURIComponent(t.email)}&ticket_no=${encodeURIComponent(t.ticket_no)}`, undefined, { credentials: 'omit' })
    thread.value = d.items?.[0] || { messages: [] }
  } catch (e) {
    thread.value = { messages: [], loadErr: true }
    toast('对话加载失败：' + (e.message || ''), 'error')
  }
}

async function send() {
  if (!reply.value.trim() || !active.value) return
  busy.value = true
  try {
    const t = await req('POST', `/api/admin/ops/tickets/${active.value.ticket_no}/reply`, { content: reply.value })
    reply.value = ''
    toast('回复已发送 ✓', 'success')
    Object.assign(active.value, t)   /* 同步右侧面板状态（0→1 处理中） */
    await openTicket(active.value)
    load(page.value)
  } catch (e) { toast('回复失败：' + (e.data?.detail || e.message), 'error') }
  finally { busy.value = false }
}

/* 状态流转：PUT /api/admin/support/tickets/{no}/status（2 等待客户 / 3 已解决） */
async function setStatus(status) {
  busy.value = true
  try {
    const t = await req('PUT', `/api/admin/support/tickets/${active.value.ticket_no}/status`, { status })
    toast(status === 2 ? '已标记等待客户 ✓' : '已标记解决 ✓', 'success')
    Object.assign(active.value, t)
    load(page.value)
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
  finally { busy.value = false }
}

/* 关闭（status=4）：ConfirmDialog 仅支持文本原因，此处按其同构样式内联弹窗 + 原因下拉 */
function openClose() { closeReason.value = 1; closeDlg.value = true }
async function doClose() {
  closeBusy.value = true
  try {
    const t = await req('PUT', `/api/admin/support/tickets/${active.value.ticket_no}/status`, { status: 4, close_reason: Number(closeReason.value) })
    toast('工单已关闭 ✓', 'success')
    Object.assign(active.value, t)
    closeDlg.value = false
    load(page.value)
  } catch (e) { toast('关闭失败：' + (e.data?.detail || e.message), 'error') }
  finally { closeBusy.value = false }
}

/* 指派展示：优先 assignee_name（列表/详情新增），否则「#id」兜底 */
const assigneeText = (t) => t.assignee_admin_id
  ? (t.assignee_name || `#${t.assignee_admin_id}`)
  : '未指派'
/* 指派给我：AssignIn 需 admin_id（取当前登录管理员 id） */
async function assignMe() {
  const adminId = session.user?.id
  if (!adminId) { toast('无法获取当前管理员 ID，请刷新页面重试', 'error'); return }
  try {
    const t = await req('POST', `/api/admin/ops/tickets/${active.value.ticket_no}/assign`, { admin_id: adminId })
    Object.assign(active.value, t)
    toast('已指派给你 ✓', 'success')
    load(page.value)
  } catch (e) { toast('指派失败：' + (e.data?.detail || e.message), 'error') }
}
const fmtTime = (iso) => (iso || '').slice(0, 16).replace('T', ' ')
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">客服工单</h1>
      <span class="page-sub">当前筛选共 {{ total }} 张工单</span>
    </div>
  </div>

  <div class="filter-bar" style="margin-bottom:14px">
    <button v-for="[k, label] in TABS" :key="k" class="ttab" :class="{ on: st.tab === k }" @click="setTab(k)">{{ label }}</button>
    <span style="flex:1"></span>
    <button class="ttab" :class="{ on: st.priority === '0' }" title="只看紧急工单（priority=0）" @click="togglePriority">仅紧急</button>
    <select class="input" :value="cat" style="width:auto;height:38px;font-size:13px" @change="setCat($event.target.value)">
      <option value="">全部分类</option>
      <option v-for="(label, v) in CATEGORY" :key="v" :value="String(v)">{{ label }}</option>
    </select>
    <select class="input" :value="mine" style="width:auto;height:38px;font-size:13px" @change="setMine($event.target.value)">
      <option value="">全部工单</option>
      <option value="1">我的工单</option>
    </select>
    <input v-model="st.q" class="input" style="width:200px;height:38px" placeholder="邮箱 / 工单号 / 主题" @keydown.enter="search()">
    <button class="btn btn-secondary btn-sm" style="height:38px" @click="search()">搜索</button>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px;margin-bottom:14px" />

  <!-- 首屏失败（无旧数据）：错误空态置顶，隐藏列表 -->
  <EmptyState v-else-if="loadErr && !tickets.length" icon="⚠️" title="工单列表加载失败" :sub="errMsg || '服务端可能未启动或会话已过期'">
    <template #action><button class="btn btn-secondary btn-sm" @click="load(page)">重试</button></template>
  </EmptyState>

  <div v-else class="grid-2" style="align-items:start">
    <div class="card tbl-wrap">
      <!-- 刷新失败（有旧数据）：卡内顶部横幅，旧数据保留 -->
      <div v-if="loadErr" class="err-banner">
        <span>⚠️ 刷新失败：{{ errMsg || '网络异常，下方为旧数据' }}</span>
        <button class="btn btn-secondary btn-sm" @click="load(page)">重试</button>
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
            <td>{{ (t.email || '').split('@')[0] }}</td>
            <td>
              <span v-if="t.first_reply_at" class="tag tag-done">✓</span>
              <span v-else class="tag tag-pending">待回复</span>
            </td>
            <td>
              <span v-if="t.assignee_admin_id" class="tag tag-ship" :title="'#' + t.assignee_admin_id">{{ assigneeText(t) }}</span>
              <span v-else class="tag tag-pending">未指派</span>
            </td>
            <td><span class="tag" :class="SSTATUS[t.status]?.[1]">{{ SSTATUS[t.status]?.[0] }}</span></td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!tickets.length" :icon="filtered ? '🔍' : '💬'" :title="filtered ? '未找到匹配的工单' : '暂无工单'" :sub="filtered ? '试试调整或清除筛选' : '客户提交工单后将显示在这里'" />
      <Pagination embed :page="page" :pages="pages" :total="total" unit="张" @go="load" />
    </div>

    <div class="card" style="padding:20px;position:sticky;top:16px">
      <EmptyState v-if="!active" icon="👈" title="选择一个工单查看对话" sub="点击左侧列表中的工单号或主题" />
      <template v-else>
        <div class="dhead">
          <div class="dtitle">{{ active.ticket_no }}</div>
          <span class="tag" :class="SSTATUS[active.status]?.[1]">{{ SSTATUS[active.status]?.[0] }}</span>
        </div>
        <div class="page-sub" style="margin-bottom:12px">
          {{ active.subject }} · {{ active.email }}<span v-if="active.order_no"> · 订单 {{ active.order_no }}</span> · 创建 {{ fmtTime(active.created_at) }}
          <span v-if="active.assignee_admin_id"> · {{ assigneeText(active) }}</span>
        </div>

        <div class="dhead" style="margin-bottom:6px">
          <div class="dtitle">对话记录</div>
          <span v-if="thread" class="item-cnt">{{ (thread.messages || []).length }} 条</span>
        </div>
        <div style="display:grid;gap:10px;max-height:320px;overflow-y:auto;margin-bottom:14px">
          <div v-if="!thread" style="color:var(--gray);font-size:13px;text-align:center;padding:20px 0">加载对话…</div>
          <template v-else>
            <div v-for="(m, i) in thread.messages || []" :key="i"
                 style="max-width:85%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.6;white-space:pre-wrap"
                 :style="{
                    background: m.sender === 1 ? 'var(--gray-light)' : 'var(--rose-pale)',
                    justifySelf: m.sender === 1 ? 'start' : 'end',
                  }">
              <div>{{ m.content }}</div>
              <div style="font-size:10.5px;color:var(--gray);margin-top:4px">{{ fmtTime(m.created_at) }}<span v-if="m.sender === 3" style="margin-left:4px">· 系统</span></div>
            </div>
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
            <button class="btn btn-secondary btn-sm" style="height:34px" title="指派给当前登录管理员" @click="assignMe">指派给我</button>
          </div>
          <textarea v-model="reply" class="input" rows="3" placeholder="输入回复…（Ctrl+Enter 发送）" style="margin-bottom:10px" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send"></textarea>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn btn-primary" style="flex:1" :class="{ loading: busy }" :disabled="busy" @click="send">发送回复</button>
            <template v-if="active.status === 1">
              <button class="btn btn-secondary" :disabled="busy" title="处理中 → 等待客户（1→2）" @click="setStatus(2)">等待客户</button>
              <button class="btn btn-secondary" :disabled="busy" title="处理中 → 已解决（1→3）" @click="setStatus(3)">标记解决</button>
            </template>
            <button class="btn btn-ghost" style="color:var(--error)" :title="isResolved ? '已解决 → 确认关闭（3→4）' : '关闭后不可重开'" @click="openClose">{{ isResolved ? '确认关闭' : '关闭' }}</button>
          </div>
        </div>
        <div v-else style="padding:12px 14px;background:var(--gray-light);border-radius:10px;font-size:12.5px;color:var(--gray);text-align:center">
          🔒 工单已关闭<span v-if="active.closed_at"> · {{ fmtTime(active.closed_at) }}</span>，不再接受回复
        </div>
      </template>
    </div>
  </div>

  <!-- 关闭工单弹窗：危险确认 + 关闭原因下拉（随 close_reason 数字提交，status=4） -->
  <div class="modal" :class="{ open: closeDlg }" @click.self="!closeBusy && (closeDlg = false)">
    <div class="modal-box" style="max-width:420px">
      <button class="modal-x" :disabled="closeBusy" @click="closeDlg = false">×</button>
      <h3 style="font-family:var(--font-title);font-size:17px;font-weight:700;margin-bottom:8px">关闭工单 {{ active?.ticket_no }}</h3>
      <p style="color:var(--gray);font-size:13px;line-height:1.6;white-space:pre-line">关闭后客户将无法继续回复，工单不可重新打开；如问题未解决请改用回复。</p>
      <div class="field" style="margin:14px 0 2px">
        <label>关闭原因</label>
        <select v-model.number="closeReason" class="input" :disabled="closeBusy">
          <option v-for="[v, label] in CLOSE_REASON" :key="v" :value="v">{{ label }}</option>
        </select>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:20px">
        <button class="btn btn-secondary btn-sm" :disabled="closeBusy" @click="closeDlg = false">取消</button>
        <button class="btn btn-sm" style="background:var(--error);color:#fff" :disabled="closeBusy" @click="doClose">{{ closeBusy ? '处理中…' : '确认关闭' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 刷新失败横幅：pale-error 底 + error 字，圆角，卡内顶部 */
.err-banner{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 14px;margin:12px 12px 0;background:var(--pale-error);color:var(--error);border-radius:10px;font-size:12.5px}
</style>
