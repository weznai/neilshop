<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../api/client'
import { fmtDate } from '../composables/datetime'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'
import { i18n, tt } from '../i18n'

const auth = useAuthStore()
const ui = useUiStore()

const isDev = !!import.meta.env.DEV
const me = ref(null)
const failed = ref(false)
const inviteEmail = ref('')
const inviteBusy = ref(false)
const copyOk = ref(false)

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
/* /api/referrals/me → {code, invited[], stats{invited,rewarded,points_earned}} */
const link = computed(() => {
  if (!me.value?.code) return ''
  return window.location.origin + '/register?ref=' + me.value.code
})

/* ReferralStatus 0-4 → [en, zh]（对齐 server service_referrals.py STATUS_TEXT；未知 status 回落后端 status_text） */
const REF_STATUS = {
  0: ['Clicked · sign-up pending', '点击注册'],
  1: ['Registered', '已注册'],
  2: ['First order pending', '首单待确认'],
  3: ['Rewarded', '已奖励'],
  4: ['Invalid', '无效'],
}
function refStatus(r) {
  const row = REF_STATUS[r.status]
  return row ? tt(row[0], row[1]) : (r.status_text || String(r.status))
}

/* 分享文案（原生 share / 渠道 chips 预设，均带推荐链接） */
const shareText = computed(() => tt(
  'Join me at GLOWMAG — sign up with my link and we both get $10 in points 💅',
  '来 GLOWMAG 和我一起变美——用我的链接注册，双方各得 $10 积分 💅',
))

async function load() {
  failed.value = false
  try { me.value = await req('GET', '/api/referrals/me') }
  catch (_) { failed.value = true }
}
onMounted(() => { if (auth.isLoggedIn) load() })

async function copyLink() {
  if (!link.value) return
  try {
    await navigator.clipboard.writeText(link.value)
    copyOk.value = true
    setTimeout(() => { copyOk.value = false }, 1500)
    ui.toast(tt('Referral link copied 💜', '推荐链接已复制 💜'), 'success')
  } catch (_) {
    ui.toast(tt('Copy failed — please copy manually: ', '复制失败，请手动复制：') + link.value, 'error')
  }
}

/* 原生分享（支持则唤起系统分享面板；取消/不支持回落复制链接） */
async function shareLink() {
  if (!link.value) return
  if (navigator.share) {
    try { await navigator.share({ title: 'GLOWMAG', text: shareText.value, url: link.value }); return } catch (_) { /* 取消/失败回落复制 */ }
  }
  copyLink()
}

/* 渠道 chips：预设文案 + 链接直接带入 */
function shareTo(ch) {
  if (!link.value) return
  const txt = encodeURIComponent(`${shareText.value} ${link.value}`)
  const u = ch === 'wa' ? 'https://wa.me/?text=' + txt
    : ch === 'x' ? 'https://twitter.com/intent/tweet?text=' + txt
    : 'mailto:?subject=' + encodeURIComponent('GLOWMAG') + '&body=' + txt
  window.open(u, '_blank', 'noopener')
}

/* 模拟邀请（演示端点，仅 DEV 可见）：登记受邀邮箱 → 状态「已注册」 */
async function sendInvite() {
  const v = inviteEmail.value.trim()
  if (!EMAIL_RE.test(v)) { ui.toast(tt('Enter a valid email address', '请输入有效的邮箱地址'), 'error'); return }
  inviteBusy.value = true
  try {
    await req('POST', '/api/referrals/simulate-invite', { email: v })
    ui.toast(tt('Invite registered — points for both sides arrive after their first paid order', '邀请已登记，好友注册并完成首单后双方到账'), 'success')
    inviteEmail.value = ''
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail
    ui.toast(d === 'already invited' ? tt('That email has already been invited', '该邮箱已被邀请过') : tt('Invite failed — please retry later', '邀请失败，请稍后再试'), 'error')
  } finally { inviteBusy.value = false }
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:680px;text-align:center">
      <div style="font-size:46px;margin-bottom:6px">🎁</div>
      <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">{{ tt('Referral Program', '推荐有礼') }}</h1>
      <p style="color:var(--gray);margin-bottom:22px">
        {{ tt('Share your exclusive link — when a friend signs up and completes their first order,', '分享你的专属链接 —— 好友注册并完成首单后，') }}
        <b>{{ tt('you both get 1000 points', '双方各得 1000 积分') }}</b>{{ tt(' (worth $10, 100 pts = $1).', '（价值 $10，100 分 = $1）。') }}
      </p>

      <template v-if="!auth.isLoggedIn">
        <p style="font-size:13.5px;color:var(--gray)">
          <router-link :to="{ path: '/login', query: { next: '/refer' } }" style="color:var(--plum);font-weight:600">{{ tt('Sign in', '登录') }}</router-link>
          {{ tt('to view your referral code and reward progress.', '后即可查看你的专属推荐码与奖励进度。') }}
        </p>
      </template>

      <template v-else>
        <div v-if="failed" class="card" style="padding:22px;color:var(--gray)">
          {{ tt('Load failed —', '加载失败，') }}<a href="javascript:void(0)" style="color:var(--plum)" @click="load">{{ tt('retry', '重试') }}</a>
        </div>
        <div v-else-if="!me" class="skeleton" style="height:120px;border-radius:14px" />
        <template v-else>
          <!-- 推荐码 + 链接 -->
          <div class="card" style="padding:20px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;max-width:500px;margin:0 auto 12px;text-align:left">
            <code style="flex:1;min-width:160px;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
              {{ link || 'glowmag.com/r/…' }}
            </code>
            <button class="btn btn-primary btn-sm" @click="copyLink">{{ copyOk ? tt('Copied ✓', '已复制 ✓') : tt('Copy link', '复制链接') }}</button>
            <button class="btn btn-secondary btn-sm" @click="shareLink">📤 {{ tt('Share', '分享') }}</button>
          </div>
          <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-bottom:18px">
            <button class="btn btn-secondary btn-sm" @click="shareTo('wa')">💬 WhatsApp</button>
            <button class="btn btn-secondary btn-sm" @click="shareTo('x')">𝕏 X</button>
            <button class="btn btn-secondary btn-sm" @click="shareTo('mail')">✉️ Email</button>
          </div>
          <div style="font-size:12px;color:var(--gray);margin-bottom:18px">
            {{ tt('Referral code', '推荐码') }} <b>{{ me.code }}</b>{{ tt(' (carried in the link, applied at friend signup)', '（链接自动携带，好友注册时生效）') }}
          </div>

          <!-- 统计 -->
          <div class="grid grid-3" style="max-width:520px;margin:0 auto 22px">
            <div class="card" style="padding:16px"><b style="font-size:24px">{{ me.stats?.invited || 0 }}</b><div style="font-size:12px;color:var(--gray)">{{ tt('Invited', '已邀请') }}</div></div>
            <div class="card" style="padding:16px"><b style="font-size:24px;color:var(--plum)">{{ me.stats?.rewarded || 0 }}</b><div style="font-size:12px;color:var(--gray)">{{ tt('Rewarded', '已奖励') }}</div></div>
            <div class="card" style="padding:16px"><b style="font-size:24px;color:var(--success)">{{ (me.stats?.points_earned || 0).toLocaleString() }}</b><div style="font-size:12px;color:var(--gray)">{{ tt('Points earned', '累计积分') }}</div></div>
          </div>

          <!-- 模拟邀请（仅 DEV 演示） -->
          <div v-if="isDev" class="card" style="padding:18px;max-width:500px;margin:0 auto 22px;text-align:left">
            <div style="font-size:13.5px;font-weight:700;margin-bottom:8px">📮 {{ tt('Register a friend’s email (Demo / simulate)', '登记好友邮箱（模拟 Demo）') }}</div>
            <div style="display:flex;gap:8px">
              <input v-model="inviteEmail" class="input" type="email" placeholder="friend@example.com" @keyup.enter="sendInvite">
              <button class="btn btn-secondary" :class="{ loading: inviteBusy }" :disabled="inviteBusy" @click="sendInvite">{{ tt('Invite (simulate)', '邀请（模拟）') }}</button>
            </div>
            <div style="font-size:12px;color:var(--gray);margin-top:6px">
              {{ tt('Demo only: the invite shows as “sign-up pending”; both rewards land after the friend signs up via your referral link and completes their first order.', '仅演示：登记后状态为「待注册」，好友经推荐链接注册并完成首单后双方奖励到账。') }}
            </div>
          </div>

          <!-- 邀请列表 -->
          <div v-if="(me.invited || []).length" class="card" style="padding:18px;max-width:500px;margin:0 auto;text-align:left">
            <div style="font-size:13.5px;font-weight:700;margin-bottom:6px">{{ tt('My invites', '我的邀请') }}</div>
            <div v-for="(r, i) in me.invited" :key="i" style="display:flex;justify-content:space-between;align-items:center;font-size:13px;padding:9px 0;border-bottom:1px dashed var(--gray-light)">
              <span>{{ r.email_masked }}<span style="color:var(--gray)"> · {{ fmtDate(r.created_at) }}</span></span>
              <span class="tag" :class="r.status === 3 ? 'tag-paid' : r.status === 4 ? 'tag-error' : 'tag-pending'">{{ refStatus(r) }}</span>
            </div>
          </div>
          <div v-else class="card" style="padding:22px;color:var(--gray);font-size:13.5px;max-width:500px;margin:0 auto">
            {{ tt('No invites yet — send your link to a bestie 💅', '还没有邀请记录 —— 把链接发给闺蜜吧 💅') }}
          </div>
        </template>
      </template>
    </div>
  </section>
</template>
