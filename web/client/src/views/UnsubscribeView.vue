<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { i18n, tt } from '../i18n'
import { useAuthStore } from '../stores/auth'
import { req } from '../api/client'
import { useUiStore } from '../stores/ui'
import { useArmConfirm } from '../composables/useArmConfirm'

/* 退订链接：/unsubscribe?email=xx&token=us_HMAC（token 为 us_ 前缀 HMAC）
 * 无参数时回退登录会话（Cookie）读取自身偏好 */
const route = useRoute()
const auth = useAuthStore()
const ui = useUiStore()
const email = ref(String(route.query.email || ''))
const token = ref(String(route.query.token || ''))
const prefs = ref(null)
const err = ref('')
const loading = ref(true)
const saving = ref(false)
const saved = ref(false)

const hasToken = computed(() => !!email.value && !!token.value)
const prefLabels = computed(() => [
  ['sub_promo', tt('🎁 Promos & offers', '🎁 促销与优惠活动')],
  ['sub_new_arrival', tt('✨ New-arrival alerts', '✨ 新品上架通知')],
  ['sub_cart_abandon', tt('🛒 Cart reminders', '🛒 购物车提醒')],
])

async function load() {
  err.value = ''
  loading.value = true
  const qs = hasToken.value
    ? '?email=' + encodeURIComponent(email.value) + '&token=' + encodeURIComponent(token.value)
    : ''
  try {
    prefs.value = await req('GET', '/api/account/email-preferences' + qs)
  } catch (e) {
    /* 带 token 请求 400（token 失效）且已登录：清参数回退会话读取自身偏好 */
    if (e && e.status === 400 && qs && auth.isLoggedIn) {
      token.value = ''
      email.value = ''
      try { prefs.value = await req('GET', '/api/account/email-preferences') } catch (_) { /* 回退也失败则走下方错误态 */ }
    }
    if (!prefs.value) {
      err.value = e && (e.status === 400 || e.status === 401)
        ? '' : tt('Failed to load, please try again', '加载失败，请稍后再试')
    }
  } finally { loading.value = false }
  if (prefs.value && prefs.value.email) email.value = prefs.value.email
}
onMounted(load)

async function save() {
  if (!prefs.value) return
  saving.value = true
  saved.value = false
  const qs = hasToken.value
    ? '?email=' + encodeURIComponent(email.value) + '&token=' + encodeURIComponent(token.value)
    : ''
  /* 部分更新：仅传三个开关（后端：任一开 → 复订；全关 → 等价全退） */
  const body = {
    sub_promo: !!prefs.value.sub_promo,
    sub_new_arrival: !!prefs.value.sub_new_arrival,
    sub_cart_abandon: !!prefs.value.sub_cart_abandon,
  }
  try {
    prefs.value = await req('PUT', '/api/account/email-preferences' + qs, body)
    saved.value = true
    ui.toast(tt('Preferences saved', '偏好已保存'), 'success')
  } catch (e) {
    const d = e && e.data && e.data.detail
    ui.toast(
      d === 'token_required'
        ? tt('This page requires a valid unsubscribe link — please log in to manage your preferences', '该操作需要有效的退订链接，请登录后再管理邮件偏好')
        : e && (e.status === 400 || e.status === 401)
          ? tt('This link is invalid or expired', '链接无效或已过期')
          : tt('Save failed, please try again', '保存失败，请稍后再试'),
      'error',
    )
    /* 保存失败：重新拉取回滚开关显示（避免 UI 与服务端状态不一致） */
    await load()
  } finally { saving.value = false }
}

/* 一键全部退订：站内二次点击确认（useArmConfirm，5 秒未确认自动复位） */
const { is, hit } = useArmConfirm()
async function unsubAll() {
  saving.value = true
  try {
    await req('POST', '/api/account/unsubscribe', {
      email: email.value,
      token: hasToken.value ? token.value : null,
    })
    ui.toast(tt('Unsubscribed from all emails', '已退订全部邮件'), 'success')
    await load()
  } catch (e) {
    const d = e && e.data && e.data.detail
    ui.toast(
      d === 'invalid_token' || d === 'token_required'
        ? tt('Invalid link — please use the unsubscribe link in your email', '链接无效，请使用邮件中的退订链接')
        : tt('Unsubscribe failed, please try again', '退订失败，请稍后再试'),
      'error',
    )
  } finally { saving.value = false }
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:560px">
      <div class="section-head"><h1 class="section-title">{{ tt('Email Preferences ✉️', '邮件偏好设置 ✉️') }}</h1></div>

      <div v-if="loading" class="skeleton" style="min-height:220px;border-radius:14px" />

      <div v-else-if="prefs" class="card" style="padding:22px">
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:16px">
          {{ tt('Managing email preferences for', '正在管理') }} <b>{{ prefs.email }}</b>{{ tt('. Turn everything off to unsubscribe — you can re-enable here anytime.', ' 的邮件偏好。关闭全部即退出订阅；之后随时可在此重新开启。') }}
        </p>
        <label v-for="[k, label] in prefLabels" :key="k" style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--gray-light);font-size:14px;position:relative">
          <span>{{ label }}</span>
          <input v-model="prefs[k]" type="checkbox" class="unsub-chk" :disabled="saving">
          <span class="unsub-sw" aria-hidden="true"></span>
        </label>
        <div v-if="prefs.unsubscribed_at" style="font-size:12.5px;color:var(--warn);margin-top:10px">
          ⚠️ {{ tt('You are unsubscribed from all emails — turn any option on to re-subscribe.', '你已退订全部邮件 —— 开启任一项即可恢复订阅。') }}
        </div>
        <button class="btn btn-primary btn-block" style="margin-top:16px" :class="{ loading: saving }" :disabled="saving" @click="save">{{ tt('Save preferences', '保存偏好') }}</button>
        <button
          class="btn btn-ghost btn-block btn-sm" style="margin-top:8px"
          :style="is('unsub') ? 'color:#fff;background:var(--error)' : 'color:var(--error)'"
          :disabled="saving"
          @click="hit('unsub', unsubAll)"
        >{{ is('unsub') ? tt('Tap again to confirm unsubscribe', '再点一次确认退订全部') : tt('Unsubscribe from all emails', '一键退订全部邮件') }}</button>
        <p v-if="saved" style="font-size:12.5px;color:var(--success);text-align:center;margin-top:10px">{{ tt('Saved — takes effect on the next send.', '已保存 —— 后续发送立即生效。') }}</p>
      </div>

      <div v-else class="card" style="padding:22px;text-align:center;color:var(--gray)">
        <template v-if="auth.isLoggedIn">
          {{ tt('Could not load your email preferences.', '未能加载邮件偏好，请稍后再试。') }}
          <div v-if="err" style="margin-top:12px">
            <button class="btn btn-secondary btn-sm" :class="{ loading }" :disabled="loading" @click="load">{{ tt('Retry', '重试') }}</button>
          </div>
        </template>
        <template v-else>
          {{ tt('This unsubscribe link is invalid or expired (it needs ?email= and ?token= parameters).', '该退订链接无效或已过期（需要 ?email= 与 ?token= 参数）。') }}
          <div style="margin-top:12px">
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/login', query: { next: '/unsubscribe' } }">{{ tt('Log in to manage', '登录后管理') }}</router-link>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 自绘 checkbox 开关（隐藏原生输入，checked 态经相邻选择器驱动滑轨/滑钮） */
.unsub-chk { position: absolute; opacity: 0; pointer-events: none; }
.unsub-sw { position: relative; flex: none; width: 44px; height: 26px; border-radius: 999px; background: var(--gray-light); transition: background .2s; }
.unsub-sw::after {
  content: ""; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.25); transition: left .2s;
}
.unsub-chk:checked + .unsub-sw { background: var(--success); }
.unsub-chk:checked + .unsub-sw::after { left: 21px; }
.unsub-chk:disabled + .unsub-sw { opacity: .55; }
.unsub-chk:focus-visible + .unsub-sw { outline: 2px solid rgba(138,74,99,.6); outline-offset: 2px; }
</style>
