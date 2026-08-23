<script setup>
import { nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { i18n, tt } from '../i18n'
import { req } from '../api/client'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'
import { zulu } from '../composables/datetime'

const router = useRouter()
const ui = useUiStore()
const auth = useAuthStore()
const open = ref(false)
const busy = ref(false)
const tab = ref('chat') /* chat（AI+人工合并） | artist */
const field = ref('')
const inputEl = ref(null)
const typing = ref(false)
const suggestions = ref([])
const loadErr = ref(false)
const inited = ref(false)
/* 客户快捷问题：后台可配置（/chat ⚡ 客户快捷问题），localStorage 5 分钟缓存，失败回退 i18n 默认 */
const quicks = ref([])
const QUICKS_CACHE_KEY = 'gm_chat_quicks'
const QUICKS_TTL = 5 * 60 * 1000
/* AI 与人工合并为单一客服 tab：同一会话内部切换（channel 0 AI ↔ 1 人工） */
const TABS = [
  ['chat', 'chat.tab.chat'],
  ['artist', 'chat.tab.artist'],
]
let msgSeq = 0 /* 本地乐观消息 key */

/* chat 槽位 = 进行中人工会话优先，否则 AI 会话（后端保证二者不同时开启） */
const convs = reactive({ chat: null, artist: null })
const artists = ref([])
const artistsLoaded = ref(false)
const pickArtist = ref(null) /* 美甲师 tab 选中待发起 */
/* 转人工中转：游客缺邮箱时先出内嵌表单 */
const wantHuman = ref(false)
/* 游客联系信息（人工/美甲师渠道回联用），localStorage 持久化复用 */
const contact = reactive({ name: '', email: '' })
const contactErr = ref('')
const CONTACT_KEY = 'gm_chat_contact'
const TOKEN_KEY = 'gm_chat_token'

function ensureToken() {
  let t = ''
  try { t = localStorage.getItem(TOKEN_KEY) || '' } catch (_) { /* 隐私模式 */ }
  if (!/^[0-9a-zA-Z_-]{8,64}$/.test(t)) {
    t = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random())).replace(/[^0-9a-zA-Z]/g, '').slice(0, 32).padEnd(12, '0')
    try { localStorage.setItem(TOKEN_KEY, t) } catch (_) { /* 隐私模式 */ }
  }
  return t
}
function loadContact() {
  try {
    const c = JSON.parse(localStorage.getItem(CONTACT_KEY) || 'null')
    if (c && typeof c.email === 'string') { contact.name = c.name || ''; contact.email = c.email }
  } catch (_) { /* 忽略坏数据 */ }
}
const needContact = () => !auth.isLoggedIn && !contact.email
const lang = () => (i18n.lang === 'zh' ? 'zh' : 'en')
/* 转人工/美甲师提交失败：常见后端错误映射双语，兜底通用文案 */
function submitErrText(e) {
  const m = String((e && e.message) || '').toLowerCase()
  if (m.includes('email')) return tt('Please enter your email first', '请先填写邮箱')
  return tt('Failed to submit, please try again', '提交失败，请重试')
}

/* 纳入全局 ESC（capture 阶段先于 App 的 document 委托）：其它浮层开着时让全局先关；
   仅面板独立在场时才自关并阻断后续监听 */
function onEsc(e) {
  if (e.key !== 'Escape' || !open.value) return
  if (ui.cartDrawer || ui.mnavOpen || ui.searchOpen || ui.openModalId) return
  e.stopPropagation()
  open.value = false
}
watch(open, (v) => { ui.chatOpen = v })

function scrollBottom() {
  nextTick(() => {
    const b = document.getElementById('chatMsgs')
    if (b) b.scrollTop = b.scrollHeight
  })
}
function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(zulu(iso))
  if (isNaN(d)) return ''
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
}
function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
function md(s) {
  return esc(s)
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1')
    .replace(/\r/g, '')
    .replace(/\n{2,}/g, '<br><br>')
    .replace(/\n/g, '<br>')
}
const SENDER_AVA = { 2: '👩‍💼', 4: '🤖', 5: '💅' }

/* ===== 会话生命周期 ===== */

async function createConv(channel, extra = {}) {
  const body = { channel, token: ensureToken(), lang: lang(), ...extra }
  if (contact.email) { body.email = contact.email; body.name = contact.name }
  return req('POST', '/api/chat/conversations', body)
}

async function init() {
  loadContact()
  loadQuicks()
  await refreshConvs()
  if (!convs.chat) {
    /* 后端合并守卫：人工会话进行中会直接复用，不会开平行 AI 会话 */
    try { convs.chat = await createConv(0); loadErr.value = false } catch (e) { loadErr.value = true }
  }
  inited.value = true
  scrollBottom()
}
async function retryInit() {
  loadErr.value = false
  await init()
}

async function loadQuicks() {
  /* 缓存对象内带 lang：语言不一致视作未命中（后台 quicks 按 zh/en 双语下发） */
  const cur = lang()
  try {
    const cached = JSON.parse(localStorage.getItem(QUICKS_CACHE_KEY) || 'null')
    if (cached && cached.lang === cur && Array.isArray(cached.items) && Date.now() - cached.at < QUICKS_TTL && cached.items.length) {
      quicks.value = cached.items
      return
    }
  } catch (_) { /* 坏缓存走网络 */ }
  try {
    const d = await req('GET', '/api/chat/quicks')
    const items = (d && (i18n.lang === 'zh' ? d.zh : d.en)) || []
    if (items.length) {
      quicks.value = items
      try { localStorage.setItem(QUICKS_CACHE_KEY, JSON.stringify({ at: Date.now(), lang: cur, items })) } catch (_) { /* 隐私模式 */ }
    }
  } catch (_) { /* 接口失败回退 i18n 默认 chips（模板里兜底渲染） */ }
}
/* 兜底（接口失败/未配置）：默认三条提问 chip */
const quickItems = () => quicks.value.length
  ? quicks.value
  : ['track', 'size', 'return'].map((k) => ({ text: i18n.t('chat.q.' + k), action: 'ask' }))
/* chip 动作分发：ask 发给 AI · link 站内跳转 · human 转人工 */
function tapQuick(q) {
  if (busy.value) return
  if (q.action === 'human') { goHuman(); return }
  if (q.action === 'link' && q.url) {
    open.value = false
    router.push(q.url)
    return
  }
  askText(q.text)
}

async function refreshConvs() {
  try {
    const d = await req('GET', '/api/chat/conversations?token=' + encodeURIComponent(ensureToken()))
    const items = (d && d.items) || []
    const openOf = (ch) => items.find((c) => c.channel === ch && c.status === 0) || null
    /* 合并槽位：人工进行中优先（转人工/客服接管态），否则 AI */
    convs.chat = openOf(1) || openOf(0)
    convs.artist = openOf(2)
    loadErr.value = false
  } catch (_) {
    loadErr.value = true
  }
}

async function toggle() {
  open.value = !open.value
  if (open.value) {
    scrollBottom()
    setTimeout(() => inputEl.value?.focus(), 250)
    if (!inited.value) await init()
  }
}

function switchTab(t) {
  tab.value = t
  suggestions.value = []
  wantHuman.value = false
  if (t === 'artist' && !artistsLoaded.value) loadArtists()
  scrollBottom()
  setTimeout(() => inputEl.value?.focus(), 150)
}

async function loadArtists() {
  try {
    const d = await req('GET', '/api/chat/artists')
    artists.value = (d && d.items) || []
    artistsLoaded.value = true
  } catch (_) { /* 卡片上留重试 */ }
}

/* ===== 转人工（唤起人工：同一会话原地升级，记录保留） ===== */

function goHuman() {
  contactErr.value = ''
  if (needContact()) { wantHuman.value = true; scrollBottom(); return }
  doEscalate()
}

async function doEscalate() {
  if (busy.value) return
  contactErr.value = ''
  if (needContact()) {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(contact.email)) { contactErr.value = i18n.t('chat.contact.err'); return }
    try { localStorage.setItem(CONTACT_KEY, JSON.stringify({ name: contact.name, email: contact.email })) } catch (_) { /* 隐私模式 */ }
  }
  busy.value = true
  try {
    let conv = convs.chat
    if (!conv) { conv = await createConv(0); convs.chat = conv }
    const d = await req('POST', `/api/chat/conversations/${conv.conv_no}/escalate`, {
      token: ensureToken(), email: contact.email || undefined, name: contact.name || undefined,
    })
    convs.chat = d
    wantHuman.value = false
    scrollBottom()
  } catch (e) {
    contactErr.value = submitErrText(e)
  } finally { busy.value = false }
}
function cancelEscalate() { wantHuman.value = false; contactErr.value = '' }

async function startArtist() {
  if (busy.value || !pickArtist.value) return
  contactErr.value = ''
  if (needContact()) {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(contact.email)) { contactErr.value = i18n.t('chat.contact.err'); return }
    try { localStorage.setItem(CONTACT_KEY, JSON.stringify({ name: contact.name, email: contact.email })) } catch (_) { /* 隐私模式 */ }
  }
  busy.value = true
  try {
    convs.artist = await createConv(2, { artist_id: pickArtist.value.id })
    pickArtist.value = null
    scrollBottom()
  } catch (e) {
    contactErr.value = submitErrText(e)
  } finally { busy.value = false }
}

async function endChat() {
  const conv = convs[tab.value]
  if (!conv || busy.value) return
  busy.value = true
  try {
    await req('POST', `/api/chat/conversations/${conv.conv_no}/close`, { token: ensureToken() })
    convs[tab.value] = null
    /* 客服 tab：结束后即开新 AI 会话（可继续问） */
    if (tab.value === 'chat') convs.chat = await createConv(0)
  } catch (_) { /* 服务端不可达时也可本地结束 */ 
    convs[tab.value] = null
  } finally { busy.value = false }
}

/* ===== 消息收发 ===== */

const curConv = () => convs[tab.value]
const curMsgs = () => (curConv() && curConv().messages) || []

function applyDetail(d) {
  const key = d.channel === 2 ? 'artist' : 'chat'
  convs[key] = d
}

async function pollActive() {
  const conv = curConv()
  if (!conv || conv.channel === 0) return /* AI 即时应答无需轮询 */
  try {
    const d = await req('GET', `/api/chat/conversations/${conv.conv_no}/messages?token=` + encodeURIComponent(ensureToken()))
    const oldMsgs = conv.messages || []
    if ((d.messages || []).length !== oldMsgs.length || d.status !== conv.status
        || d.agent_admin_id !== conv.agent_admin_id) {
      applyDetail(d)
      scrollBottom()
    }
  } catch (_) { /* 轮询失败静默，下轮重试 */ }
}
let pollTimer = null
onMounted(() => {
  window.addEventListener('keydown', onEsc, true)
  pollTimer = setInterval(() => {
    if (open.value && document.visibilityState === 'visible') pollActive()
  }, 4000)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onEsc, true)
  if (pollTimer) clearInterval(pollTimer)
  ui.chatOpen = false
})

async function send() {
  const v = field.value.trim()
  if (!v || busy.value) return
  let conv = curConv()
  if (!conv) {
    if (tab.value === 'chat') { conv = await createConv(0); convs.chat = conv }
    else if (tab.value === 'artist') { await startArtist(); conv = convs.artist }
    if (!conv) return
  }
  if (conv.status === 1) return
  field.value = ''
  busy.value = true
  /* 乐观上屏：用户消息即刻可见，AI 渠道追加 typing 气泡 */
  conv.messages.push({ id: --msgSeq, sender: 1, content: v, created_at: new Date().toISOString() })
  scrollBottom()
  if (conv.channel === 0) typing.value = true
  try {
    const d = await req('POST', `/api/chat/conversations/${conv.conv_no}/messages`, { token: ensureToken(), content: v })
    applyDetail(d)
    suggestions.value = d.suggestions || []
    /* AI 内部升级转人工（human 意图 + 邮箱齐备）：同会话保留，仅状态提示变化 */
  } catch (e) {
    conv.messages.push({
      id: --msgSeq, sender: 3, content: i18n.t('chat.sendFail') + '—— ' + ((e && e.message) || ''), created_at: new Date().toISOString(),
    })
  } finally {
    typing.value = false
    busy.value = false
    scrollBottom()
  }
}

function askText(text) {
  if (busy.value) return
  if (tab.value !== 'chat') switchTab('chat')
  field.value = text
  send()
}

function sugClick(e) {
  const t = e.target
  if (t && t.dataset && t.dataset.q && !busy.value) askText(t.dataset.q)
}
</script>

<template>
  <button class="chat-fab" :class="{ active: open }" :aria-label="i18n.t('aria.chat')" @click="toggle()">
    <svg class="chat-ico-bubble" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/><path d="M8.5 10.5h.01M12 10.5h.01M15.5 10.5h.01" stroke-width="2.4"/></svg>
    <svg class="chat-ico-x" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
    <span class="chat-dot"></span>
  </button>
  <div class="chat-panel" :class="{ open }" role="dialog" :aria-label="i18n.t('chat.title')">
    <div class="chat-head">
      <div class="chat-head-top">
        <div>
          <b>{{ i18n.t('chat.title') }}</b>
          <div class="chat-status"><i></i>{{ i18n.t('chat.status') }}</div>
        </div>
        <button :aria-label="i18n.t('aria.chatClose')" style="color:#fff;font-size:20px;opacity:.8" @click="toggle()">×</button>
      </div>
      <div class="chat-tabs" role="tablist">
        <button v-for="[k, key] in TABS" :key="k" role="tab" :aria-selected="tab === k" :class="{ on: tab === k }" @click="switchTab(k)">{{ i18n.t(key) }}</button>
      </div>
    </div>

    <div class="chat-body" id="chatMsgs" role="log" aria-live="polite">
      <!-- 合并客服 tab：AI 应答 ↔ 人工接管 状态条 -->
      <template v-if="tab === 'chat' && curConv()">
        <div v-if="curConv().channel === 1 && !curConv().agent_admin_id && curConv().status === 0" class="chat-notice">⏳ {{ i18n.t('chat.human.waiting') }}</div>
        <div v-else-if="curConv().channel === 1 && curConv().agent_name" class="chat-notice ok">👩‍💼 {{ curConv().agent_name }} · {{ i18n.t('chat.human.serving') }}</div>
      </template>

      <!-- 会话消息（两 tab 共用） -->
      <template v-if="curConv()">
        <div v-if="tab === 'artist' && curConv().artist_name" class="chat-notice ok">💅 {{ curConv().artist_name }}</div>
        <template v-for="m in curMsgs()" :key="m.id">
          <div v-if="m.sender === 3" class="chat-sys">{{ m.content }}</div>
          <div v-else class="chat-row" :class="{ me: m.sender === 1 }">
            <span v-if="m.sender !== 1" class="chat-ava">{{ SENDER_AVA[m.sender] || '💬' }}</span>
            <div class="chat-msg" :class="m.sender === 1 ? 'user' : 'bot'">
              <div v-if="m.sender !== 1 && m.sender_name" class="chat-who">{{ m.sender_name }}</div>
              <!-- eslint-disable-next-line vue/no-v-html -->
              <span v-html="md(m.content)" @click="sugClick" />
              <span class="chat-time">{{ fmtTime(m.created_at) }}</span>
            </div>
          </div>
        </template>
        <div v-if="typing" class="chat-row"><span class="chat-ava">🤖</span><div class="chat-msg bot typing"><span class="tdots"><i></i><i></i><i></i></span></div></div>
        <div v-if="tab === 'chat' && curConv().channel === 0 && suggestions.length" class="chat-sugs">
          <button v-for="s in suggestions.slice(0, 3)" :key="s" class="chat-quick" :data-q="s" @click="askText(s)">{{ s }}</button>
        </div>
      </template>

      <!-- 转人工中转：游客补邮箱（内嵌表单，确认后原地升级） -->
      <div v-if="tab === 'chat' && wantHuman" class="chat-form">
        <div class="chat-intro" style="padding:6px 0 2px">
          <b>{{ i18n.t('chat.human.escT') }}</b>
          <p>{{ i18n.t('chat.human.escNote') }}</p>
        </div>
        <input v-model="contact.name" class="chat-field" :placeholder="i18n.t('chat.contact.name')">
        <input v-model="contact.email" class="chat-field" type="email" :placeholder="i18n.t('chat.contact.email')">
        <div v-if="contactErr" class="chat-err">{{ contactErr }}</div>
        <div style="display:flex;gap:8px">
          <button class="chat-go" style="flex:1" :disabled="busy" @click="doEscalate">{{ i18n.t('chat.esc') }}</button>
          <button type="button" class="chat-quick end" style="height:40px;flex:none;padding:0 16px" @click="cancelEscalate">{{ i18n.t('chat.cancel') }}</button>
        </div>
      </div>

      <!-- 美甲师引导（选择卡片） -->
      <template v-if="tab === 'artist' && !convs.artist">
        <div class="chat-intro">
          <div class="chat-intro-ico">💅</div>
          <b>{{ i18n.t('chat.artist.introT') }}</b>
          <p>{{ i18n.t('chat.artist.intro') }}</p>
        </div>
        <div v-if="!artistsLoaded" class="chat-tip">…</div>
        <button v-else-if="!artists.length" class="chat-go" @click="loadArtists">{{ i18n.t('chat.retry') }}</button>
        <template v-else>
          <div class="chat-artist-grid">
            <button v-for="a in artists" :key="a.id" class="chat-artist-card" :class="{ on: pickArtist && pickArtist.id === a.id }" @click="pickArtist = a">
              <span class="chat-artist-ava">💅</span>
              <b>{{ a.name }}</b>
              <p>{{ a.intro }}</p>
            </button>
          </div>
          <div v-if="needContact() && pickArtist" class="chat-form">
            <input v-model="contact.name" class="chat-field" :placeholder="i18n.t('chat.contact.name')">
            <input v-model="contact.email" class="chat-field" type="email" :placeholder="i18n.t('chat.contact.email')">
            <div v-if="contactErr" class="chat-err">{{ contactErr }}</div>
            <button class="chat-go" :disabled="busy" @click="startArtist">{{ i18n.t('chat.artist.chat') }}</button>
          </div>
          <button v-else-if="pickArtist" class="chat-go" :disabled="busy" @click="startArtist">{{ i18n.t('chat.artist.chat') }}</button>
        </template>
      </template>

      <div v-if="loadErr" class="chat-err">
        {{ i18n.t('chat.loadErr') }}
        <button class="chat-quick" style="display:block;margin:8px auto 0" @click="retryInit">{{ i18n.t('chat.retry') }}</button>
      </div>
    </div>

    <div v-if="curConv()" class="chat-quicks">
      <!-- 合并客服：AI 态给后台配置的快捷问题+转人工；人工态给结束 -->
      <template v-if="tab === 'chat' && curConv().channel === 0">
        <button v-for="(q, i) in quickItems()" :key="i" class="chat-quick" :class="{ esc: q.action === 'human' }" @click="tapQuick(q)">
          {{ q.text }}<span v-if="q.action === 'link'" style="opacity:.6"> ↗</span>
        </button>
      </template>
      <button v-if="curConv().status === 0" class="chat-quick end" :disabled="busy" @click="endChat">✕ {{ i18n.t('chat.close') }}</button>
    </div>
    <form v-if="curConv()" class="chat-input" @submit.prevent="send">
      <input v-model="field" ref="inputEl" :placeholder="i18n.t('chat.placeholder')" :aria-label="i18n.t('chat.placeholder')" autocomplete="off">
      <button type="submit" :aria-label="i18n.t('chat.send')" :disabled="busy">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      </button>
    </form>
  </div>
</template>
