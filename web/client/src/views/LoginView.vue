<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { i18n } from '../i18n'

const auth = useAuthStore()
const cart = useCartStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)

const isDev = !!import.meta.env.DEV
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const mode = ref('login') /* login | forgot | sent */
const email = ref('')
const password = ref('')
const busy = ref(false)
const err = ref('')

/* 站内跳转白名单：仅接受以单个 / 开头且不以 // 开头的路径，非法回落 '/'；缺省回落 /account */
function nextRoute() {
  const n = route.query.next
  if (n === undefined || n === null) return '/account'
  return typeof n === 'string' && /^\/(?!\/)/.test(n) ? n : '/'
}

/* 已登录直接进账户 */
if (auth.isLoggedIn) router.replace(nextRoute())

function fieldCheck() {
  if (!EMAIL_RE.test(email.value.trim())) return tt('Enter a valid email address', '请输入有效的邮箱地址')
  if (mode.value === 'login' && !password.value) return tt('Enter your password', '请输入密码')
  return ''
}

async function submit() {
  err.value = fieldCheck()
  if (err.value) return
  busy.value = true
  try {
    await auth.login(email.value.trim(), password.value)
    await cart.mergeAfterLogin()
    ui.toast(tt('Welcome back 💜', '欢迎回来 💜'), 'success')
    router.push(nextRoute())
  } catch (e) {
    const d = e && e.data && e.data.detail
    if (e && e.status === 401 && d === 'invalid credentials') err.value = tt('Incorrect email or password', '邮箱或密码不正确')
    else if (e && e.status === 422) err.value = tt('Enter a valid email address', '请输入有效的邮箱地址')
    else err.value = tt('Sign-in failed — please retry later', '登录失败，请稍后再试')
  } finally { busy.value = false }
}

/* 忘记密码：POST /api/account/password-reset/request {email} → 恒 {ok:true}（防枚举）
 * 邮件携带 token 链接 → /reset-password?token=… 完成重置 */
async function sendReset() {
  err.value = fieldCheck()
  if (err.value) return
  busy.value = true
  try {
    await req('POST', '/api/account/password-reset/request', { email: email.value.trim() })
    mode.value = 'sent'
  } catch (e) {
    err.value = e && e.status === 422 ? tt('Enter a valid email address', '请输入有效的邮箱地址') : tt('Could not send — please retry later', '发送失败，请稍后再试')
  } finally { busy.value = false }
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:420px">
      <div class="card" style="padding:30px">
        <template v-if="mode === 'login'">
          <h1 style="font-family:var(--font-title);font-size:26px;margin-bottom:4px">{{ tt('Welcome back 💅', '欢迎回来 💅') }}</h1>
          <p style="font-size:13.5px;color:var(--gray);margin-bottom:20px">{{ tt('Sign in for orders, points & faster checkout.', '登录后管理订单、积分，结算更快捷。') }}</p>
          <form @submit.prevent="submit">
            <div class="field">
              <label>{{ tt('Email', '邮箱') }}</label>
              <input v-model="email" class="input" type="email" autocomplete="email" placeholder="you@example.com">
            </div>
            <div class="field">
              <div style="display:flex;justify-content:space-between;align-items:baseline">
                <label>{{ tt('Password', '密码') }}</label>
                <button type="button" style="font-size:12px;color:var(--plum);font-weight:600;background:none;border:none;cursor:pointer;padding:0" @click="mode = 'forgot'; err = ''">{{ tt('Forgot password?', '忘记密码？') }}</button>
              </div>
              <input v-model="password" class="input" type="password" autocomplete="current-password" placeholder="••••••••">
            </div>
            <div v-if="err" class="field-msg" style="display:block;margin-bottom:10px">{{ err }}</div>
            <button class="btn btn-primary btn-block btn-lg" :class="{ loading: busy }" :disabled="busy">{{ tt('Sign In 登录', '登录 Sign In') }}</button>
          </form>
          <div style="text-align:center;margin-top:14px;font-size:13px;color:var(--gray)">
            {{ tt('New here?', '还不是会员？') }}
            <router-link :to="{ path: '/register', query: route.query.next ? { next: String(route.query.next) } : undefined }" style="color:var(--plum);font-weight:600">{{ tt('Create account', '注册账号') }}</router-link>
            · <router-link to="/track" style="text-decoration:underline">{{ tt('Track order (no login)', '订单查询（免登录）') }}</router-link>
          </div>
          <div v-if="isDev" style="margin-top:16px;padding:10px 12px;background:var(--rose-pale);border-radius:10px;font-size:12px;color:var(--gray)">
            🧪 {{ tt('Demo account:', '演示账号：') }} <b>emma@glowmag.com</b> / <b>glowmag123</b>
          </div>
        </template>

        <template v-else-if="mode === 'forgot'">
          <h1 style="font-family:var(--font-title);font-size:24px;margin-bottom:4px">{{ tt('Reset password', '重置密码') }}</h1>
          <p style="font-size:13.5px;color:var(--gray);margin-bottom:20px">{{ tt('Enter your registered email — we’ll send a reset link (valid for 15 minutes).', '输入注册邮箱，我们将发送重置链接（15 分钟内有效）。') }}</p>
          <form @submit.prevent="sendReset">
            <div class="field">
              <label>{{ tt('Email', '邮箱') }}</label>
              <input v-model="email" class="input" type="email" autocomplete="email" placeholder="you@example.com">
            </div>
            <div v-if="err" class="field-msg" style="display:block;margin-bottom:10px">{{ err }}</div>
            <button class="btn btn-primary btn-block btn-lg" :class="{ loading: busy }" :disabled="busy">{{ tt('Send reset email', '发送重置邮件') }}</button>
          </form>
          <div style="text-align:center;margin-top:14px;font-size:13px">
            <button type="button" style="color:var(--plum);font-weight:600;background:none;border:none;cursor:pointer;padding:0" @click="mode = 'login'; err = ''">{{ tt('← Back to sign in', '← 返回登录') }}</button>
          </div>
        </template>

        <template v-else>
          <div style="font-size:40px;text-align:center;margin-bottom:10px">📧</div>
          <h1 style="font-family:var(--font-title);font-size:22px;margin-bottom:8px;text-align:center">{{ tt('Reset email sent', '重置邮件已发送') }}</h1>
          <p style="font-size:13.5px;color:var(--gray);text-align:center;margin-bottom:18px">
            {{ tt('If that email is registered, a reset link will arrive at', '如果该邮箱已注册，重置邮件将发送至') }} <b>{{ email }}</b>，
            {{ tt('please follow the link to finish resetting. (Demo environment: the link is printed in the backend logs / demo notes.)', '请按邮件内链接完成重置。（演示环境：链接见后端日志/演示说明。）') }}
          </p>
          <button class="btn btn-secondary btn-block" @click="mode = 'login'; err = ''">{{ tt('← Back to sign in', '← 返回登录') }}</button>
        </template>
      </div>
    </div>
  </section>
</template>
