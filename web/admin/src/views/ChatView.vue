<script setup>
/* 在线客服聊天工作台：三渠道会话列表 + 实时对话（4s 轮询）+ 快捷模板回复 + 接单/关闭
 * 渠道 0 AI / 1 人工 / 2 美甲师；美甲师账号（role=4）默认锁定「我的会话」 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'
import { dt } from '../composables/format'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const session = useSessionStore()
const isArtist = computed(() => session.role === 4)

const items = ref([])
const total = ref(0)
const SIZE = 30
const loaded = ref(false)
const loadErr = ref(false)
const errMsg = ref('')

/* 筛选 URL 同步：channel(all/0/1/2) / status(0 进行中 1 已关闭) / mine / q / page */
const st = reactive({ channel: 'all', status: '0', q: '', mine: '', page: 1 })
useQuerySync(st, { nums: ['page'], defaults: { channel: 'all', status: '0', q: '', mine: '', page: 1 } })
if (isArtist.value) st.mine = '1' /* 美甲师只看自己的会话（不可解除） */

const CHANNEL = { 0: 'AI', 1: '人工', 2: '美甲师' }
const CHANNEL_TAG = { 0: 'tag-cat', 1: 'tag-ship', 2: 'tag-done' }
const TABS = [
  ['all', '全部', null],
  ['1', '人工', 1],
  ['2', '美甲师', 2],
  ['0', 'AI', 0],
]

const active = ref(null) /* 会话详情（含 messages） */
const reply = ref('')
const busy = ref(false)
const threadBox = ref(null)
const pages = computed(() => Math.max(1, Math.ceil(total.value / SIZE)))

function buildUrl(p) {
  const params = new URLSearchParams({ page: p, size: SIZE })
  const ch = TABS.find((t) => t[0] === st.channel)?.[2]
  if (ch !== null && ch !== undefined) params.set('channel', ch)
  if (st.status !== '') params.set('status', st.status)
  if (st.mine === '1' && session.user?.id) params.set('mine', 1)
  const s = st.q.trim()
  if (s) params.set('q', s)
  return '/api/admin/chat/conversations?' + params
}

async function load(p = 1) {
  loadErr.value = false
  errMsg.value = ''
  try {
    const d = await req('GET', buildUrl(p))
    items.value = d.items || []
    total.value = d.total ?? 0
    st.page = p
  } catch (e) {
    loadErr.value = true
    errMsg.value = e.message || ''
    toast('会话列表加载失败：' + (e.message || ''), 'error')
  }
  loaded.value = true
}

async function openConv(row) {
  active.value = { ...row, messages: [] }
  await refreshActive(true)
  scrollThread()
}

async function refreshActive(quiet) {
  if (!active.value) return
  try {
    const d = await req('GET', '/api/admin/chat/conversations/' + active.value.conv_no)
    const prevCount = (active.value.messages || []).length
    active.value = d
    if ((d.messages || []).length !== prevCount) nextTick(scrollThread)
  } catch (e) {
    if (!quiet) toast('对话加载失败：' + (e.message || ''), 'error')
  }
}

function scrollThread() {
  nextTick(() => { if (threadBox.value) threadBox.value.scrollTop = threadBox.value.scrollHeight })
}

function setTab(k) { if (st.channel !== k) { st.channel = k; load(1) } }
function setStatus(v) { if (st.status !== v) { st.status = v; load(1) } }
function search() { load(1) }
const filtered = computed(() => st.channel !== 'all' || st.status !== '0' || st.mine !== '' || st.q.trim() !== '')

/* ===== 快捷回复模板（复用工单域 reply_templates，公开端点） ===== */
const templates = ref([])
const templatesLoaded = ref(false)
async function loadTemplates() {
  if (templatesLoaded.value) return
  try { templates.value = (await req('GET', '/api/support/templates')) || []; templatesLoaded.value = true } catch (_) { /* 重选再试 */ }
}
function applyTemplate(e) {
  const id = parseInt(e.target.value, 10)
  e.target.value = ''
  const t = templates.value.find((x) => x.id === id)
  if (!t) return
  reply.value = reply.value.trim() ? reply.value.trim() + '\n' + t.content : t.content
}

/* ===== 操作 ===== */
async function send() {
  if (!reply.value.trim() || !active.value || busy.value) return
  busy.value = true
  try {
    const d = await req('POST', `/api/admin/chat/conversations/${active.value.conv_no}/reply`, { content: reply.value })
    active.value = d
    reply.value = ''
    scrollThread()
    load(st.page)
  } catch (e) { toast('发送失败：' + (e.data?.detail || e.message), 'error') }
  finally { busy.value = false }
}

async function take() {
  if (busy.value || !active.value) return
  busy.value = true
  try {
    active.value = await req('POST', `/api/admin/chat/conversations/${active.value.conv_no}/take`)
    toast('已接单 ✓', 'success')
    load(st.page)
  } catch (e) { toast('接单失败：' + (e.data?.detail || e.message), 'error') }
  finally { busy.value = false }
}

/* 人工 → AI 内部切换：同一会话交还 GlowBot 自动应答（客户侧系统提示可见） */
async function resumeAi() {
  if (busy.value || !active.value) return
  busy.value = true
  try {
    active.value = await req('POST', `/api/admin/chat/conversations/${active.value.conv_no}/resume-ai`)
    toast('已转回 AI 自动回复 ✓', 'success')
    load(st.page)
  } catch (e) { toast('转回 AI 失败：' + (e.data?.detail || e.message), 'error') }
  finally { busy.value = false }
}

async function closeConv() {
  if (busy.value || !active.value) return
  busy.value = true
  try {
    active.value = await req('POST', `/api/admin/chat/conversations/${active.value.conv_no}/close`)
    toast('会话已关闭 ✓', 'success')
    load(st.page)
  } catch (e) { toast('关闭失败：' + (e.data?.detail || e.message), 'error') }
  finally { busy.value = false }
}

/* 客户名展示：name 优先，否则邮箱前缀 */
const who = (c) => c.name || (c.email || '').split('@')[0] || '游客'

/* ===== 4s 轮询：列表红点 + 当前会话新消息（页面可见时） ===== */
let timer = null
onMounted(() => {
  load(1)
  timer = setInterval(() => {
    if (document.visibilityState === 'visible') { load(st.page); refreshActive(true) }
  }, 4000)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })

const isOpen = computed(() => !!active.value && active.value.status === 0)
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">在线客服</h1>
      <span class="page-sub">当前筛选共 {{ total }} 个会话 · 4 秒自动刷新</span>
    </div>
  </div>

  <div class="filter-bar" style="margin-bottom:14px">
    <button v-for="[k, label] in TABS" :key="k" class="ttab" :class="{ on: st.channel === k }" @click="setTab(k)">{{ label }}</button>
    <span style="flex:1"></span>
    <button class="ttab" :class="{ on: st.status === '0' }" @click="setStatus('0')">进行中</button>
    <button class="ttab" :class="{ on: st.status === '1' }" @click="setStatus('1')">已关闭</button>
    <select v-if="!isArtist" class="input" :value="st.mine" style="width:auto;height:38px;font-size:13px" @change="st.mine = $event.target.value; load(1)">
      <option value="">全部会话</option>
      <option value="1">我的会话</option>
    </select>
    <input v-model="st.q" class="input" style="width:200px;height:38px" placeholder="会话号 / 邮箱 / 姓名" @keydown.enter="search()">
    <button class="btn btn-secondary btn-sm" style="height:38px" @click="search()">搜索</button>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px" />

  <EmptyState v-else-if="loadErr && !items.length" icon="⚠️" title="会话列表加载失败" :sub="errMsg || '服务端可能未启动或会话已过期'">
    <template #action><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></template>
  </EmptyState>

  <div v-else class="chatws">
    <!-- 左：会话列表 -->
    <div class="card chatws-list">
      <div v-for="c in items" :key="c.conv_no" class="chatws-row" :class="{ on: active && active.conv_no === c.conv_no }" @click="openConv(c)">
        <div class="chatws-row-top">
          <span class="tag" :class="CHANNEL_TAG[c.channel]">{{ CHANNEL[c.channel] }}</span>
          <b class="chatws-who">{{ who(c) }}</b>
          <span v-if="c.pending_reply" class="chatws-dot" title="客户待回复">●</span>
          <span class="chatws-time">{{ dt(c.last_message_at) }}</span>
        </div>
        <div class="chatws-preview">
          <template v-if="c.last_message">{{ c.last_message.sender === 1 ? '' : '↩ ' }}{{ c.last_message.preview }}</template>
          <template v-else">（暂无消息）</template>
        </div>
        <div class="chatws-meta">
          <span class="chatws-no">{{ c.conv_no }}</span>
          <span v-if="c.status === 1" class="tag tag-pending">已关闭</span>
          <span v-else-if="c.channel === 1 && !c.agent_admin_id" class="tag tag-pending">待接入</span>
          <span v-else-if="c.channel === 1 && c.agent_name" class="tag tag-done">{{ c.agent_name }}</span>
          <span v-else-if="c.channel === 2 && c.artist_name" class="tag tag-done">💅 {{ c.artist_name }}</span>
        </div>
      </div>
      <EmptyState v-if="!items.length" :icon="filtered ? '🔍' : '💬'" :title="filtered ? '未找到匹配的会话' : '暂无会话'" :sub="filtered ? '试试调整或清除筛选' : '客户发起聊天后将显示在这里'" />
      <Pagination embed :page="st.page" :pages="pages" :total="total" unit="个" @go="load" />
    </div>

    <!-- 右：对话窗 -->
    <div class="card chatws-pane">
      <EmptyState v-if="!active" icon="👈" title="选择一个会话开始服务" sub="点击左侧会话查看完整对话" />
      <template v-else>
        <div class="chatws-head">
          <div>
            <div class="dtitle">{{ active.conv_no }}
              <span class="tag" :class="CHANNEL_TAG[active.channel]" style="margin-left:6px">{{ CHANNEL[active.channel] }}</span>
              <span v-if="active.status === 1" class="tag tag-pending" style="margin-left:4px">已关闭</span>
            </div>
            <div class="page-sub" style="margin-top:4px">
              {{ active.name || '游客' }}<template v-if="active.email"> · {{ active.email }}</template>
              <template v-if="active.channel === 2 && active.artist_name"> · 美甲师 {{ active.artist_name }}</template>
              <template v-if="active.channel === 1 && active.agent_name"> · 客服 {{ active.agent_name }}</template>
              · {{ dt(active.created_at) }}
            </div>
          </div>
          <div v-if="isOpen" style="display:flex;gap:8px">
            <button v-if="active.channel === 1 && active.agent_admin_id !== session.user?.id" class="btn btn-secondary btn-sm" :disabled="busy" @click="take">接单</button>
            <button v-if="active.channel === 1" class="btn btn-secondary btn-sm" :disabled="busy" title="人工 → AI（同一会话交还 GlowBot 自动应答）" @click="resumeAi">转回 AI</button>
            <button class="btn btn-ghost btn-sm" style="color:var(--error)" :disabled="busy" @click="closeConv">关闭会话</button>
          </div>
        </div>

        <div class="chatws-thread" ref="threadBox">
          <template v-for="m in active.messages || []" :key="m.id">
            <div v-if="m.sender === 3" class="chatws-sys">{{ m.content }}<span class="chatws-sys-t">{{ dt(m.created_at) }}</span></div>
            <div v-else class="chatws-msg" :class="{ me: m.sender !== 1 }">
              <div class="chatws-bubble">
                <div v-if="m.sender !== 1 && m.sender_name" class="chatws-who-line">{{ m.sender === 5 ? '💅 ' + m.sender_name : m.sender === 4 ? '🤖 ' + m.sender_name : '👩‍💼 ' + m.sender_name }}</div>
                <div class="chatws-text">{{ m.content }}</div>
                <div class="chatws-t">{{ dt(m.created_at) }}</div>
              </div>
            </div>
          </template>
          <div v-if="!(active.messages || []).length" class="empty-line" style="text-align:center">（无消息记录）</div>
        </div>

        <div v-if="isOpen" class="chatws-reply">
          <div class="chatws-reply-bar">
            <select class="input" style="height:34px;font-size:12.5px;flex:1" @focus="loadTemplates" @change="applyTemplate">
              <option value="">{{ templatesLoaded ? (templates.length ? '快捷模板…' : '暂无模板') : '加载快捷模板…' }}</option>
              <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.title }}</option>
            </select>
            <span class="chatws-count">{{ (active.messages || []).length }} 条</span>
          </div>
          <textarea v-model="reply" class="input" rows="3" placeholder="输入回复…（Ctrl+Enter 发送）" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send" />
          <button class="btn btn-primary" style="margin-top:10px;width:100%" :class="{ loading: busy }" :disabled="busy || !reply.trim()" @click="send">发送回复</button>
        </div>
        <div v-else class="chatws-closed">🔒 会话已关闭，不再接受回复</div>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* 工作台双栏：左列表 380px + 右对话自适应；高度铺满视口（减去顶栏/筛选） */
.chatws{display:grid;grid-template-columns:380px 1fr;gap:16px;align-items:start}
.chatws-list{padding:6px 0}
.chatws-row{padding:11px 14px;border-bottom:1px solid var(--gray-light);cursor:pointer;transition:background .12s}
.chatws-row:hover{background:var(--row-hover)}
.chatws-row.on{background:var(--rose-pale);box-shadow:inset 3px 0 0 var(--plum)}
.chatws-row-top{display:flex;align-items:center;gap:8px}
.chatws-who{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chatws-dot{color:var(--error);font-size:10px}
.chatws-time{margin-left:auto;font-size:10.5px;color:var(--gray);white-space:nowrap}
.chatws-preview{font-size:12px;color:var(--gray);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chatws-meta{display:flex;align-items:center;gap:6px;margin-top:5px}
.chatws-no{font-size:10.5px;color:var(--gray)}
/* 右侧对话面板 */
.chatws-pane{padding:18px;display:flex;flex-direction:column;min-height:640px}
.chatws-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:12px}
.chatws-thread{flex:1;overflow-y:auto;max-height:calc(100vh - 430px);min-height:300px;display:flex;flex-direction:column;gap:10px;padding:12px;background:var(--bg-page);border-radius:12px}
.chatws-sys{justify-self:center;max-width:90%;text-align:center;background:#fff;color:var(--gray);font-size:11.5px;line-height:1.5;padding:4px 12px;border-radius:999px;border:1px dashed var(--gray-light)}
.chatws-sys-t{margin-left:6px;font-size:10.5px;opacity:.8}
.chatws-msg{display:flex;max-width:78%}
.chatws-msg.me{align-self:flex-end;justify-content:flex-end}
.chatws-bubble{background:#fff;border-radius:12px 12px 12px 4px;padding:10px 14px;font-size:13.5px;line-height:1.65;white-space:pre-wrap;word-break:break-word;box-shadow:var(--shadow-card)}
.chatws-msg.me .chatws-bubble{background:var(--rose-pale);border-radius:12px 12px 4px 12px}
.chatws-who-line{font-size:11px;font-weight:700;color:var(--plum);margin-bottom:3px}
.chatws-text{color:var(--ink)}
.chatws-t{font-size:10.5px;color:var(--gray);margin-top:5px;text-align:right}
.chatws-reply{margin-top:12px}
.chatws-reply-bar{display:flex;gap:8px;align-items:center;margin-bottom:8px}
.chatws-count{font-size:11.5px;color:var(--gray);white-space:nowrap}
.chatws-closed{margin-top:12px;padding:12px;background:var(--gray-light);border-radius:10px;font-size:12.5px;color:var(--gray);text-align:center}
@media (max-width:1080px){.chatws{grid-template-columns:1fr}}
</style>
