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

/* ===== 快捷回复模板（复用工单域 reply_templates） ===== */
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

/* ===== 模板管理弹窗（GET/POST/PUT/DELETE /api/admin/ops/templates） ===== */
const tplDlg = ref(false)
const tplList = ref([])
const tplBusy = ref(false)
const TPL_CATS = { 1: '物流', 2: '质量', 3: '退换', 4: '账户', 5: '售前', 6: '其他' }
const tplForm = reactive({ id: null, category: 1, title: '', content: '', active: 1 })
async function openTplDlg() {
  tplDlg.value = true
  await reloadTplList()
}
async function reloadTplList() {
  try { tplList.value = (await req('GET', '/api/admin/ops/templates')).items || [] } catch (e) { toast('模板加载失败：' + (e.message || ''), 'error') }
}
function newTpl() {
  Object.assign(tplForm, { id: null, category: 1, title: '', content: '', active: 1 })
}
function editTpl(t) {
  Object.assign(tplForm, { id: t.id, category: t.category, title: t.title, content: t.content, active: t.active })
}
async function saveTpl() {
  if (!tplForm.title.trim() || !tplForm.content.trim()) { toast('标题与内容必填', 'error'); return }
  tplBusy.value = true
  try {
    const body = { category: tplForm.category, title: tplForm.title.trim(), content: tplForm.content.trim(), active: tplForm.active }
    if (tplForm.id) await req('PUT', '/api/admin/ops/templates/' + tplForm.id, body)
    else await req('POST', '/api/admin/ops/templates', body)
    toast(tplForm.id ? '模板已保存 ✓' : '模板已新增 ✓', 'success')
    newTpl()
    await reloadTplList()
    templatesLoaded.value = false /* 下拉数据源刷新 */
    slashAllLoaded.value = false /* slash 菜单数据源同步刷新 */
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
  finally { tplBusy.value = false }
}
async function delTpl(t) {
  if (tplBusy.value) return
  tplBusy.value = true
  try {
    await req('DELETE', '/api/admin/ops/templates/' + t.id)
    toast('模板已删除 ✓', 'success')
    await reloadTplList()
    templatesLoaded.value = false
    slashAllLoaded.value = false /* slash 菜单数据源同步刷新 */
  } catch (e) { toast('删除失败：' + (e.data?.detail || e.message), 'error') }
  finally { tplBusy.value = false }
}

/* ===== Slash 快捷指令：回复框输入 / 弹出模板菜单（关键字过滤 · ↑↓ 选择 · Enter 插入） ===== */
const slashOpen = ref(false)
const slashItems = ref([])   /* 当前过滤结果（≤8 条） */
const slashIdx = ref(0)
const slashAll = ref([])     /* 启用中的模板缓存（含分类） */
const slashAllLoaded = ref(false)
let slashStart = -1          /* 当前 /token 起始下标（替换用） */

async function ensureSlashAll() {
  if (slashAllLoaded.value) return
  try {
    const d = await req('GET', '/api/admin/ops/templates')
    slashAll.value = (d.items || []).filter((t) => t.active)
    slashAllLoaded.value = true
  } catch (_) { slashAll.value = [] }
}

/* 光标处 / 指令 token 探测：行首或空白后的 `/关键字`（关键字 ≤20 字符） */
function matchSlashToken() {
  return reply.value.match(/(?:^|\s)\/([^\s/]{0,20})$/)
}

async function onReplyInput() {
  const m = matchSlashToken()
  if (!m) { slashOpen.value = false; return }
  await ensureSlashAll()
  slashStart = reply.value.length - m[1].length - 1 /* '/' 位置 */
  const q = m[1].toLowerCase()
  slashItems.value = slashAll.value
    .filter((t) => !q || t.title.toLowerCase().includes(q) || t.content.toLowerCase().includes(q))
    .slice(0, 8)
  slashIdx.value = 0
  slashOpen.value = slashItems.value.length > 0
}

function applySlash(t) {
  /* 用模板内容替换光标前的 /token（保留 token 前的正文与换行） */
  reply.value = reply.value.slice(0, slashStart) + t.content
  slashOpen.value = false
}

function onReplyKeydown(e) {
  if (!slashOpen.value) return
  if (e.key === 'ArrowDown') { e.preventDefault(); slashIdx.value = (slashIdx.value + 1) % slashItems.value.length }
  else if (e.key === 'ArrowUp') { e.preventDefault(); slashIdx.value = (slashIdx.value - 1 + slashItems.value.length) % slashItems.value.length }
  else if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) { e.preventDefault(); applySlash(slashItems.value[slashIdx.value]) }
  else if (e.key === 'Escape') { slashOpen.value = false }
}
function onReplyBlur() { slashOpen.value = false }

/* ===== 客户快捷问题配置（settings key=chat_quick_replies，前台聊天窗 chips 数据源） =====
 * 结构化卡片编辑：每条 = 文案(≤40字) + 动作(ask 提问/link 跳转/human 转人工 + url)
 * + 增删排序 + 字数即时校验 + 手机预览 + 恢复默认 + dirty 拦截 + 审计展示 */
const quickDlg = ref(false)
const quickBusy = ref(false)
const quickLang = ref('zh')
const quickLists = reactive({ zh: [], en: [] })
const quickMeta = reactive({ customized: false, updated_by: null, updated_at: null })
const QUICK_LIMIT = 6
const QUICK_CHARS = 40
const ACTION_OPTS = [
  ['ask', '💬 提问', '点击发送文案给 AI'],
  ['link', '🔗 跳转', '打开站内页面（如 /returns-policy）'],
  ['human', '👩‍💼 转人工', '直接升级人工客服'],
]
const actionLabel = (a) => ACTION_OPTS.find((x) => x[0] === a)?.[1] || a

async function openQuickDlg() {
  quickDlg.value = true
  try {
    const d = await req('GET', '/api/admin/chat/quicks')
    quickLists.zh = cloneItems(d.items?.zh) || []
    quickLists.en = cloneItems(d.items?.en) || []
    Object.assign(quickMeta, { customized: !!d.customized, updated_by: d.updated_by || null, updated_at: d.updated_at || null })
    snapshotQuicks()
  } catch (e) {
    toast('配置加载失败：' + (e.message || ''), 'error')
  }
}
const cloneItems = (arr) => (arr || []).map((x) => ({ text: x.text || '', action: x.action || 'ask', url: x.url || '' }))
const curList = () => quickLists[quickLang.value]

function addQuick() {
  if (curList().length >= QUICK_LIMIT) { toast(`每语言最多 ${QUICK_LIMIT} 条`, 'error'); return }
  curList().push({ text: '', action: 'ask', url: '' })
}
function delQuick(i) { curList().splice(i, 1) }
function moveQuick(i, d) {
  const arr = curList()
  const j = i + d
  if (j < 0 || j >= arr.length) return
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}

/* dirty 判定基线：打开时快照（简单可靠，两语言合并比较） */
const savedSnap = reactive({ items: { zh: [], en: [] } })
function snapshotQuicks() { savedSnap.items = { zh: cloneItems(quickLists.zh), en: cloneItems(quickLists.en) } }
const isQuickDirty = computed(() => JSON.stringify({ zh: quickLists.zh, en: quickLists.en }) !== JSON.stringify(savedSnap.items))

const validItems = (arr) => arr.filter((x) => x.text.trim())

async function saveQuicks() {
  const zh = validItems(quickLists.zh).map(normItem)
  const en = validItems(quickLists.en).map(normItem)
  if (!zh.length && !en.length) { toast('至少配置一条有效快捷问题', 'error'); return }
  const over = [...quickLists.zh, ...quickLists.en].find((x) => x.text.length > QUICK_CHARS)
  if (over) { toast(`「${over.text.slice(0, 12)}…」超过 ${QUICK_CHARS} 字`, 'error'); return }
  const badLink = [...zh, ...en].find((x) => x.action === 'link' && !/^\/[^/]/.test(x.url))
  if (badLink) { toast(`「${badLink.text}」跳转地址需为站内路径（以 / 开头）`, 'error'); return }
  quickBusy.value = true
  try {
    await req('PUT', '/api/admin/chat/quicks', { zh, en })
    toast('已保存 ✓ 前台 5 分钟缓存过期后生效', 'success')
    snapshotQuicks()
    Object.assign(quickMeta, { customized: true, updated_by: session.name, updated_at: new Date().toISOString() })
  } catch (e) { toast('保存失败：' + (e.data?.detail || e.message), 'error') }
  finally { quickBusy.value = false }
}
const normItem = (x) => {
  const item = { text: x.text.trim().slice(0, QUICK_CHARS), action: x.action }
  if (x.action === 'link') item.url = x.url.trim()
  return item
}

async function resetQuicks() {
  if (quickBusy.value) return
  quickBusy.value = true
  try {
    const d = await req('POST', '/api/admin/chat/quicks/reset')
    quickLists.zh = cloneItems(d.zh)
    quickLists.en = cloneItems(d.en)
    snapshotQuicks()
    Object.assign(quickMeta, { customized: false, updated_by: null, updated_at: null })
    toast('已恢复默认 ✓', 'success')
  } catch (e) { toast('恢复失败：' + (e.data?.detail || e.message), 'error') }
  finally { quickBusy.value = false }
}
function closeQuickDlg() {
  if (isQuickDirty.value && !confirm('有未保存的修改，确定关闭？')) return
  quickDlg.value = false
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
    <div style="display:flex;gap:10px;align-items:center">
      <button class="btn btn-secondary" @click="openQuickDlg">⚡ 客户快捷问题</button>
      <button class="btn btn-secondary" @click="openTplDlg">🗂 快捷模板</button>
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
          <div class="chatws-input-wrap">
            <textarea v-model="reply" class="input" rows="3" placeholder="输入回复…（/ 调出快捷模板 · Ctrl+Enter 发送）" @input="onReplyInput" @blur="onReplyBlur" @keydown="onReplyKeydown" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send" />
            <!-- Slash 快捷指令菜单：浮于输入框上方 -->
            <div v-if="slashOpen" class="slash-menu">
              <button v-for="(t, i) in slashItems" :key="t.id" type="button" class="slash-item" :class="{ on: i === slashIdx }" @mousedown.prevent="applySlash(t)" @mousemove="slashIdx = i">
                <span class="tag tag-cat">{{ TPL_CATS[t.category] || t.category }}</span>
                <span class="slash-body">
                  <b>{{ t.title }}</b>
                  <i>{{ t.content.replace(/\s+/g, ' ').slice(0, 46) }}</i>
                </span>
              </button>
              <div class="slash-hint">↑↓ 选择 · Enter 插入 · Esc 关闭</div>
            </div>
          </div>
          <button class="btn btn-primary" style="margin-top:10px;width:100%" :class="{ loading: busy }" :disabled="busy || !reply.trim()" @click="send">发送回复</button>
        </div>
        <div v-else class="chatws-closed">🔒 会话已关闭，不再接受回复</div>
      </template>
    </div>
  </div>

  <!-- 快捷模板管理弹窗 -->
  <div v-if="tplDlg" class="modal open" @click.self="tplDlg = false">
    <div class="modal-box" style="max-width:720px">
      <button class="modal-x" @click="tplDlg = false">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:10px">快捷回复模板</h3>
      <div class="tpl-grid">
        <div class="tpl-list">
          <div v-for="t in tplList" :key="t.id" class="tpl-row" :class="{ on: tplForm.id === t.id }" @click="editTpl(t)">
            <span class="tag tag-cat">{{ TPL_CATS[t.category] || t.category }}</span>
            <b>{{ t.title }}</b>
            <span v-if="!t.active" class="tag tag-pending">停用</span>
            <span style="flex:1"></span>
            <button class="btn btn-ghost btn-sm" style="color:var(--error)" :disabled="tplBusy" @click.stop="delTpl(t)">删</button>
          </div>
          <div v-if="!tplList.length" class="empty-line" style="text-align:center;padding:16px 0">（暂无模板）</div>
        </div>
        <div class="tpl-form">
          <div style="display:flex;gap:8px">
            <select v-model.number="tplForm.category" class="input" style="flex:1">
              <option v-for="(name, v) in TPL_CATS" :key="v" :value="Number(v)">{{ name }}</option>
            </select>
            <label style="display:flex;align-items:center;gap:5px;font-size:12.5px;white-space:nowrap">
              <input v-model.number="tplForm.active" type="checkbox" :true-value="1" :false-value="0"> 启用
            </label>
          </div>
          <input v-model="tplForm.title" class="input" placeholder="模板标题（如：运费/时效说明）">
          <textarea v-model="tplForm.content" class="input" rows="4" placeholder="模板内容（回复时可直接插入）"></textarea>
          <div style="display:flex;gap:8px">
            <button class="btn btn-primary btn-sm" style="flex:1" :disabled="tplBusy" @click="saveTpl">{{ tplForm.id ? '保存修改' : '新增模板' }}</button>
            <button v-if="tplForm.id" class="btn btn-secondary btn-sm" @click="newTpl">新建</button>
          </div>
        </div>
      </div>
      <p style="font-size:11.5px;color:var(--gray);margin-top:10px">回复框输入 <code>/</code> 可快捷调出模板（↑↓ 选择 · Enter 插入）</p>
    </div>
  </div>

  <!-- 客户快捷问题配置（结构化卡片 + 动作类型 + 手机预览） -->
  <div v-if="quickDlg" class="modal open" @click.self="closeQuickDlg">
    <div class="modal-box" style="max-width:880px">
      <button class="modal-x" @click="closeQuickDlg">×</button>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <h3 style="font-family:var(--font-title)">⚡ 客户快捷问题</h3>
        <span v-if="quickMeta.customized" class="tag tag-done">自定义</span>
        <span v-else class="tag tag-pending">默认配置</span>
      </div>
      <p style="font-size:12px;color:var(--gray);margin-bottom:12px">
        前台聊天窗 AI 模式下的快捷 chips（每语言 ≤{{ QUICK_LIMIT }} 条 · 单条 ≤{{ QUICK_CHARS }} 字）
        <template v-if="quickMeta.updated_at"> · 最后修改：{{ quickMeta.updated_by || '#' }} {{ dt(quickMeta.updated_at) }}</template>
      </p>
      <div class="qk-grid">
        <!-- 左：编辑区 -->
        <div>
          <div class="otab" style="margin-bottom:10px">
            <button v-for="l in ['zh', 'en']" :key="l" :class="{ on: quickLang === l }" style="background:none;border:none;cursor:pointer" @click="quickLang = l">{{ l === 'zh' ? '中文' : 'English' }}</button>
          </div>
          <div class="qk-list">
            <div v-for="(q, i) in curList()" :key="i" class="qk-card">
              <div class="qk-card-top">
                <span class="qk-idx">{{ i + 1 }}</span>
                <input v-model="q.text" class="input" style="flex:1" :maxlength="QUICK_CHARS + 10" placeholder="按钮文案，如 📦 我的订单到哪了？">
                <span class="qk-cnt" :class="{ over: q.text.length > QUICK_CHARS }">{{ q.text.length }}/{{ QUICK_CHARS }}</span>
                <button class="btn btn-ghost btn-sm" :disabled="i === 0" title="上移" @click="moveQuick(i, -1)">↑</button>
                <button class="btn btn-ghost btn-sm" :disabled="i === curList().length - 1" title="下移" @click="moveQuick(i, 1)">↓</button>
                <button class="btn btn-ghost btn-sm" style="color:var(--error)" title="删除" @click="delQuick(i)">✕</button>
              </div>
              <div class="qk-card-act">
                <select v-model="q.action" class="input" style="width:auto;height:30px;font-size:12px">
                  <option v-for="[v, label] in ACTION_OPTS" :key="v" :value="v">{{ label }}</option>
                </select>
                <input v-if="q.action === 'link'" v-model="q.url" class="input" style="flex:1;height:30px;font-size:12px" placeholder="站内路径，如 /returns-policy">
                <span v-else style="font-size:11px;color:var(--gray)">{{ ACTION_OPTS.find((x) => x[0] === q.action)?.[2] }}</span>
              </div>
            </div>
            <button class="btn btn-secondary btn-sm" style="width:100%" :disabled="curList().length >= QUICK_LIMIT" @click="addQuick">
              ＋ 添加（{{ curList().length }}/{{ QUICK_LIMIT }}）
            </button>
          </div>
        </div>
        <!-- 右：手机预览（模拟前台聊天窗 chips 实际渲染） -->
        <div class="qk-preview">
          <div class="qk-phone">
            <div class="qk-phone-head">GLOWMAG 客服</div>
            <div class="qk-phone-body"><div class="qk-bubble">嗨，宝贝！💅 有什么可以帮你？</div></div>
            <div class="qk-phone-quicks">
              <span v-for="(q, i) in curList().filter((x) => x.text.trim())" :key="i" class="qk-chip" :class="{ human: q.action === 'human' }">
                {{ q.text }}<template v-if="q.action === 'link'"> ↗</template>
              </span>
            </div>
          </div>
          <div class="qk-legend">
            <div><span class="qk-chip">文案</span> 点击发送给 AI</div>
            <div><span class="qk-chip">文案 ↗</span> 跳转站内页面</div>
            <div><span class="qk-chip human">文案</span> 直接转人工</div>
          </div>
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-top:14px;align-items:center">
        <button class="btn btn-primary" :class="{ loading: quickBusy }" :disabled="quickBusy || !isQuickDirty" @click="saveQuicks">{{ isQuickDirty ? '保存修改' : '已保存' }}</button>
        <button class="btn btn-secondary" :disabled="quickBusy" title="删除自定义配置，恢复出厂默认" @click="resetQuicks">恢复默认</button>
        <span style="flex:1"></span>
        <span v-if="isQuickDirty" class="tag tag-error">未保存</span>
        <button class="btn btn-ghost" @click="closeQuickDlg">关闭</button>
      </div>
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
.chatws-input-wrap{position:relative}
/* Slash 快捷指令菜单：输入框上方浮层（mousedown 抢先于 blur 生效） */
.slash-menu{position:absolute;left:0;right:0;bottom:calc(100% + 6px);background:#fff;border:1px solid var(--gray-light);border-radius:12px;box-shadow:var(--shadow-pop);overflow:hidden;z-index:20}
.slash-item{display:flex;align-items:center;gap:10px;width:100%;text-align:left;padding:8px 12px;background:none;border:none;cursor:pointer;font-size:12.5px}
.slash-item + .slash-item{border-top:1px solid var(--gray-light)}
.slash-item:hover,.slash-item.on{background:var(--rose-pale)}
.slash-body{display:flex;flex-direction:column;gap:2px;min-width:0}
.slash-body b{font-size:12.5px;color:var(--ink)}
.slash-body i{font-style:normal;font-size:11px;color:var(--gray);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.slash-hint{padding:6px 12px;font-size:10.5px;color:var(--gray);background:var(--bg-page);text-align:center}
.chatws-reply-bar{display:flex;gap:8px;align-items:center;margin-bottom:8px}
.chatws-count{font-size:11.5px;color:var(--gray);white-space:nowrap}
.chatws-closed{margin-top:12px;padding:12px;background:var(--gray-light);border-radius:10px;font-size:12.5px;color:var(--gray);text-align:center}
/* 模板管理弹窗：左列表 + 右表单 */
.tpl-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.tpl-list{max-height:340px;overflow-y:auto;border:1px solid var(--gray-light);border-radius:10px;padding:4px 0}
.tpl-row{display:flex;align-items:center;gap:8px;padding:8px 12px;font-size:12.5px;cursor:pointer;border-bottom:1px solid var(--gray-light)}
.tpl-row:last-child{border-bottom:none}
.tpl-row:hover{background:var(--row-hover)}
.tpl-row.on{background:var(--rose-pale)}
.tpl-row b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tpl-form{display:flex;flex-direction:column;gap:8px}
/* 客户快捷问题配置：左编辑卡 + 右手机预览 */
.qk-grid{display:grid;grid-template-columns:1fr 240px;gap:16px}
.qk-list{display:flex;flex-direction:column;gap:8px}
.qk-card{border:1px solid var(--gray-light);border-radius:10px;padding:8px 10px;background:var(--row-alt)}
.qk-card-top{display:flex;align-items:center;gap:6px}
.qk-idx{font-size:11px;color:var(--gray);width:14px;text-align:center;flex:none}
.qk-cnt{font-size:10.5px;color:var(--gray);flex:none;min-width:44px;text-align:right}
.qk-cnt.over{color:var(--error);font-weight:700}
.qk-card-act{display:flex;align-items:center;gap:8px;margin-top:6px;padding-left:20px}
.qk-preview{display:flex;flex-direction:column;gap:10px}
.qk-phone{border:1.5px solid var(--gray-light);border-radius:16px;overflow:hidden;box-shadow:var(--shadow-card);background:#fff}
.qk-phone-head{background:var(--plum);color:#fff;font-size:12px;font-weight:700;padding:8px 12px}
.qk-phone-body{background:var(--bg-page);padding:10px;min-height:64px}
.qk-bubble{background:#fff;border:1px solid var(--gray-light);border-radius:10px 10px 10px 4px;font-size:11.5px;padding:7px 10px;display:inline-block;color:var(--ink)}
.qk-phone-quicks{display:flex;flex-wrap:wrap;gap:5px;padding:8px 10px;border-top:1px solid var(--gray-light);background:#fff}
.qk-chip{font-size:11px;font-weight:600;color:var(--plum);background:var(--rose-pale);border-radius:999px;padding:3px 9px}
.qk-chip.human{background:var(--plum);color:#fff}
.qk-legend{font-size:11px;color:var(--gray);display:flex;flex-direction:column;gap:6px}
.qk-legend .qk-chip{cursor:default}
@media (max-width:1080px){.chatws{grid-template-columns:1fr}.qk-grid{grid-template-columns:1fr}}
</style>
