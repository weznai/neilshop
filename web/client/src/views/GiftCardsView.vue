<script setup>
import { computed, onMounted, ref } from 'vue'
import { i18n } from '../i18n'
import { errMessage, intentNoChannel, req } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'
import { fmtDate } from '../composables/datetime'

const auth = useAuthStore()
const ui = useUiStore()

const zh = computed(() => i18n.lang === 'zh')
const t = (en, cn) => (zh.value ? cn : en)
const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

/* 后端 GiftcardPurchaseIn.amount_cents 枚举：2500 / 5000 / 10000 */
const AMOUNTS = [2500, 5000, 10000]
const amountC = ref(5000)
const purchaser = ref('')
const recipient = ref('')
const msg = ref('')
const busy = ref(false)
const paying = ref(false)

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/* 购买结果：{code, order_no, amount_cents, status}，status 0=待支付激活 1=已激活 */
const result = ref(null)
const paid = ref(false)
const copied = ref(false)

/* 待付礼品卡订单暂存（hosted 支付跳转回来后可恢复待付卡继续支付） */
const GC_DRAFT_KEY = 'gm_last_gc_order'
function saveGcDraft() {
  if (!result.value) return
  try {
    localStorage.setItem(GC_DRAFT_KEY, JSON.stringify({
      code: result.value.code, order_no: result.value.order_no,
      amount_cents: result.value.amount_cents, email: purchaser.value.trim(),
    }))
  } catch (_) { /* 隐私模式 */ }
}
function clearGcDraft() { try { localStorage.removeItem(GC_DRAFT_KEY) } catch (_) { /* 隐私模式 */ } }

onMounted(async () => {
  if (auth.user && auth.user.email) purchaser.value = auth.user.email
  let saved = null
  try { saved = JSON.parse(localStorage.getItem(GC_DRAFT_KEY) || 'null') } catch (_) { saved = null }
  if (saved && saved.order_no) {
    try {
      const o = await req('GET', '/api/orders/' + encodeURIComponent(saved.order_no) + '?email=' + encodeURIComponent(saved.email || ''))
      if (o && o.status === 0) {
        if (saved.email) purchaser.value = saved.email
        result.value = { code: saved.code || '', order_no: saved.order_no, amount_cents: saved.amount_cents, status: 0 }
        paid.value = false
      } else {
        clearGcDraft()
      }
    } catch (e) {
      if (e && e.status === 404) clearGcDraft()
    }
  }
})

const purchaserBad = computed(() => !!purchaser.value && !EMAIL_RE.test(purchaser.value))
const recipientBad = computed(() => !!recipient.value && !EMAIL_RE.test(recipient.value))

async function buy() {
  if (busy.value) return
  if (!EMAIL_RE.test(purchaser.value.trim())) { ui.toast(t('Enter your email (we send the code there)', '请填写你的邮箱（礼品卡码将发送至此）'), 'error'); return }
  if (recipientBad.value) { ui.toast(t('Recipient email looks invalid', '收件人邮箱格式不正确'), 'error'); return }
  busy.value = true
  try {
    result.value = await req('POST', '/api/promo/giftcard/purchase', {
      amount_cents: amountC.value,
      purchaser_email: purchaser.value.trim(),
      recipient_email: recipient.value.trim() || null,
      message: msg.value.trim() || null,
    })
    paid.value = false
    saveGcDraft()
    ui.toast(t('Gift card created 🎁', '礼品卡已生成 🎁'), 'success')
  } catch (e) {
    const m = e && e.data && e.data.detail ? errMessage(e) : ''
    if (m === 'code collision') ui.toast(t('Please retry — code generation conflict', '生成冲突，请重试'), 'error')
    else if (e && e.status === 422) ui.toast(t('Please check the email format and retry', '请检查邮箱格式后重试'), 'error')
    else if (m) ui.toast(m, 'error')
    else if (e && e.status === 0) ui.toast(t('Network unreachable — check your connection', '网络连接失败，请检查网络'), 'error')
    else ui.toast(t('Purchase failed — please retry', '购买失败，请稍后再试'), 'error')
  } finally { busy.value = false }
}

/* 礼品卡订单为待支付订单：mock 通道直接演示支付；真实 provider 走 hosted redirect（支付成功后后端自动激活 status 0→1）；游客单带购买人 email 过归属校验 */
async function payAndActivate() {
  if (paying.value || !result.value) return
  paying.value = true
  const em = purchaser.value.trim()
  try {
    const intent = await req('POST', '/api/payments/create-intent', { order_no: result.value.order_no, email: em })
    if (intent && intent.redirect_url) {
      window.location.href = intent.redirect_url
      return
    }
    if (intentNoChannel(intent)) {
      ui.toast(i18n.t('pay.unsupported_channel'), 'error')
      return
    }
    try {
      await req('POST', '/api/payments/mock-pay', { order_no: result.value.order_no, email: em, succeed: true })
      paid.value = true
      clearGcDraft()
      ui.toast(t('Paid — gift card activated', '支付成功 · 礼品卡已激活'), 'success')
    } catch (e) {
      const m = (e.data && e.data.detail) || ''
      if (m === 'already_paid') { paid.value = true; clearGcDraft(); ui.toast(t('Already paid', '已支付'), 'success') }
      else ui.toast(m === 'use_webhook' ? t('Complete payment via the link emailed to you', '请通过邮件中的支付链接完成付款') : m || i18n.t('pay.failed'), 'error')
    }
  } catch (e) {
    ui.toast((e.data && e.data.detail) || i18n.t('pay.failed'), 'error')
  } finally { paying.value = false }
}

/* 余额查询：POST /api/promo/giftcard {code} → {balance_cents, status, expires_at}；404 invalid_card 等 */
const balCode = ref('')
const balBusy = ref(false)
const balResult = ref(null)
const balErr = ref('')
async function checkBalance() {
  const c = balCode.value.trim().toUpperCase()
  balErr.value = ''
  if (!c) { balErr.value = i18n.t('gc.check.enter'); return }
  balBusy.value = true
  balResult.value = null
  try {
    balResult.value = await req('POST', '/api/promo/giftcard', { code: c })
  } catch (e) {
    const m = e && e.data && e.data.detail
    balErr.value = m === 'invalid_card' ? i18n.t('gc.check.invalid') : i18n.t('gc.check.fail')
  } finally { balBusy.value = false }
}

async function copyCode() {
  if (!result.value) return
  try {
    await navigator.clipboard.writeText(result.value.code)
  } catch (_) {
    const ta = document.createElement('textarea')
    ta.value = result.value.code; document.body.appendChild(ta); ta.select()
    try { document.execCommand('copy') } catch (_) { /* older browsers */ }
    document.body.removeChild(ta)
  }
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

const mailto = computed(() => {
  if (!result.value) return '#'
  const subject = encodeURIComponent(`A GLOWMAG gift card for you 💅`)
  const body = encodeURIComponent(
    `Here's your GLOWMAG gift card!\n\nCode: ${result.value.code}\nAmount: ${money(result.value.amount_cents)}\n${msg.value.trim() ? '\n' + msg.value.trim() + '\n' : ''}Redeem at checkout — no expiry. Enjoy the glam! 💅`,
  )
  return `mailto:${encodeURIComponent(recipient.value.trim())}?subject=${subject}&body=${body}`
})
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:46px">💳</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">{{ t('Gift Cards', '礼品卡') }}</h1>
        <p style="color:var(--gray)">{{ t('The glam that always fits. Delivered instantly by email.', '最不会出错的礼物，即时发送到邮箱。') }}</p>
      </div>

      <!-- 购买结果卡 -->
      <div v-if="result" class="card" style="padding:26px;margin-bottom:22px;text-align:center">
        <div style="font-size:15px;font-weight:700;margin-bottom:14px">
          {{ paid || result.status === 1 ? '🎉 ' + t('Gift card activated!', '礼品卡已激活！') : '🎁 ' + t('Gift card created — pay to activate', '礼品卡已生成 · 支付后激活') }}
        </div>
        <div class="gc-code">{{ result.code }}</div>
        <div style="font-size:13.5px;color:var(--gray);margin:10px 0 4px">
          {{ t('Amount', '面额') }} <b style="color:var(--plum)">{{ money(result.amount_cents) }}</b> ·
          {{ t('Order', '订单') }} <b>{{ result.order_no }}</b>
        </div>
        <p style="font-size:12.5px;color:var(--gray);margin-bottom:16px">
          <template v-if="paid || result.status === 1">
            {{ t("We've emailed this code to", '礼品卡码已发送至') }} <b>{{ purchaser }}</b><template v-if="recipient.trim()"> → {{ recipient.trim() }}</template>.
          </template>
          <template v-else>
            {{ t('The code will be emailed to', '支付完成后，卡码将发送至') }} <b>{{ purchaser }}</b><template v-if="recipient.trim()"> → {{ recipient.trim() }}</template>
            {{ t('once payment is completed.', '（当前订单待支付）。') }}
          </template>
          {{ t('Use it at checkout (gift card field). No expiry.', '结算时在礼品卡栏输入即可，永久有效。') }}
        </p>
        <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
          <button v-if="!paid && result.status !== 1" class="btn btn-primary" :class="{ loading: paying }" :disabled="paying" @click="payAndActivate">
            {{ t(`Pay & activate · ${money(result.amount_cents)}`, `支付并激活 · ${money(result.amount_cents)}`) }}
          </button>
          <button class="btn btn-secondary" @click="copyCode">{{ copied ? '✓ ' + t('Copied', '已复制') : t('Copy code', '复制卡码') }}</button>
          <a v-if="recipient.trim()" :href="mailto" class="btn btn-secondary">✉️ {{ t('Send to friend', '发送给好友') }}</a>
          <button class="btn btn-ghost" @click="result = null; paid = false">{{ t('Buy another', '再买一张') }}</button>
        </div>
      </div>

      <div v-else class="grid-m-1" style="display:grid;grid-template-columns:1fr 1fr;gap:22px">
        <div class="card" style="padding:26px;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff">
          <div style="font-family:var(--font-title);font-size:24px">GLOW<span style="opacity:.75">MAG</span></div>
          <div style="font-size:38px;font-weight:800;margin:26px 0 6px">{{ money(amountC) }}</div>
          <div style="font-size:12.5px;opacity:.8">GIFT CARD · NO EXPIRY</div>
        </div>
        <div class="card" style="padding:22px">
          <div class="field"><label>{{ t('Amount', '面额') }}</label>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button v-for="a in AMOUNTS" :key="a" class="btn btn-sm" :class="amountC === a ? 'btn-primary' : 'btn-secondary'" @click="amountC = a">{{ money(a) }}</button>
            </div>
          </div>
          <div class="field" :class="{ error: purchaserBad }">
            <label>{{ t('Your email (purchaser)', '你的邮箱（购买人）') }} *</label>
            <input v-model="purchaser" class="input" :class="{ error: purchaserBad }" type="email" autocomplete="email" placeholder="you@example.com">
            <div class="field-msg">{{ t('Enter a valid email', '请输入有效邮箱') }}</div>
          </div>
          <div class="field" :class="{ error: recipientBad }">
            <label>{{ t('Recipient email (optional)', '收件人邮箱（选填）') }}</label>
            <input v-model="recipient" class="input" :class="{ error: recipientBad }" type="email" autocomplete="off" placeholder="friend@example.com">
            <div class="field-msg">{{ t('Enter a valid email', '请输入有效邮箱') }}</div>
          </div>
          <div class="field">
            <label>{{ t('Message', '留言') }} ({{ msg.length }}/255)</label>
            <textarea v-model="msg" class="input" rows="2" maxlength="255" :placeholder="t('Happy glam birthday! 💅', '生日快乐！💅')"></textarea>
          </div>
          <button class="btn btn-primary btn-block" :class="{ loading: busy }" :disabled="busy" @click="buy">
            {{ t(`Buy gift card · ${money(amountC)}`, `购买礼品卡 · ${money(amountC)}`) }}
          </button>
          <p style="font-size:11.5px;color:var(--gray);margin-top:10px;text-align:center">
            {{ t('Instant email delivery · no expiry · stackable with points', '即时发送 · 永久有效 · 可与积分同享') }}
          </p>
        </div>
      </div>

      <!-- 余额查询 -->
      <div class="card" style="padding:22px;margin-top:22px">
        <h2 style="font-family:var(--font-title);font-size:20px;margin-bottom:4px">🔍 {{ i18n.t('gc.check.t') }}</h2>
        <p style="font-size:13px;color:var(--gray);margin-bottom:14px">{{ i18n.t('gc.check.d') }}</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <input
            v-model="balCode" class="input" style="flex:1;min-width:200px;text-transform:uppercase"
            :placeholder="i18n.t('co.gcPh')" @keyup.enter="checkBalance"
          >
          <button class="btn btn-secondary" :class="{ loading: balBusy }" :disabled="balBusy" @click="checkBalance">
            {{ i18n.t('gc.check.btn') }}
          </button>
        </div>
        <p v-if="balErr" style="font-size:13px;color:var(--error);margin-top:10px">{{ balErr }}</p>
        <div v-if="balResult" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:14px;font-size:14px">
          <b>{{ balCode.trim().toUpperCase() }}</b>
          <span>· {{ i18n.t('gc.check.balance') }} <b style="color:var(--plum)">{{ money(balResult.balance_cents) }}</b></span>
          <span>· {{ i18n.t('gc.check.status') }} <span class="tag tag-paid">{{ i18n.t('gc.check.active') }}</span></span>
          <span>· {{ balResult.expires_at ? i18n.t('gc.check.expires', fmtDate(balResult.expires_at, '')) : i18n.t('gc.check.noExpiry') }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.gc-code { font-family: monospace; font-size: 22px; font-weight: 700; letter-spacing: 1.5px; background: var(--rose-pale); border: 1.5px dashed var(--plum); color: var(--plum); border-radius: 12px; padding: 14px 18px; display: inline-block; user-select: all; }
</style>
