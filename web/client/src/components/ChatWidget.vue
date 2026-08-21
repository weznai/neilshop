<script setup>
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { i18n } from '../i18n'
import { req } from '../api/client'
import { useUiStore } from '../stores/ui'

const router = useRouter()
const ui = useUiStore()
const open = ref(false)
const greeted = ref(false)
const busy = ref(false)
const msgs = ref([]) /* {id, who:'user'|'bot', html, typing} */
const field = ref('')
const inputEl = ref(null)
const lastAsk = ref(null) /* {q, key} 失败重试 */
const QUICKS = ['track', 'size', 'return', 'human']
const HIST_KEY = 'gm_chat_hist'
const HIST_MAX = 30 /* 最近 N 条持久化（含问答双方） */
let msgSeq = 0 /* 稳定 key：避免 v-for 用 idx（历史裁剪/typing 增删导致错位复用） */

/* 纳入全局 ESC（capture 阶段先于 App 的 document 委托）：其它浮层（drawer/search/mnav/modal）
   开着时跳过自己，让全局先关浮层；仅面板独立在场时才自关并阻断后续监听 */
function onEsc(e) {
  if (e.key !== 'Escape' || !open.value) return
  if (ui.cartDrawer || ui.mnavOpen || ui.searchOpen || ui.openModalId) return
  e.stopPropagation()
  open.value = false
}

/* 面板开合上报 ui store：body 滚动锁由 StoreLayout 统一 watch anyOverlay 处理 */
watch(open, (v) => { ui.chatOpen = v })

const shipQ = () => (i18n.lang === 'zh' ? '🚚 运费与配送时效？' : '🚚 Shipping cost & delivery time?')

onMounted(() => {
  window.addEventListener('keydown', onEsc, true)
  try {
    const saved = JSON.parse(localStorage.getItem(HIST_KEY) || '[]')
    if (Array.isArray(saved) && saved.length) {
      msgs.value = saved
        .filter((m) => m && m.who && typeof m.html === 'string')
        .slice(-HIST_MAX)
        .map((m) => ({ ...m, id: ++msgSeq }))
      greeted.value = true
    }
  } catch (_) { msgs.value = [] }
})
onUnmounted(() => { window.removeEventListener('keydown', onEsc, true); ui.chatOpen = false })

watch(msgs, () => {
  const keep = msgs.value.filter((m) => !m.typing).slice(-HIST_MAX)
  try { localStorage.setItem(HIST_KEY, JSON.stringify(keep)) } catch (_) { /* 隐私模式等写入失败即弃 */ }
}, { deep: true })

function scrollBottom() {
  nextTick(() => {
    const b = document.getElementById('chatMsgs')
    if (b) b.scrollTop = b.scrollHeight
  })
}

async function toggle() {
  open.value = !open.value
  if (open.value && !greeted.value) {
    greeted.value = true
    botSay(i18n.t('chat.hello'), 0)
  }
  if (open.value) {
    scrollBottom()
    setTimeout(() => inputEl.value?.focus(), 250)
  }
}

function match(text) {
  const t = text.toLowerCase()
  if (/(shipping|运费|配送|邮寄|清关)/i.test(t)) return 'shipping'
  if (/(track|order|where|package|deliver|shipped|订单|物流|快递|包裹|到哪|发货)/i.test(t)) return 'track'
  if (/(size|fit|measure|尺码|尺寸|选码|大小|合适)/i.test(t)) return 'size'
  if (/(return|refund|exchange|退|换|退款)/i.test(t)) return 'return'
  if (/(human|agent|staff|person|人工|客服|真人|投诉)/i.test(t)) return 'human'
  if (/(cart|basket|购物车)/i.test(t)) return 'cart'
  if (/(code|coupon|discount|promo|折扣|优惠|码|券)/i.test(t)) return 'code'
  return 'fallback'
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
function push(who, html) {
  msgs.value.push({ id: ++msgSeq, who, html })
  scrollBottom()
}
function botSay(html, delay = 700) {
  if (delay > 0) {
    msgs.value.push({ id: ++msgSeq, who: 'bot', typing: true })
    setTimeout(() => {
      msgs.value = msgs.value.filter((m) => !m.typing)
      push('bot', html)
    }, delay)
  } else push('bot', html)
}
function localReply(key) {
  const t = i18n.t('chat.r.' + key)
  return t === 'chat.r.' + key ? i18n.t('chat.r.fallback') : t
}
async function botApi(message, localKey) {
  busy.value = true
  try {
    const d = await req('POST', '/api/ai/chat', { message })
    let html = md(d.reply)
    if (Array.isArray(d.suggestions) && d.suggestions.length) {
      html += `<div class="chat-sugs" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">` +
        d.suggestions.slice(0, 3).map((s) => `<button class="chat-quick" data-q="${esc(s)}">${esc(s)}</button>`).join('') +
        `</div>`
    }
    botSay(html)
  } catch (_) {
    const lbl = i18n.lang === 'zh' ? '↻ 重试' : '↻ Retry'
    botSay(localReply(localKey) +
      `<div style="margin-top:8px"><button class="chat-quick" data-retry="1">${lbl}</button></div>`)
  } finally {
    busy.value = false
  }
}
function askText(text, key) {
  if (busy.value) return
  push('user', esc(text))
  lastAsk.value = { q: text, key }
  botApi(text, key)
}
function ask(key) {
  askText(i18n.t('chat.q.' + key), key)
}
function retryLast() {
  if (busy.value || !lastAsk.value) return
  botApi(lastAsk.value.q, lastAsk.value.key)
}
function sugClick(e) {
  const t = e.target
  if (!t || !t.dataset) return
  if (t.dataset.retry) { retryLast(); return }
  if (t.dataset.q && !busy.value) {
    field.value = t.dataset.q
    send()
  }
}
function goContact() {
  open.value = false
  router.push('/contact')
}
function send() {
  const v = field.value.trim()
  if (!v || busy.value) return
  field.value = ''
  push('user', esc(v))
  lastAsk.value = { q: v, key: match(v) }
  botApi(v, lastAsk.value.key)
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
      <div>
        <b>{{ i18n.t('chat.title') }}</b>
        <div class="chat-status"><i></i>{{ i18n.t('chat.status') }}</div>
      </div>
      <button :aria-label="i18n.t('aria.chatClose')" style="color:#fff;font-size:20px;opacity:.8" @click="toggle()">×</button>
    </div>
    <div class="chat-body" id="chatMsgs" role="log" aria-live="polite">
      <div v-for="m in msgs" :key="m.id" class="chat-msg" :class="m.who">
        <span v-if="m.typing" class="tdots"><i></i><i></i><i></i></span>
        <template v-else><!-- eslint-disable-next-line vue/no-v-html -->
          <span v-html="m.html" @click="sugClick" /></template>
      </div>
    </div>
    <div class="chat-quicks">
      <button v-for="k in QUICKS" :key="k" class="chat-quick" @click="ask(k)">{{ i18n.t('chat.q.' + k) }}</button>
      <button class="chat-quick" @click="askText(shipQ(), 'shipping')">{{ i18n.lang === 'zh' ? '🚚 运费/时效' : '🚚 Shipping' }}</button>
      <button class="chat-quick" @click="goContact">🎫 {{ i18n.lang === 'zh' ? '提交工单' : 'Open a ticket' }}</button>
    </div>
    <form class="chat-input" @submit.prevent="send">
      <input v-model="field" ref="inputEl" :placeholder="i18n.t('chat.placeholder')" :aria-label="i18n.t('chat.placeholder')" autocomplete="off">
      <button type="submit" :aria-label="i18n.t('chat.send')" :disabled="busy">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      </button>
    </form>
  </div>
</template>
