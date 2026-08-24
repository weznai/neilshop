<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { i18n, tt } from '../i18n'

const auth = useAuthStore()
const cart = useCartStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const name = ref('')
const email = ref('')
const password = ref('')
const password2 = ref('')
const showPw = ref(false)
const showPw2 = ref(false)
const busy = ref(false)
const err = ref('')
const agreed = ref(false)
/* 推荐落地：/register?ref=GLOW-XXXX（存表单，注册请求体带 ref_code 由后端绑定） */
const refCode = ref(String(route.query.ref || '').trim())
/* 「直接登录」透传 next 与 ref（好友邀请登录后仍可回来注册拿奖励） */
const loginLink = computed(() => {
  const q = {}
  if (route.query.next) q.next = String(route.query.next)
  if (refCode.value) q.ref = refCode.value
  return { path: '/login', query: Object.keys(q).length ? q : undefined }
})

/* 注册即自动登录（后端注册返回 token 并写会话 Cookie）；
   认证页互跳（login/register/reset-password）回落 /account，避免重定向循环 */
function nextRoute() {
  const n = route.query.next
  if (n === undefined || n === null) return '/account'
  if (typeof n !== 'string' || !/^\/(?!\/)/.test(n)) return '/'
  if (n === '/login' || n === '/register' || n.startsWith('/reset-password')) return '/account'
  return n
}
if (auth.isLoggedIn) router.replace(nextRoute())

const pwLen = computed(() => password.value.length)
const pwOk = computed(() => pwLen.value >= 8 && pwLen.value <= 128)
/* 弱密码提示：纯数字易被撞库 */
const pwWeak = computed(() => pwOk.value && /^\d+$/.test(password.value))

function fieldCheck() {
  if (!name.value.trim()) return tt('Enter your name', '请输入昵称')
  if (!EMAIL_RE.test(email.value.trim())) return tt('Enter a valid email address', '请输入有效的邮箱地址')
  if (!pwOk.value) return tt('Password must be 8-128 characters', '密码长度需为 8-128 位')
  if (password.value !== password2.value) return tt('Passwords do not match', '两次输入的密码不一致')
  if (!agreed.value) return tt('Please agree to the Terms of Service & Privacy Policy', '请先阅读并同意服务条款与隐私政策')
  return ''
}

async function submit() {
  err.value = fieldCheck()
  if (err.value) return
  busy.value = true
  try {
    await auth.register(email.value.trim(), password.value, name.value.trim(), refCode.value || undefined)
    await cart.mergeAfterLogin()
    ui.toast(tt('Welcome to GLOWMAG 💜', '欢迎加入 GLOWMAG 💜'), 'success')
    router.push(nextRoute())
  } catch (e) {
    const d = e && e.data && e.data.detail
    if (e && e.status === 409 && d === 'email already registered') err.value = tt('This email is already registered — sign in instead', '该邮箱已注册，请直接登录')
    else if (e && e.status === 422) err.value = tt('Please check: name 1-100 chars, valid email, password 8-128 chars', '请检查填写：昵称 1-100 字、有效邮箱、密码 8-128 位')
    else err.value = tt('Registration failed — please retry later', '注册失败，请稍后再试')
  } finally { busy.value = false }
}
</script>

<template>
  <section class="section">
    <div class="container auth-wrap">
      <!-- 品牌分栏：左 45% 渐变板（≤768px 折叠为顶部 140px 横条） -->
      <aside class="auth-brand">
        <div class="auth-logo">GLOW<span>MAG</span></div>
        <p class="auth-tag">{{ tt('Join the glam club — member-only drops & birthday gifts.', '加入 glam 俱乐部 —— 会员限定上新与生日礼。') }}</p>
        <ul class="auth-trust">
          <li>↩️ {{ tt('30-day free returns', '30 天免费退货') }}</li>
          <li>🚚 {{ tt('Free shipping over $35', '满 $35 免邮') }}</li>
          <li>⭐ {{ tt('Points on every order', '每单攒积分') }}</li>
        </ul>
      </aside>
      <div class="card auth-card">
        <div v-if="refCode" style="margin:-6px -6px 14px;padding:8px 12px;background:var(--rose-pale);border-radius:10px;font-size:12.5px;color:var(--plum);font-weight:600">
          🎁 {{ tt(`Invited by a friend (${refCode}) — you both get 1000 points after their first order`, `受好友邀请（${refCode}）——注册下单后双方各得 1000 积分`) }}
        </div>
        <h1 style="font-family:var(--font-title);font-size:26px;margin-bottom:4px">{{ tt('Join GLOWMAG ✨', '加入 GLOWMAG ✨') }}</h1>
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:20px">{{ tt('Member-only drops · birthday gift · points on every order.', '会员限定上新 · 生日礼 · 每单攒积分。') }}</p>
        <form @submit.prevent="submit">
          <div class="field">
            <label>{{ tt('Name', '昵称') }}</label>
            <input v-model="name" class="input" autocomplete="name" maxlength="100" placeholder="Glam Queen">
          </div>
          <div class="field">
            <label>{{ tt('Email', '邮箱') }}</label>
            <input v-model="email" class="input" type="email" autocomplete="email" placeholder="you@example.com">
          </div>
          <div class="field">
            <label>{{ tt('Password (8-128 chars)', '密码（8-128 位）') }}</label>
            <div class="pw-wrap">
              <input v-model="password" class="input" :type="showPw ? 'text' : 'password'" autocomplete="new-password" :placeholder="tt('At least 8 characters', '至少 8 位')">
              <button type="button" class="pw-eye" :aria-label="tt('Toggle password visibility', '切换密码可见')" @click="showPw = !showPw">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
              </button>
            </div>
            <div v-if="password" class="field-msg" :style="{ display: 'block', color: pwOk ? 'var(--success)' : 'var(--error)' }">
              {{ pwOk ? '✓ ' + tt('Length OK', '长度符合要求') : tt(`${8 - pwLen} more to go`, `还需 ${8 - pwLen} 位`) }}
            </div>
            <div v-if="pwWeak" class="field-msg" style="display:block;color:var(--warn)">
              ⚠️ {{ tt('All-digit passwords are easy to crack — mix in letters or symbols', '纯数字密码容易被破解，建议加入字母/符号') }}
            </div>
          </div>
          <div class="field">
            <label>{{ tt('Confirm password', '确认密码') }}</label>
            <div class="pw-wrap">
              <input v-model="password2" class="input" :type="showPw2 ? 'text' : 'password'" autocomplete="new-password" placeholder="••••••••">
              <button type="button" class="pw-eye" :aria-label="tt('Toggle password visibility', '切换密码可见')" @click="showPw2 = !showPw2">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
              </button>
            </div>
            <div v-if="password && password2 && password !== password2" class="field-msg" style="display:block;color:var(--error)">
              {{ tt('Passwords do not match', '两次输入的密码不一致') }}
            </div>
          </div>
            <div v-if="err" class="field-msg" style="display:block;margin-bottom:10px" role="alert">{{ err }}</div>
            <label style="display:flex;gap:8px;align-items:flex-start;margin:0 0 14px;font-size:13px;color:var(--gray)">
              <input v-model="agreed" type="checkbox" style="width:16px;height:16px;margin-top:1px;accent-color:var(--plum)">
              <span>{{ tt('I have read and agree to the', '我已阅读并同意') }}
                <router-link to="/terms" style="color:var(--plum);text-decoration:underline">{{ tt('Terms of Service', '服务条款') }}</router-link>
                {{ tt('and', '与') }}
                <router-link to="/privacy" style="color:var(--plum);text-decoration:underline">{{ tt('Privacy Policy', '隐私政策') }}</router-link>
              </span>
            </label>
            <button class="btn btn-primary btn-block btn-lg" :class="{ loading: busy }" :disabled="busy">{{ tt('Create Account', '注册') }}</button>
        </form>
        <div style="text-align:center;margin-top:14px;font-size:13px;color:var(--gray)">
          {{ tt('Already a member?', '已是会员？') }}
          <router-link :to="loginLink" style="color:var(--plum);font-weight:600">{{ tt('Sign in', '直接登录') }}</router-link>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 品牌分栏注册页：左 45% 渐变品牌板 + 右表单卡（≤768px 折叠为顶部 140px 横条） */
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
