<script setup>
/* 在线客服聊天工作台：三渠道会话列表 + 实时对话（4s 轮询）+ 快捷模板回复 + 接单/关闭
 * 渠道 0 AI / 1 人工 / 2 美甲师；美甲师账号（role=4）默认锁定「我的会话」 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { req } from '../api/client'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'
import { dt } from '../composables/format'
import { useQuerySync } from '../composables/useQuerySync'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const session = useSessionStore()
const isArtist = computed(() => session.role === 4)

const items = ref([])
const total = ref(0)
const pendingTotal = ref(null)   /* 后端全局待回复数（列表响应 pending_total，缺失时回退当前页口径） */
const SIZE = 30
const loaded = ref(false)
const loadErr = ref(false)
const errMsg = ref('')
const pollFail = ref(false)      /* 轮询失败 → 顶栏「连接中断」横幅，恢复后自动清除 */

/* 筛选 URL 同步：channel(all/0/1/2) / status(0 进行中 1 已关闭) / mine / q / page
 * 美甲师（role=4）mine 默认 '1'（URL 无值/被清时回落我的会话，不可解除） */
const st = reactive({ channel: 'all', status: '0', q: '', mine: '', page: 1 })
useQuerySync(st, { nums: ['page'], defaults: { channel: 'all', status: '0', q: '', mine: isArtist.value ? '1' : '', page: 1 } })
if (isArtist.value && st.mine !== '1') st.mine = '1'
/* watch 兜底：外部导航清掉 mine 键时回落默认，onPop 回填 '' 也会被强制拉回 '1' */
watch(() => st.mine, () => { if (isArtist.value && st.mine !== '1') st.mine = '1' })

const CHANNEL = { 0: 'AI', 1: '人工', 2: '美甲师' }
const TABS = [
  ['all', '全部', null, '💬'],
  ['1', '人工', 1, '👩‍💼'],
  ['2', '美甲师', 2, '💅'],
  ['0', 'AI', 0, '🤖'],
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

/* quiet=true 为轮询路径：失败静默（console.warn + 顶栏横幅），手动刷新仍 toast */
async function load(p = 1, quiet = false) {
  if (!quiet) { loadErr.value = false; errMsg.value = '' }
  try {
    const d = await req('GET', buildUrl(p))
    items.value = d.items || []
    total.value = d.total ?? 0
    pendingTotal.value = d.pending_total
    st.page = p
    pollFail.value = false
    /* 轮询/翻页后页码越界（会话被关闭致数据收缩）：空页且 total>0 且不在第 1 页 → 回第 1 页重拉（防递归：第 1 页不再回拉） */
    if (!items.value.length && total.value > 0 && st.page > 1) { load(1, quiet); return }
  } catch (e) {
    if (quiet) {
      console.warn('会话列表轮询失败：', e.message || e)
      pollFail.value = true
    } else {
      loadErr.value = true
      errMsg.value = e.message || ''
      toast('会话列表加载失败：' + (e.message || ''), 'error')
    }
  }
  loaded.value = true
}

async function openConv(row) {
  active.value = { ...row, messages: [] }
  await refreshActive()
  scrollThread(true)   /* 切换会话强制滚到底 */
}

/* 打开失败置错误态（线程区渲染错误文案 + 重试，见 retryActive），不再伪装「无消息记录」；
 * quiet（轮询）失败不置错误态，仅由顶栏横幅提示 */
async function refreshActive(quiet) {
  if (!active.value) return
  const no = active.value.conv_no   /* 竞态守卫：响应回来时已切换会话则丢弃 */
  try {
    const d = await req('GET', '/api/admin/chat/conversations/' + no)
    if (!active.value || active.value.conv_no !== no) return
    const prevCount = (active.value.messages || []).length
    const nextCount = (d.messages || []).length
    /* 替换消息数据「前」先测是否在底部（消息变少视为 force）：
     * DOM 增长后再测「距底 <80px」会把本在底部、但新消息高于 80px 的用户误判为不在底部 */
    const el = threadBox.value
    const wasBottom = nextCount < prevCount || !el || el.scrollHeight - el.scrollTop - el.clientHeight < 80
    active.value = d
    if (nextCount !== prevCount) scrollThread(wasBottom)
  } catch (e) {
    if (!active.value || active.value.conv_no !== no) return
    if (!quiet) {
      toast('对话加载失败：' + (e.message || ''), 'error')
      active.value.loadErr = true
      active.value.loadErrMsg = e.message || ''
    } else {
      /* 兑现注释：线程轮询失败也由顶栏「连接中断」横幅提示（列表轮询成功时统一清除） */
      pollFail.value = true
    }
  }
}

async function retryActive() {
  if (!active.value) return
  active.value.loadErr = false
  await refreshActive()
  if ((active.value?.messages || []).length) scrollThread(true)
}

/* 滚动跟随：follow 由调用方在「替换消息数据前」测得的 wasBottom 传入，切会话/发送成功恒 true 强制拉底；
 * 上翻历史（follow=false）不拽回 */
function scrollThread(follow) {
  nextTick(() => {
    const el = threadBox.value
    if (!el || !follow) return
    el.scrollTop = el.scrollHeight
  })
}

function setTab(k) { if (st.channel !== k) { st.channel = k; load(1) } }
function setStatus(v) { if (st.status !== v) { st.status = v; load(1) } }
function search() { load(1) }
const filtered = computed(() => st.channel !== 'all' || st.status !== '0' || st.mine !== '' || st.q.trim() !== '')

/* ===== 快捷回复模板（下拉与 slash 菜单共用同一数据源：admin 端点过滤启用项） ===== */
const templates = ref([])
const templatesLoaded = ref(false)
async function loadTemplates() {
  if (templatesLoaded.value) return
  await ensureSlashAll()
  if (!slashAllLoaded.value) return   /* 拉取失败保持「加载快捷模板…」，重选再试 */
  templates.value = slashAll.value
  templatesLoaded.value = true
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
/* dirty 基线：表单与打开模板时的快照比对（新增/编辑/保存成功时重置），未保存关闭需确认丢弃 */
const tplSnap = ref('')
const tplFormJson = () => JSON.stringify({ id: tplForm.id, category: tplForm.category, title: tplForm.title, content: tplForm.content, active: tplForm.active })
const isTplDirty = computed(() => tplDlg.value && tplFormJson() !== tplSnap.value)
function closeTplDlg() {
  if (isTplDirty.value) { askDiscard(() => { tplDlg.value = false }); return }
  tplDlg.value = false
}
async function openTplDlg() {
  tplDlg.value = true
  /* 打开即写快照：表单可能残留上次编辑值，不写快照会导致未编辑直接关闭误弹「放弃未保存的修改」 */
  tplSnap.value = tplFormJson()
  await reloadTplList()
}
async function reloadTplList() {
  try { tplList.value = (await req('GET', '/api/admin/ops/templates')).items || [] } catch (e) { toast('模板加载失败：' + (e.message || ''), 'error') }
}
function newTpl() {
  Object.assign(tplForm, { id: null, category: 1, title: '', content: '', active: 1 })
  tplSnap.value = tplFormJson()
}
function editTpl(t) {
  Object.assign(tplForm, { id: t.id, category: t.category, title: t.title, content: t.content, active: t.active })
  tplSnap.value = tplFormJson()
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
/* 删除模板：danger 确认（防误触；删除后下拉与 slash 菜单数据源同步刷新） */
const delTplDlg = ref(false)
const delTplTarget = ref(null)
function askDelTpl(t) { delTplTarget.value = t; delTplDlg.value = true }
async function delTpl() {
  const t = delTplTarget.value
  if (tplBusy.value || !t) return
  tplBusy.value = true
  try {
    await req('DELETE', '/api/admin/ops/templates/' + t.id)
    toast('模板已删除 ✓', 'success')
    delTplDlg.value = false
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
  /* 逐语言非空校验（与后端对齐）：任一语言缺失即拦截 */
  if (!zh.length) { toast('中文快捷问题不能为空', 'error'); return }
  if (!en.length) { toast('英文快捷问题不能为空', 'error'); return }
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
  if (isQuickDirty.value) { askDiscard(() => { quickDlg.value = false }); return }
  quickDlg.value = false
}

/* 未保存修改丢弃确认（模板编辑 / 快捷问题弹窗共用 ConfirmDialog，替代原生 confirm） */
const discardDlg = ref(false)
let discardFn = null
function askDiscard(fn) { discardFn = fn; discardDlg.value = true }
function doDiscard() { discardDlg.value = false; if (discardFn) discardFn() }

/* ===== 操作 ===== */
async function send() {
  if (!reply.value.trim() || !active.value || busy.value) return
  if (reply.value.length > 2000) { toast('回复内容过长（最多 2000 字）', 'error'); return }
  busy.value = true
  try {
    const d = await req('POST', `/api/admin/chat/conversations/${active.value.conv_no}/reply`, { content: reply.value })
    active.value = d
    reply.value = ''
    scrollThread(true)   /* 发送成功直接拉底（不依赖距底判定，新消息再高也跟随） */
    load(st.page)
  } catch (e) {
    const det = String(e.data?.detail || e.message || '')
    toast('发送失败：' + (/reply too long/i.test(det) ? '回复内容过长（最多 2000 字）' : det), 'error')
  }
  finally { busy.value = false }
}

/* 接单抢占确认：会话已被他人接单（agent_admin_id 存在且非本人）时先弹确认再接管 */
const takeDlg = ref(false)
const takeOverName = computed(() => active.value?.agent_name || '#' + (active.value?.agent_admin_id || ''))
function askTake() {
  if (busy.value || !active.value) return
  if (active.value.agent_admin_id && active.value.agent_admin_id !== session.user?.id) takeDlg.value = true
  else take()
}
async function doTake() { takeDlg.value = false; await take() }

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

/* 关闭会话：不可恢复操作，先 ConfirmDialog 确认（见 askClose/doCloseConv） */
const closeDlg = ref(false)
function askClose() { if (busy.value || !active.value) return; closeDlg.value = true }
async function doCloseConv() { closeDlg.value = false; await closeConv() }

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

/* ===== 视觉辅助：头像渐变（按名字 hash 取色）/ 首字母 / 日期分组 / 本页待回复数 ===== */
const AVA_G = [
  'linear-gradient(135deg,#c084fc,#7c3aed)',
  'linear-gradient(135deg,#fb7185,#e11d48)',
  'linear-gradient(135deg,#fbbf24,#f97316)',
  'linear-gradient(135deg,#34d399,#059669)',
  'linear-gradient(135deg,#60a5fa,#2563eb)',
  'linear-gradient(135deg,#f472b6,#db2777)',
]
function avaG(s) {
  let h = 0
  for (const ch of String(s || '?')) h = (h * 31 + ch.codePointAt(0)) % 997
  return AVA_G[h % AVA_G.length]
}
const initial = (s) => String(s || '?').trim().charAt(0).toUpperCase()
const SENDER_ICON = { 2: '👩‍💼', 4: '🤖', 5: '💅' }

/* 消息按日期分组（今天/昨天/MM月DD日），组间渲染时间分隔条
 * 日期口径与 dt() 一致（后端 UTC 补 Z → 本地时区），确保「今天/昨天」与气泡时间吻合 */
const localDay = (iso) => dt(iso).slice(0, 10)
function dayLabel(d) {
  const now = Date.now()
  if (d === localDay(new Date(now).toISOString())) return '今天'
  if (d === localDay(new Date(now - 864e5).toISOString())) return '昨天'
  return d.slice(5).replace('-', '月') + '日'
}
const threadGroups = computed(() => {
  const out = []
  let cur = null
  for (const m of active.value?.messages || []) {
    const day = localDay(m.created_at) || String(m.created_at || '').slice(0, 10)
    if (!cur || cur.day !== day) { cur = { day, label: dayLabel(day), msgs: [] }; out.push(cur) }
    cur.msgs.push(m)
  }
  return out
})
/* 待回复数：优先后端全局 pending_total（跨页汇总），字段缺失时回退当前页口径 */
const pendingN = computed(() => pendingTotal.value ?? items.value.filter((c) => c.pending_reply).length)

/* ===== 4s 轮询：列表红点 + 当前会话新消息（页面可见时） ===== */
let timer = null
onMounted(() => {
  load(1)
  timer = setInterval(() => {
    if (document.visibilityState === 'visible') { load(st.page, true); refreshActive(true) }
  }, 4000)
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })

const isOpen = computed(() => !!active.value && active.value.status === 0)
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">在线客服</h1>
      <span class="page-sub">共 {{ total }} 个会话<template v-if="pendingN"> · <b class="cw-pend">{{ pendingN }} 待回复</b></template> · 4 秒自动刷新</span>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <button class="btn btn-secondary" @click="openQuickDlg">⚡ 客户快捷问题</button>
      <button class="btn btn-secondary" @click="openTplDlg">🗂 快捷模板</button>
    </div>
  </div>

  <!-- 轮询失败：连接中断横幅（恢复后自动清除） -->
  <div v-if="pollFail" class="cw-offline">⚠️ 连接中断，正在自动重试…</div>

  <div class="filter-bar" style="margin-bottom:14px">
    <button v-for="[k, label, , ico] in TABS" :key="k" class="ttab" :class="{ on: st.channel === k }" @click="setTab(k)"><span class="cw-tab-ico">{{ ico }}</span>{{ label }}</button>
    <span style="flex:1"></span>
    <button class="ttab" :class="{ on: st.status === '0' }" @click="setStatus('0')">进行中</button>
    <button class="ttab" :class="{ on: st.status === '1' }" @click="setStatus('1')">已关闭</button>
    <select v-if="!isArtist" class="input" :value="st.mine" style="width:auto;height:38px;font-size:13px" @change="st.mine = $event.target.value; load(1)">
      <option value="">全部会话</option>
      <option value="1">我的会话</option>
    </select>
    <input v-model="st.q" class="input js-search" style="width:200px;height:38px" placeholder="会话号 / 邮箱 / 姓名" @keydown.enter="search()">
    <button class="btn btn-secondary btn-sm" style="height:38px" @click="search()">搜索</button>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px" />

  <EmptyState v-else-if="loadErr && !items.length" icon="⚠️" title="会话列表加载失败" :sub="errMsg || '服务端可能未启动或会话已过期'">
    <template #action><button class="btn btn-secondary btn-sm" @click="load(st.page)">重试</button></template>
  </EmptyState>

  <div v-else class="chatws">
    <!-- 左：会话列表 -->
    <div class="card cw-listcard">
      <div class="cw-scroll">
        <div v-for="c in items" :key="c.conv_no" class="cw-row" :class="{ on: active && active.conv_no === c.conv_no }" @click="openConv(c)">
          <div class="cw-ava" :style="{ background: avaG(who(c)) }">{{ initial(who(c)) }}</div>
          <div class="cw-row-main">
            <div class="cw-row-top">
              <b class="cw-name">{{ who(c) }}</b>
              <span class="cw-ch" :class="'c' + c.channel">{{ CHANNEL[c.channel] }}</span>
              <span v-if="c.status === 1" class="cw-ch off">关闭</span>
              <span v-if="c.pending_reply" class="cw-dot" title="客户待回复"></span>
              <span class="cw-time">{{ dt(c.last_message_at) }}</span>
            </div>
            <div class="cw-preview">
              <template v-if="c.last_message">{{ [2, 4, 5].includes(c.last_message.sender) ? '↩ ' : '' }}{{ c.last_message.preview }}</template>
              <template v-else>（暂无消息）</template>
            </div>
            <div class="cw-meta">
              <span class="cw-no">{{ c.conv_no }}</span>
              <span style="flex:1"></span>
              <span v-if="c.status !== 1 && c.channel === 1 && !c.agent_admin_id" class="cw-mini warn">待接入</span>
              <span v-else-if="c.channel === 1 && c.agent_name" class="cw-mini ok">👩‍💼 {{ c.agent_name }}</span>
              <span v-else-if="c.channel === 2 && c.artist_name" class="cw-mini ok">💅 {{ c.artist_name }}</span>
            </div>
          </div>
        </div>
      <EmptyState v-if="!items.length" :icon="filtered ? '🔍' : '💬'" :title="filtered ? '未找到匹配的会话' : '暂无会话'" :sub="filtered ? '试试调整或清除筛选' : '客户发起聊天后将显示在这里'" />
      </div>
      <Pagination embed :page="st.page" :pages="pages" :total="total" unit="个" @go="load" />
    </div>

    <!-- 右：对话窗（客户档案头 + 日期分组气泡流 + 回复区） -->
    <div class="card cw-pane">
      <div v-if="!active" class="cw-empty">
        <EmptyState icon="💬" title="选择一个会话开始服务" sub="点击左侧会话查看完整对话与客户信息" />
      </div>
      <template v-else>
        <div class="cw-head">
          <div class="cw-ava lg" :style="{ background: avaG(who(active)) }">{{ initial(who(active)) }}</div>
          <div class="cw-head-info">
            <div class="cw-head-name">
              {{ who(active) }}
              <span class="cw-ch" :class="'c' + active.channel">{{ CHANNEL[active.channel] }}</span>
              <span v-if="active.status === 1" class="cw-ch off">已关闭</span>
            </div>
            <div class="cw-head-sub">
              {{ active.conv_no }}<template v-if="active.email"> · {{ active.email }}</template>
              <template v-if="active.channel === 2 && active.artist_name"> · 美甲师 {{ active.artist_name }}</template>
              <template v-if="active.channel === 1 && active.agent_name"> · 客服 {{ active.agent_name }}</template>
              · {{ dt(active.created_at) }}
            </div>
          </div>
          <div v-if="isOpen" class="cw-head-acts">
            <button v-if="active.channel === 1 && active.agent_admin_id !== session.user?.id" class="btn btn-secondary btn-sm" :disabled="busy" @click="askTake">🙋 接单</button>
            <button v-if="active.channel === 1" class="btn btn-secondary btn-sm" :disabled="busy" title="人工 → AI（同一会话交还 GlowBot 自动应答）" @click="resumeAi">🤖 转回 AI</button>
            <button class="btn btn-ghost btn-sm" style="color:var(--error)" :disabled="busy" @click="askClose">关闭会话</button>
          </div>
        </div>

        <div class="cw-thread" ref="threadBox">
          <template v-for="g in threadGroups" :key="g.day">
            <div class="cw-day">{{ g.label }}</div>
            <template v-for="m in g.msgs" :key="m.id">
              <div v-if="m.sender === 3" class="cw-sys">{{ m.content }}<span class="cw-sys-t">{{ dt(m.created_at) }}</span></div>
              <div v-else class="cw-msg" :class="{ me: m.sender !== 1 }">
                <div v-if="m.sender === 1" class="cw-mava" :style="{ background: avaG(who(active)) }">{{ initial(who(active)) }}</div>
                <div v-else class="cw-mava bot">{{ SENDER_ICON[m.sender] || '👩‍💼' }}</div>
                <div class="cw-bwrap">
                  <div v-if="m.sender !== 1 && m.sender_name" class="cw-who-line">{{ m.sender_name }}</div>
                  <div class="cw-bubble">{{ m.content }}</div>
                  <div class="cw-t">{{ dt(m.created_at) }}</div>
                </div>
              </div>
            </template>
          </template>
          <div v-if="active.loadErr" class="cw-none">
            <span style="color:var(--error)">对话加载失败：{{ active.loadErrMsg || '网络异常' }}</span>
            <button class="btn btn-secondary btn-sm" style="margin-left:10px" @click="retryActive">重试</button>
          </div>
          <div v-else-if="!(active.messages || []).length" class="cw-none">（无消息记录）</div>
        </div>

        <div v-if="isOpen" class="cw-reply">
          <div class="cw-reply-bar">
            <select class="input cw-tplsel" @focus="loadTemplates" @change="applyTemplate">
              <option value="">{{ templatesLoaded ? (templates.length ? '🗂 快捷模板…' : '暂无模板') : '加载快捷模板…' }}</option>
              <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.title }}</option>
            </select>
            <span class="cw-count">{{ (active.messages || []).length }} 条消息</span>
            <span class="cw-kbd-hint"><code>/</code> 模板 · <code>Ctrl+Enter</code> 发送</span>
          </div>
          <div class="cw-input-wrap">
            <textarea v-model="reply" class="input" rows="3" maxlength="2000" placeholder="输入回复…" @input="onReplyInput" @blur="onReplyBlur" @keydown="onReplyKeydown" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send" />
            <button class="btn btn-primary cw-send" :class="{ loading: busy }" :disabled="busy || !reply.trim()" @click="send">➤ 发送</button>
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
        </div>
        <div v-else class="cw-closed">🔒 会话已关闭，不再接受回复</div>
      </template>
    </div>
  </div>

  <!-- 快捷模板管理弹窗 -->
  <div v-if="tplDlg" class="modal open" @click.self="closeTplDlg">
    <div class="modal-box" style="max-width:720px">
      <button class="modal-x" @click="closeTplDlg">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:10px">快捷回复模板</h3>
      <div class="tpl-grid">
        <div class="tpl-list">
          <div v-for="t in tplList" :key="t.id" class="tpl-row" :class="{ on: tplForm.id === t.id }" @click="editTpl(t)">
            <span class="tag tag-cat">{{ TPL_CATS[t.category] || t.category }}</span>
            <b>{{ t.title }}</b>
            <span v-if="!t.active" class="tag tag-pending">停用</span>
            <span style="flex:1"></span>
            <button class="btn btn-ghost btn-sm" style="color:var(--error)" :disabled="tplBusy" @click.stop="askDelTpl(t)">删</button>
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

  <!-- 关闭会话确认：不可恢复（danger） -->
  <ConfirmDialog
    :open="closeDlg"
    title="关闭会话"
    :body="`关闭 ${active?.conv_no} 后客户不能再回复，且不可恢复；如仅暂停人工接待可先转回 AI。`"
    confirm-text="确认关闭"
    danger
    :busy="busy"
    @confirm="doCloseConv"
    @close="closeDlg = false"
  />

  <!-- 接管会话确认：他人接单中抢占 -->
  <ConfirmDialog
    :open="takeDlg"
    title="接管会话"
    :body="`该会话由 ${takeOverName} 接单中，确定接管吗？`"
    confirm-text="确定接管"
    :busy="busy"
    @confirm="doTake"
    @close="takeDlg = false"
  />

  <!-- 删除快捷模板确认（danger） -->
  <ConfirmDialog
    :open="delTplDlg"
    title="删除快捷模板"
    :body="`删除模板「${delTplTarget?.title || ''}」？删除后不可恢复，回复下拉与 / 菜单将同步移除。`"
    danger
    confirm-text="删除"
    :busy="tplBusy"
    @confirm="delTpl"
    @close="delTplDlg = false"
  />

  <!-- 未保存修改丢弃确认（模板编辑 / 快捷问题弹窗共用） -->
  <ConfirmDialog
    :open="discardDlg"
    title="放弃未保存的修改？"
    body="当前弹窗有未保存的修改，关闭后将丢失。"
    confirm-text="放弃修改"
    danger
    @confirm="doDiscard"
    @close="discardDlg = false"
  />
</template>

<style scoped>
/* ===== 工作台：满高双栏（左 370px 列表 + 右对话），栏内滚动，整页不再跟随长列表 ===== */
.chatws{display:grid;grid-template-columns:370px 1fr;gap:16px;height:calc(100vh - 216px);min-height:560px}
.cw-pend{color:var(--error)}
/* 轮询中断横幅 */
.cw-offline{margin:-4px 0 12px;padding:8px 14px;border-radius:10px;background:var(--pale-error);color:var(--error);font-size:12.5px}
.cw-tab-ico{margin-right:5px;font-size:12px}
/* ---- 左：会话列表 ---- */
.cw-listcard{display:flex;flex-direction:column;overflow:hidden;padding:0}
.cw-scroll{flex:1;overflow-y:auto;min-height:0}
.cw-row{display:flex;gap:10px;padding:12px 14px;border-bottom:1px solid var(--gray-light);cursor:pointer;transition:background .12s}
.cw-row:hover{background:var(--row-hover)}
.cw-row.on{background:var(--rose-pale);box-shadow:inset 3px 0 0 var(--plum)}
.cw-row-main{flex:1;min-width:0}
.cw-row-top{display:flex;align-items:center;gap:6px}
.cw-name{font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cw-time{margin-left:auto;font-size:10.5px;color:var(--gray);white-space:nowrap}
.cw-preview{font-size:12px;color:var(--gray);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cw-meta{display:flex;align-items:center;gap:6px;margin-top:5px}
.cw-no{font-size:10.5px;color:var(--gray);letter-spacing:.3px}
/* 头像：按名字 hash 取渐变色 + 首字母 */
.cw-ava{width:38px;height:38px;border-radius:12px;color:#fff;font-weight:700;font-size:15px;display:flex;align-items:center;justify-content:center;flex:none;user-select:none}
.cw-ava.lg{width:44px;height:44px;border-radius:14px;font-size:17px}
/* 渠道小徽章 */
.cw-ch{font-size:10px;font-weight:700;padding:2px 8px;border-radius:999px;letter-spacing:.4px;flex:none}
.cw-ch.c0{background:#f1ecfa;color:#7c3aed}
.cw-ch.c1{background:var(--rose-pale);color:var(--plum)}
.cw-ch.c2{background:#e7f6ee;color:#1f9d55}
.cw-ch.off{background:var(--gray-light);color:var(--gray)}
/* 状态迷你胶囊 */
.cw-mini{font-size:10.5px;padding:1px 8px;border-radius:999px;white-space:nowrap}
.cw-mini.warn{background:#fdf0dd;color:#c2660a}
.cw-mini.ok{background:#e7f6ee;color:#1f9d55}
/* 待回复脉冲点 */
.cw-dot{width:8px;height:8px;border-radius:50%;background:var(--error);flex:none;animation:cwpulse 1.6s ease-in-out infinite}
@keyframes cwpulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.45;transform:scale(.75)}}
/* ---- 右：对话窗 ---- */
.cw-pane{display:flex;flex-direction:column;overflow:hidden;padding:0}
.cw-empty{flex:1;display:flex;align-items:center;justify-content:center}
.cw-head{display:flex;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid var(--gray-light);background:linear-gradient(180deg,#fff, #fdfaff)}
.cw-head-info{flex:1;min-width:0}
.cw-head-name{font-size:15px;font-weight:700;display:flex;align-items:center;gap:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cw-head-sub{font-size:11.5px;color:var(--gray);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* 消息流：细点纹理底 + 日期分隔 + 气泡（客户左/我方右） */
.cw-thread{flex:1;overflow-y:auto;min-height:0;display:flex;flex-direction:column;gap:6px;padding:16px 18px;background-color:#faf9fb;background-image:radial-gradient(var(--gray-light) 1px,transparent 1px);background-size:22px 22px}
.cw-day{align-self:center;font-size:10.5px;color:var(--gray);background:#fff;border:1px solid var(--gray-light);border-radius:999px;padding:2px 12px;margin:6px 0;position:sticky;top:0;z-index:2;box-shadow:var(--shadow-card)}
.cw-sys{align-self:center;max-width:88%;text-align:center;background:#fff;color:var(--gray);font-size:11.5px;line-height:1.5;padding:4px 12px;border-radius:999px;border:1px dashed var(--gray-light);white-space:pre-wrap;word-break:break-all}
.cw-sys-t{margin-left:6px;font-size:10.5px;opacity:.8}
.cw-msg{display:flex;gap:8px;max-width:78%;align-items:flex-end}
.cw-msg.me{align-self:flex-end;flex-direction:row-reverse}
.cw-mava{width:28px;height:28px;border-radius:50%;color:#fff;font-weight:700;font-size:12px;display:flex;align-items:center;justify-content:center;flex:none;user-select:none}
.cw-mava.bot{background:#fff;border:1px solid var(--gray-light);font-size:14px}
.cw-bwrap{display:flex;flex-direction:column;min-width:0}
.cw-msg.me .cw-bwrap{align-items:flex-end}
.cw-who-line{font-size:11px;font-weight:600;color:var(--gray);margin-bottom:3px}
.cw-bubble{background:#fff;border-radius:14px 14px 14px 4px;padding:10px 14px;font-size:13.5px;line-height:1.65;white-space:pre-wrap;word-break:break-word;box-shadow:var(--shadow-card);color:var(--ink)}
.cw-msg.me .cw-bubble{background:var(--rose-pale);color:var(--ink);border:1px solid var(--rose-light);box-shadow:none;border-radius:14px 14px 4px 14px}
.cw-t{font-size:10.5px;color:var(--gray);margin-top:4px;padding:0 2px}
.cw-none{align-self:center;font-size:12px;color:var(--gray);padding:24px 0}
/* 回复区：模板选择 + 内联发送按钮 */
.cw-reply{border-top:1px solid var(--gray-light);padding:12px 16px;background:#fff}
.cw-reply-bar{display:flex;gap:10px;align-items:center;margin-bottom:8px}
.cw-tplsel{height:32px;font-size:12.5px;flex:1;min-width:0}
.cw-count{font-size:11.5px;color:var(--gray);white-space:nowrap}
.cw-kbd-hint{font-size:11px;color:var(--gray);white-space:nowrap}
.cw-kbd-hint code{background:var(--gray-light);border-radius:4px;padding:1px 5px;font-size:10.5px}
.cw-input-wrap{position:relative;display:flex;gap:10px;align-items:stretch}
.cw-input-wrap .input{flex:1;resize:none}
.cw-send{width:96px;flex:none;font-weight:700}
.cw-closed{margin:12px 16px 16px;padding:12px;background:var(--gray-light);border-radius:10px;font-size:12.5px;color:var(--gray);text-align:center}
/* Slash 快捷指令菜单：输入框上方浮层（mousedown 抢先于 blur 生效） */
.slash-menu{position:absolute;left:0;right:106px;bottom:calc(100% + 6px);background:#fff;border:1px solid var(--gray-light);border-radius:12px;box-shadow:var(--shadow-pop);overflow:hidden;z-index:20}
.slash-item{display:flex;align-items:center;gap:10px;width:100%;text-align:left;padding:8px 12px;background:none;border:none;cursor:pointer;font-size:12.5px}
.slash-item + .slash-item{border-top:1px solid var(--gray-light)}
.slash-item:hover,.slash-item.on{background:var(--rose-pale)}
.slash-body{display:flex;flex-direction:column;gap:2px;min-width:0}
.slash-body b{font-size:12.5px;color:var(--ink)}
.slash-body i{font-style:normal;font-size:11px;color:var(--gray);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.slash-hint{padding:6px 12px;font-size:10.5px;color:var(--gray);background:var(--bg-page);text-align:center}
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
@media (max-width:1080px){
  .chatws{grid-template-columns:1fr;height:auto}
  .cw-scroll{max-height:420px}
  .cw-thread{max-height:520px}
  .cw-pane{min-height:560px}
  .qk-grid{grid-template-columns:1fr}
}
</style>
