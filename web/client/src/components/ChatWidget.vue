<script setup>
import { nextTick, ref } from 'vue'
import { i18n } from '../i18n'
import { req } from '../api/client'

const open = ref(false)
const greeted = ref(false)
const msgs = ref([]) /* {who:'user'|'bot', html, typing} */
const field = ref('')
const inputEl = ref(null)
const QUICKS = ['track', 'size', 'return', 'human']

async function toggle() {
  open.value = !open.value
  if (open.value && !greeted.value) {
    greeted.value = true
    botSay(i18n.t('chat.hello'), 0)
  }
  if (open.value) setTimeout(() => inputEl.value?.focus(), 250)
}

function match(text) {
  const t = text.toLowerCase()
  if (/(track|order|where|package|deliver|shipped|订单|物流|快递|包裹|到哪|发货)/i.test(t)) return 'track'
  if (/(size|fit|measure|尺码|尺寸|选码|大小|合适)/i.test(t)) return 'size'
  if (/(return|refund|exchange|退|换|退款)/i.test(t)) return 'return'
  if (/(human|agent|staff|person|人工|客服|真人|投诉)/i.test(t)) return 'human'
  if (/(cart|basket|购物车)/i.test(t)) return 'cart'
  if (/(code|coupon|discount|promo|折扣|优惠|码|券)/i.test(t)) return 'code'
  return 'fallback'
}
function md(s) {
  return String(s || '')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1')
    .replace(/[*_`#>]/g, '')
    .replace(/\r/g, '')
    .replace(/\n{2,}/g, '<br><br>')
    .replace(/\n/g, '<br>')
}
function push(who, html) {
  msgs.value.push({ who, html })
  nextTick(() => {
    const b = document.getElementById('chatMsgs')
    if (b) b.scrollTop = b.scrollHeight
  })
}
function botSay(html, delay = 700) {
  if (delay > 0) {
    msgs.value.push({ who: 'bot', typing: true })
    setTimeout(() => {
      msgs.value = msgs.value.filter((m) => !m.typing)
      push('bot', html)
    }, delay)
  } else push('bot', html)
}
async function botApi(message, localKey) {
  try {
    const d = await req('POST', '/api/ai/chat', { message })
    let html = md(d.reply)
    if (Array.isArray(d.suggestions) && d.suggestions.length) {
      html += `<div class="chat-sugs" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">` +
        d.suggestions.slice(0, 3).map((s) => `<button class="chat-quick" data-q="${String(s).replace(/"/g, '&quot;')}">${s}</button>`).join('') +
        `</div>`
    }
    botSay(html)
  } catch (_) {
    botSay(i18n.t('chat.r.' + localKey))
  }
}
function ask(key) {
  const q = i18n.t('chat.q.' + key)
  push('user', q)
  botApi(q, key)
}
function sugClick(e) {
  const q = e.target && e.target.dataset ? e.target.dataset.q : null
  if (q) sug(e)
}
function sug(e) {
  field.value = e.target.dataset.q
  send()
}
function send() {
  const v = field.value.trim()
  if (!v) return
  field.value = ''
  push('user', v)
  botApi(v, match(v))
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
    <div class="chat-body" id="chatMsgs">
      <div v-for="(m, idx) in msgs" :key="idx" class="chat-msg" :class="m.who">
        <span v-if="m.typing" class="tdots"><i></i><i></i><i></i></span>
        <template v-else><!-- eslint-disable-next-line vue/no-v-html -->
          <span v-html="m.html" @click="sugClick" /></template>
      </div>
    </div>
    <div class="chat-quicks">
      <button v-for="k in QUICKS" :key="k" class="chat-quick" @click="ask(k)">{{ i18n.t('chat.q.' + k) }}</button>
    </div>
    <form class="chat-input" @submit.prevent="send">
      <input v-model="field" ref="inputEl" :placeholder="i18n.t('chat.placeholder')" autocomplete="off">
      <button type="submit" :aria-label="i18n.t('chat.send')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      </button>
    </form>
  </div>
</template>
