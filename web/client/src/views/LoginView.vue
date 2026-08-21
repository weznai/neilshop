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
const showPw = ref(false)
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
    <div class="container auth-wrap">
      <!-- 品牌分栏：左 45% 渐变板（≤768px 折叠为顶部 140px 横条） -->
      <aside class="auth-brand">
        <div class="auth-logo">GLOW<span>MAG</span></div>
        <p class="auth-tag">{{ tt('Press-on nails & magnetic lashes, delivered glam.', '穿戴甲与磁吸假睫毛，美貌直达。') }}</p>
        <ul class="auth-trust">
          <li>↩️ {{ tt('30-day free returns', '30 天免费退货') }}</li>
          <li>🚚 {{ tt('Free shipping over $35', '满 $35 免邮') }}</li>
          <li>⭐ {{ tt('Points on every order', '每单攒积分') }}</li>
        </ul>
      </aside>
      <div class="card auth-card">
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
              <div class="pw-wrap">
                <input v-model="password" class="input" :type="showPw ? 'text' : 'password'" autocomplete="current-password" placeholder="••••••••">
                <button type="button" class="pw-eye" :aria-label="tt('Toggle password visibility', '切换密码可见')" @click="showPw = !showPw">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
                </button>
              </div>
            </div>
            <div v-if="err" class="field-msg" style="display:block;margin-bottom:10px">{{ err }}</div>
            <button class="btn btn-primary btn-block btn-lg" :class="{ loading: busy }" :disabled="busy">{{ tt('Sign In', '登录') }}</button>
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

<style scoped>
/* 品牌分栏登录页：左 45% 渐变品牌板 + 右表单卡（≤768px 折叠为顶部 140px 横条） */
.auth-wrap { max-width: 860px; display: grid; grid-template-columns: 45% 1fr; align-items: stretch; border-radius: var(--radius-card); overflow: hidden; box-shadow: var(--shadow-card); background: #fff; }
.auth-brand { background: linear-gradient(160deg, var(--rose), var(--plum)); color: #fff; padding: 48px 36px; display: flex; flex-direction: column; justify-content: center; gap: 14px; }
.auth-logo { font-family: var(--font-title); font-size: 42px; font-weight: 700; letter-spacing: 1px; }
.auth-logo span { opacity: .7; }
.auth-tag { font-size: 13.5px; opacity: .88; line-height: 1.7; margin: 0; }
.auth-trust { list-style: none; display: grid; gap: 10px; margin: 10px 0 0; padding: 0; }
.auth-trust li { display: flex; gap: 10px; align-items: center; font-size: 13px; font-weight: 600; background: rgba(255,255,255,.14); border-radius: 10px; padding: 10px 14px; }
.auth-card { border: none; box-shadow: none; padding: 34px 30px; }
@media (max-width: 768px) {
  .auth-wrap { grid-template-columns: 1fr; }
  .auth-brand { min-height: 140px; padding: 24px 22px; }
  .auth-logo { font-size: 28px; }
  .auth-trust { display: none; }
}
</style>
