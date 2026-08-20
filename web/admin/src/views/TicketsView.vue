<script setup>
import { computed, onMounted, ref } from 'vue'
import { API_BASE, req } from '../api/client'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'

const session = useSessionStore()
const tickets = ref([])
const total = ref(0)
const page = ref(1)
const SIZE = 50
const loaded = ref(false)
const loadErr = ref(false)
const tab = ref('all')         /* all/new/processing/wait/closed */
const cat = ref('')            /* '' = 全部分类 */
const q = ref('')

const SSTATUS = { 0: ['新工单', 'tag-pending'], 1: ['处理中', 'tag-paid'], 2: ['等待客户', 'tag-pending'], 3: ['已解决', 'tag-done'], 4: ['已关闭', 'tag-done'] }
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

/* 仅 status===4（已关闭）锁定操作；3（已解决）保留「确认关闭」走 3→4 */
const isClosed = computed(() => !!active.value && active.value.status === 4)
const isResolved = computed(() => !!active.value && active.value.status === 3)
/* 响应含 total/page/size（无 pages），页数由 total 折算 */
const pages = computed(() => Math.max(1, Math.ceil(total.value / SIZE)))

function buildUrl(status, p) {
  const params = new URLSearchParams({ page: p, size: SIZE })
  if (status !== null && status !== undefined) params.set('status', status)
  if (cat.value !== '') params.set('category', cat.value)
  const s = q.value.trim()
  if (s) params.set('q', s)
  return '/api/admin/ops/tickets?' + params
}

async function load(p = 1) {
  loaded.value = false
  loadErr.value = false
  try {
    /* 已关 tab 由后端组合状态 status=3,4 单请求返回 */
    const st = TABS.find((t) => t[0] === tab.value)?.[2]
    const d = await req('GET', buildUrl(st, p))
    tickets.value = d.items || []
    total.value = d.total ?? 0
    page.value = p
  } catch (e) {
    loadErr.value = true
    toast('工单列表加载失败：' + (e.message || ''), 'error')
  }
  loaded.value = true
}
onMounted(() => load(1))

function setTab(k) { if (tab.value !== k) { tab.value = k; load(1) } }
function setCat(v) { cat.value = v; load(1) }
function search() { load(1) }
function go(d) { const n = page.value + d; if (n >= 1 && n <= pages.value) load(n) }

/* 快捷回复模板：GET /api/support/templates（公开端点，返回 [{id,category,title,content}]） */
const templates = ref([])
const templatesLoaded = ref(false)
async function loadTemplates() {
  if (templatesLoaded.value) return
  try {
    templates.value = (await req('GET', '/api/support/templates')) || []
    templatesLoaded.value = true
  } catch (_) { /* 下拉里提示加载失败，可重选再试 */ }
}
function applyTemplate(e) {
  const id = parseInt(e.target.value, 10)
  e.target.value = ''
  const t = templates.value.find((x) => x.id === id)
  if (!t) return
  reply.value = reply.value.trim() ? reply.value.trim() + '\n' + t.content : t.content
}

/* 工单线程走用户侧查询接口：omit credentials（匿名路径需 ticket_no+email，与后台会话无关）。
 * 拼 API_BASE：拆独立 API 域后不再依赖同源相对路径 */
async function openTicket(t) {
  active.value = t
  thread.value = null
  try {
    const r = await fetch(`${API_BASE}/api/support/tickets?email=${encodeURIComponent(t.email)}&ticket_no=${encodeURIComponent(t.ticket_no)}`, {
      credentials: 'omit',
    })
    if (!r.ok) throw new Error('HTTP ' + r.status)
    const d = await r.json()
    thread.value = d.items?.[0] || { messages: [] }
  } catch (e) {
    thread.value = { messages: [], loadErr: true }
    toast('对话加载失败：' + e.message, 'error')
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
async function close() {
  if (!confirm('关闭工单 ' + active.value.ticket_no + '？')) return
  try {
    const t = await req('POST', `/api/admin/ops/tickets/${active.value.ticket_no}/close`, { close_reason: 0 })
    toast('工单已关闭 ✓', 'success')
    Object.assign(active.value, t)
    load(page.value)
  } catch (e) {
    const d = e.data?.detail
    toast('关闭失败：' + (d === 'ticket_already_closed' ? '工单已是关闭状态，请刷新列表' : (d || e.message)), 'error')
  }
}
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
      <h1 style="font-size:22px">客服工单</h1>
      <span style="font-size:12.5px;color:var(--gray)">当前筛选共 {{ total }} 张工单</span>
    </div>
  </div>

  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:14px">
    <button v-for="[k, label] in TABS" :key="k" class="ttab" :class="{ on: tab === k }" @click="setTab(k)">{{ label }}</button>
    <span style="flex:1"></span>
    <select class="input" :value="cat" style="width:auto;height:36px;font-size:13px" @change="setCat($event.target.value)">
      <option value="">全部分类</option>
      <option v-for="(label, v) in CATEGORY" :key="v" :value="String(v)">{{ label }}</option>
    </select>
    <input v-model="q" class="input" style="width:200px;height:36px" placeholder="搜工单号 / 邮箱" @keydown.enter="search()">
    <button class="btn btn-secondary btn-sm" style="height:36px" @click="search()">搜索</button>
  </div>

  <div class="grid-2" style="align-items:start">
    <div class="card tbl-wrap">
      <table style="width:100%;min-width:560px;border-collapse:collapse;font-size:13px">
        <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">工单号</th><th>主题</th><th>客户</th><th>首次回复</th><th>状态</th></tr></thead>
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
            <td><span class="tag" :class="SSTATUS[t.status]?.[1]">{{ SSTATUS[t.status]?.[0] }}</span></td>
          </tr>
        </tbody>
      </table>
      <div v-if="loadErr" style="text-align:center;padding:28px 18px">
        <div style="font-size:24px;margin-bottom:6px">⚠️</div>
        <div style="color:var(--error);font-size:13px;margin-bottom:10px">工单列表加载失败</div>
        <button class="btn btn-secondary btn-sm" @click="load(1)">重试</button>
      </div>
      <div v-else-if="loaded && !tickets.length" style="text-align:center;color:var(--gray);padding:28px 0">暂无工单</div>
      <div v-if="pages > 1" style="display:flex;justify-content:space-between;align-items:center;padding:12px 10px;font-size:12.5px;color:var(--gray);border-top:1px solid var(--gray-light)">
        <span>第 {{ page }} / {{ pages }} 页 · 共 {{ total }} 张</span>
        <div style="display:flex;gap:8px">
          <button class="btn btn-secondary btn-sm" :disabled="page <= 1" :style="{ opacity: page <= 1 ? 0.45 : 1 }" @click="go(-1)">上一页</button>
          <button class="btn btn-secondary btn-sm" :disabled="page >= pages" :style="{ opacity: page >= pages ? 0.45 : 1 }" @click="go(1)">下一页</button>
        </div>
      </div>
    </div>

    <div class="card" style="padding:20px;position:sticky;top:16px">
      <div v-if="!active" style="text-align:center;color:var(--gray);padding:40px 0">← 选择一个工单查看对话</div>
      <template v-else>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap">
          <b style="font-size:14.5px">{{ active.ticket_no }}</b>
          <span class="tag" :class="SSTATUS[active.status]?.[1]">{{ SSTATUS[active.status]?.[0] }}</span>
        </div>
        <div style="font-size:12.5px;color:var(--gray);margin-bottom:12px">
          {{ active.subject }} · {{ active.email }}<span v-if="active.order_no"> · 订单 {{ active.order_no }}</span> · 创建 {{ fmtTime(active.created_at) }}
        </div>

        <div style="display:grid;gap:10px;max-height:320px;overflow-y:auto;margin-bottom:14px">
          <div v-if="!thread" style="color:var(--gray);font-size:13px;text-align:center;padding:20px 0">加载对话…</div>
          <template v-else>
            <div v-for="(m, i) in thread.messages || []" :key="i"
                 style="max-width:85%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.6;white-space:pre-wrap"
                 :class="m.sender === 1 ? '' : 'staff'"
                 :style="{
                    background: m.sender === 1 ? 'var(--gray-light)' : 'var(--rose-pale)',
                    justifySelf: m.sender === 1 ? 'start' : 'end',
                  }">
              <div>{{ m.content }}</div>
              <div style="font-size:10.5px;color:var(--gray);margin-top:4px">{{ fmtTime(m.created_at) }}<span v-if="m.sender === 3" style="margin-left:4px">· 系统</span></div>
            </div>
            <div v-if="!(thread.messages || []).length && !thread.loadErr" style="color:var(--gray);font-size:13px;text-align:center">（无消息记录）</div>
            <div v-if="thread.loadErr" style="text-align:center;padding:10px 0">
              <div style="color:var(--error);font-size:13px;margin-bottom:8px">对话加载失败</div>
              <button class="btn btn-secondary btn-sm" @click="openTicket(active)">重试</button>
            </div>
          </template>
        </div>

        <div v-if="!isClosed">
          <div style="display:flex;gap:8px;margin-bottom:10px;align-items:center">
            <select class="input" style="height:34px;font-size:12.5px;flex:1" @focus="loadTemplates" @change="applyTemplate">
              <option value="">{{ templatesLoaded ? (templates.length ? '快捷模板…' : '暂无模板') : '加载快捷模板…' }}</option>
              <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.title }}</option>
            </select>
            <button class="btn btn-secondary btn-sm" style="height:34px" title="指派给当前登录管理员" @click="assignMe">指派给我</button>
          </div>
          <textarea v-model="reply" class="input" rows="3" placeholder="输入回复…" style="margin-bottom:10px"></textarea>
          <div style="display:flex;gap:8px">
            <button class="btn btn-primary" style="flex:1" :class="{ loading: busy }" :disabled="busy" @click="send">发送回复</button>
            <button v-if="isResolved" class="btn btn-secondary" title="已解决 → 确认关闭（3→4）" @click="close">确认关闭</button>
            <button v-else class="btn btn-ghost" style="color:var(--error)" @click="close">关闭</button>
          </div>
          <p v-if="isResolved" style="font-size:11.5px;color:var(--gray);margin-top:8px">工单已解决但未关闭，点击「确认关闭」完成 3→4 流转（关闭后不再接受回复）。</p>
        </div>
        <div v-else style="padding:12px 14px;background:var(--gray-light);border-radius:10px;font-size:12.5px;color:var(--gray);text-align:center">
          🔒 工单已关闭<span v-if="active.closed_at"> · {{ fmtTime(active.closed_at) }}</span>，不再接受回复
        </div>
      </template>
    </div>
  </div>
</template>
