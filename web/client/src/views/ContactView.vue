<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { errMessage, req } from '../api/client'
import { fmtDateTime } from '../composables/datetime'
import { useArmConfirm } from '../composables/useArmConfirm'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'
import { i18n, tt } from '../i18n'

const route = useRoute()
const ui = useUiStore()
const auth = useAuthStore()

/* TicketCategory（server/app/core/enums.py）：1物流 2质量 3退换 4账户 5售前 6其他 */
const CATEGORIES = [
  [1, '🚚 Shipping & delivery', '🚚 物流与配送'],
  [2, '💎 Product quality', '💎 商品质量'],
  [3, '↩️ Returns & exchanges', '↩️ 退换货'],
  [4, '👤 Account & points', '👤 账户与积分'],
  [5, '💬 Pre-sale questions', '💬 售前咨询'],
  [6, '✨ Other', '✨ 其他'],
]
/* TicketStatus：0新建 1已回复 2等待用户回复 3已解决 4已关闭 */
const STATUS = {
  0: ['Open', '待处理', 'tag-pending'],
  1: ['Replied', '已回复', 'tag-paid'],
  2: ['Awaiting your reply', '等待你回复', 'tag-ship'],
  3: ['Resolved', '已解决', 'tag-paid'],
  4: ['Closed', '已关闭', 'tag-done'],
}
const mode = ref('new')
const busy = ref(false)

const form = ref({ email: '', order_no: '', category: 1, subject: '', content: '' })
const errors = ref({})
const created = ref(null)
const templates = ref([])

const lookup = ref({ email: '', ticket_no: '' })
const tickets = ref(null)
const lookupBusy = ref(false)
const lookupErr = ref('')
const replyBox = ref('')
const replyBusy = ref(false)
const activeNo = ref('')

const activeTicket = computed(() => {
  const list = tickets.value || []
  if (!list.length) return null
  return list.find((t) => t.ticket_no === activeNo.value) || list[0]
})
function statusLabelOf(t) {
  const s = STATUS[t.status] || ['In progress', '处理中']
  return tt(s[0], s[1])
}
function statusTagOf(t) { return (STATUS[t.status] || [])[2] || 'tag-ship' }
function catLabel(c) {
  const row = CATEGORIES.find((x) => x[0] === c)
  return row ? tt(row[1], row[2]) : tt('Other', '其他')
}
const fmtTime = (s) => (s ? fmtDateTime(s, '') : '')

/* 模板按类目内存缓存 + 序列守卫（快速切换类目时丢弃过期响应） */
const tplCache = new Map()
let tplSeq = 0
async function loadTemplates(cat) {
  if (tplCache.has(cat)) { templates.value = tplCache.get(cat); return }
  const seq = ++tplSeq
  try {
    const d = await req('GET', '/api/support/templates?category=' + cat) || []
    if (seq !== tplSeq) return
    tplCache.set(cat, d)
    templates.value = d
  } catch (_) { if (seq === tplSeq) templates.value = [] }
}
watch(() => form.value.category, (c) => loadTemplates(c), { immediate: true })

const tplArm = useArmConfirm()
function applyTpl(t) {
  form.value.content = t.content
  if (!form.value.subject.trim()) form.value.subject = t.title
}
function useTpl(t) {
  if (!form.value.content.trim()) { applyTpl(t); return }
  tplArm.hit('tpl-' + t.id, () => applyTpl(t))
}

function validate() {
  const f = form.value
  const e = {}
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim())) e.email = tt('Enter a valid email — replies land here', '请输入有效邮箱，回复将发送至此')
  if (!f.subject.trim()) e.subject = tt('A short subject helps us route your ticket', '请填写简短主题，便于快速分派')
  if (f.content.trim().length < 5) e.content = tt('Tell us a little more (at least 5 characters)', '再多说一点吧（至少 5 个字符）')
  if (f.order_no && !/^[A-Za-z0-9]{6,20}$/.test(f.order_no.trim())) e.order_no = tt('Order numbers look like NS260728XXXXXX', '订单号形如 NS260728XXXXXX')
  errors.value = e
  return !Object.keys(e).length
}

async function submit() {
  if (!validate()) return
  busy.value = true
  try {
    const f = form.value
    const d = await req('POST', '/api/support/tickets', {
      email: f.email.trim(),
      order_no: f.order_no.trim() || null,
      category: f.category,
      subject: f.subject.trim(),
      content: f.content.trim(),
    })
    created.value = d
    ui.toast(tt('Ticket created', '工单已创建'), 'success')
  } catch (e) {
    ui.toast(e.status === 422 ? errMessage(e) : tt('Submit failed — please retry', '提交失败，请稍后再试'), 'error')
  } finally { busy.value = false }
}

function resetForm() {
  created.value = null
  form.value.subject = ''
  form.value.content = ''
  errors.value = {}
}

async function copyNo(no) {
  try { await navigator.clipboard.writeText(no) } catch (_) {
    const ta = document.createElement('textarea')
    ta.value = no; document.body.appendChild(ta); ta.select()
    try { document.execCommand('copy') } catch (__) { /* noop */ }
    document.body.removeChild(ta)
  }
  ui.toast(no + ' ' + tt('copied', '已复制'), 'success')
}

function goLookup() {
  lookup.value.email = created.value ? form.value.email : lookup.value.email
  if (created.value) lookup.value.ticket_no = created.value.ticket_no
  mode.value = 'check'
  query()
}

async function query() {
  let l = lookup.value
  lookupErr.value = ''
  /* 登录态锁定账户邮箱查询（后端校验 email 须与账户一致，异邮箱恒 403） */
  if (auth.isLoggedIn && auth.user) {
    l.email = String(auth.user.email || '')
    l.ticket_no = ''
  }
  if (!l.email.trim()) {
    lookupErr.value = tt('Enter the email used on the ticket.', '请填写创建工单时使用的邮箱')
    return
  }
  if (!auth.isLoggedIn && !l.ticket_no.trim()) {
    lookupErr.value = tt('Ticket number (TK…) is needed — or sign in to see all your tickets.', '未登录需提供工单号（TK…），或登录后按账户邮箱查看全部工单')
    return
  }
  lookupBusy.value = true
  tickets.value = null
  activeNo.value = ''
  try {
    let url = '/api/support/tickets?email=' + encodeURIComponent(l.email.trim())
    if (!auth.isLoggedIn) url += '&ticket_no=' + encodeURIComponent(l.ticket_no.trim())
    const d = await req('GET', url)
    tickets.value = d.items || []
    if (!tickets.value.length) lookupErr.value = tt('No ticket found with that combination.', '未找到符合条件的工单')
  } catch (e) {
    const d = e && e.data && e.data.detail
    if (e && e.status === 404) lookupErr.value = tt('Ticket not found — check the number (TK…) and the email you used.', '未找到工单——请核对工单号（TK…）与创建邮箱')
    else lookupErr.value = tt('Could not load the conversation — please retry.', '加载失败，请稍后再试')
  } finally { lookupBusy.value = false }
}

async function sendReply() {
  const t = activeTicket.value
  const v = replyBox.value.trim()
  if (!t || !v) return
  replyBusy.value = true
  try {
    await req('POST', `/api/support/tickets/${encodeURIComponent(t.ticket_no)}/messages`, {
      email: lookup.value.email.trim(),
      content: v,
    })
    replyBox.value = ''
    await query()
  } catch (e) {
    /* 422：TicketMessageIn.content max_length=2000（maxlength 已挡输入，兜底提示） */
    ui.toast(e.status === 409 ? tt('This ticket is closed — please open a new one', '该工单已关闭，请提交新工单') : e.status === 422 ? tt('Message too long (max 2000 characters)', '内容过长（最多 2000 字）') : tt('Could not send — please retry', '发送失败，请稍后再试'), 'error')
  } finally { replyBusy.value = false }
}

onMounted(() => {
  if (route.query.subject) form.value.subject = String(route.query.subject).slice(0, 80)
  if (route.query.email) form.value.email = String(route.query.email).slice(0, 80)
  else if (auth.user && auth.user.email) form.value.email = auth.user.email
  if (auth.user && auth.user.email) lookup.value.email = auth.user.email
  if (route.query.ticket_no) {
    lookup.value.ticket_no = String(route.query.ticket_no).slice(0, 20)
    mode.value = 'check'
  }
})
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:680px">
      <div class="section-head"><h1 class="section-title">{{ tt('Contact Us 💬', '联系我们 💬') }}</h1></div>

      <div style="display:flex;gap:8px;margin-bottom:18px">
        <button class="trend-chip" :class="{ on: mode === 'new' }" :aria-pressed="mode === 'new'" @click="mode = 'new'">✍️ {{ tt('New ticket', '新建工单') }}</button>
        <button class="trend-chip" :class="{ on: mode === 'check' }" :aria-pressed="mode === 'check'" @click="mode = 'check'">💬 {{ tt('Check my ticket', '查询我的工单') }}</button>
      </div>

      <div class="card" style="padding:12px 16px;margin-bottom:18px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:13px;color:var(--gray)">
        <span>✉️ support@glowmag.com</span>
        <span class="meta-dot" />
        <span>{{ tt('Mon–Sat 9–18 ET', '周一至周六 9–18（美东）') }}</span>
        <button class="btn btn-secondary btn-sm" style="margin-left:auto;height:30px;padding:0 12px" @click="ui.chatOpen = true">{{ tt('Chat online', '在线聊天') }}</button>
      </div>

      <div v-if="mode === 'new'">
        <div v-if="created" class="card" style="padding:28px;text-align:center">
          <div style="width:56px;height:56px;border-radius:50%;background:var(--rose-pale);color:var(--plum);font-size:26px;display:inline-flex;align-items:center;justify-content:center;margin-bottom:12px">✓</div>
          <h2 style="font-family:var(--font-title);font-size:20px;margin-bottom:6px">{{ tt('Ticket received!', '工单已收到！') }}</h2>
          <p style="font-size:13.5px;color:var(--gray);margin-bottom:14px">
            {{ tt('Average first reply: under 4 hours (Mon–Sat). Save your ticket number:', '平均 4 小时内首次回复（周一至周六）。请保存工单号：') }}
          </p>
          <div style="display:inline-flex;align-items:center;gap:10px;background:var(--rose-pale);border-radius:10px;padding:10px 16px;margin-bottom:18px">
            <b style="font-size:18px;letter-spacing:1px;color:var(--plum)">{{ created.ticket_no }}</b>
            <button class="btn btn-secondary btn-sm" style="height:30px;padding:0 12px" @click="copyNo(created.ticket_no)">{{ tt('Copy', '复制') }}</button>
          </div>
          <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
            <button class="btn btn-primary btn-sm" @click="goLookup">{{ tt('View conversation', '查看对话') }}</button>
            <button class="btn btn-ghost btn-sm" @click="resetForm">{{ tt('Open another ticket', '再提一个工单') }}</button>
          </div>
        </div>

        <div v-else class="card" style="padding:24px">
          <div class="field" :class="{ error: errors.email }">
            <label>{{ tt('Email', '邮箱') }} *</label>
            <input v-model="form.email" class="input" :class="{ error: errors.email }" type="email" autocomplete="email" placeholder="you@example.com" @input="errors.email = ''">
            <div class="field-msg">{{ errors.email }}</div>
          </div>
          <div class="field" :class="{ error: errors.order_no }">
            <label>{{ tt('Order number', '订单号') }} <span style="color:var(--gray);font-weight:400">({{ tt('optional — speeds things up', '选填，可加快处理') }})</span></label>
            <input v-model="form.order_no" class="input" :class="{ error: errors.order_no }" placeholder="NS260728XXXXXX" autocomplete="off" @input="errors.order_no = ''">
            <div class="field-msg">{{ errors.order_no }}</div>
          </div>
          <div class="field">
            <label>{{ tt('Category', '工单类目') }} *</label>
            <select v-model="form.category" class="input">
              <option v-for="[v, en, zh] in CATEGORIES" :key="v" :value="v">{{ tt(en, zh) }}</option>
            </select>
          </div>
          <div class="field" :class="{ error: errors.subject }">
            <label>{{ tt('Subject', '主题') }} *</label>
            <input v-model="form.subject" class="input" :class="{ error: errors.subject }" maxlength="80" :placeholder="tt('Short summary, e.g. Wrong size in my set', '简短概述，例如：套装尺码不对')" @input="errors.subject = ''">
            <div class="field-msg">{{ errors.subject }}</div>
          </div>
          <div v-if="templates.length" style="margin-bottom:14px">
            <div style="font-size:12px;font-weight:700;color:var(--gray);text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px">{{ tt('Quick starters', '快捷模板') }}</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              <button v-for="t in templates" :key="t.id" class="trend-chip" :class="{ arm: tplArm.is('tpl-' + t.id) }" @click="useTpl(t)">{{ tplArm.is('tpl-' + t.id) ? tt('Tap again to replace', '再点一次替换') : t.title }}</button>
            </div>
          </div>
          <div class="field" :class="{ error: errors.content }">
            <label>{{ tt('Message', '留言内容') }} *</label>
            <textarea v-model="form.content" class="input" :class="{ error: errors.content }" rows="5" maxlength="2000" style="height:auto;padding-top:10px" :placeholder="tt('How can we help? Include sizes, order details or anything handy.', '我们能帮你什么？可附上尺码、订单信息等细节。')" @input="errors.content = ''"></textarea>
            <div class="field-msg" style="display:flex;justify-content:flex-between"><span>{{ errors.content }}</span><span style="color:var(--gray)">{{ form.content.length }}/2000</span></div>
          </div>
          <button class="btn btn-primary" :class="{ loading: busy }" :disabled="busy" @click="submit">{{ tt('Send message', '发送留言') }}</button>
          <p style="font-size:12.5px;color:var(--gray);margin-top:12px">
            {{ tt('No account needed — follow the whole conversation with your email + ticket number.', '无需注册账号——用邮箱 + 工单号即可跟进整个对话。') }}
          </p>
        </div>
      </div>

      <div v-else class="card" style="padding:24px">
        <div class="lk-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field">
            <label>{{ tt('Email', '邮箱') }}</label>
            <input v-model="lookup.email" class="input" type="email" autocomplete="email" :disabled="auth.isLoggedIn || tickets !== null || lookupBusy" :placeholder="tt('Email used on the ticket', '创建工单时使用的邮箱')">
          </div>
          <div v-if="!auth.isLoggedIn" class="field">
            <label>{{ tt('Ticket number', '工单号') }}</label>
            <input v-model="lookup.ticket_no" class="input" placeholder="TK260728XXXX" autocomplete="off" :disabled="tickets !== null || lookupBusy">
          </div>
        </div>
        <p v-if="auth.isLoggedIn" style="font-size:12.5px;color:var(--gray);margin:6px 0 0">
          {{ tt('Signed in — this lookup covers tickets from your account email. To check tickets made with another email, please sign out first.', '登录状态下查询当前账户的工单；如需查询其他邮箱的工单请退出登录。') }}
        </p>
        <button class="btn btn-primary" :class="{ loading: lookupBusy }" :disabled="lookupBusy" style="margin-top:12px" @click="query">{{ tt('Find my ticket', '查询工单') }}</button>
        <div v-if="lookupErr" style="font-size:13px;color:var(--error);margin-top:10px">{{ lookupErr }}</div>

        <div v-if="lookupBusy" class="skeleton" style="min-height:180px;margin-top:16px" />

        <template v-else-if="activeTicket">
          <div v-if="tickets.length > 1" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:16px">
            <button
              v-for="t in tickets" :key="t.ticket_no" class="trend-chip" :class="{ on: activeTicket.ticket_no === t.ticket_no }" :aria-pressed="activeTicket.ticket_no === t.ticket_no"
              @click="activeNo = t.ticket_no"
            >{{ t.ticket_no }}</button>
          </div>

          <div style="border-top:1px solid var(--gray-light);margin-top:20px;padding-top:18px">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px">
              <b style="font-size:15px">{{ activeTicket.subject }}</b>
              <span class="tag" :class="statusTagOf(activeTicket)">{{ statusLabelOf(activeTicket) }}</span>
            </div>
            <div style="font-size:12.5px;color:var(--gray);margin-bottom:16px">
              {{ activeTicket.ticket_no }} · {{ catLabel(activeTicket.category) }}
              <template v-if="activeTicket.order_no"> · {{ tt('Order', '订单') }} {{ activeTicket.order_no }}</template>
              · {{ tt('Opened', '创建于') }} {{ fmtTime(activeTicket.created_at) }}
            </div>

            <div style="display:grid;gap:10px">
              <div
                v-for="m in activeTicket.messages" :key="m.id"
                style="max-width:85%;padding:10px 14px;border-radius:14px;font-size:13.5px;line-height:1.6"
                :style="m.sender === 1
                  ? 'justify-self:end;background:var(--plum);color:#fff;border-bottom-right-radius:4px'
                  : 'justify-self:start;background:var(--rose-pale);color:var(--ink);border-bottom-left-radius:4px'"
              >
                <div style="font-size:10.5px;opacity:.75;margin-bottom:3px;font-weight:700">
                  {{ m.sender === 1 ? tt('You', '我') : 'GLOWMAG ' + tt('Support', '客服') }} · {{ fmtTime(m.created_at) }}
                </div>
                {{ m.content }}
              </div>
            </div>

            <div v-if="activeTicket.status === 4" style="margin-top:16px;font-size:13px;color:var(--gray);background:var(--gray-light);border-radius:10px;padding:12px 14px">
              🔒 {{ tt('This ticket is closed. Need more help?', '该工单已关闭。还需要帮助？') }}
              <a style="color:var(--plum);font-weight:600;cursor:pointer" @click.prevent="mode = 'new'; created = null">{{ tt('Open a new ticket', '提交新工单') }}</a>.
            </div>
            <div v-else-if="activeTicket.status === 2" style="margin-top:14px;font-size:12.5px;color:var(--warn)">
              ⏳ {{ tt('Our team is waiting for your reply below.', '客服正在等待你的回复，请在下方继续对话。') }}
            </div>
            <div v-else style="margin-top:16px">
              <textarea v-model="replyBox" class="input" rows="3" maxlength="2000" style="height:auto;padding-top:10px" :placeholder="tt('Add a reply — it goes straight to our team', '追加回复——直达客服团队')"></textarea>
              <button class="btn btn-primary btn-sm" :class="{ loading: replyBusy }" :disabled="replyBusy || !replyBox.trim()" style="margin-top:10px" @click="sendReply">{{ tt('Send reply', '发送回复') }}</button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
@media (max-width: 640px) {
  .lk-grid { grid-template-columns: 1fr !important; }
}
</style>
