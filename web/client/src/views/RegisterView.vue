<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const name = ref('')
const email = ref('')
const password = ref('')
const busy = ref(false)
const err = ref('')
/* 推荐落地：/register?ref=GLOW-XXXX（存表单，注册请求体带 ref_code 由后端绑定） */
const refCode = ref(String(route.query.ref || '').trim())

/* 注册即自动登录（后端注册返回 token 并写会话 Cookie） */
function nextRoute() {
  const n = route.query.next
  if (n === undefined || n === null) return '/account'
  return typeof n === 'string' && /^\/(?!\/)/.test(n) ? n : '/'
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
    <div class="container" style="max-width:440px">
      <div class="card" style="padding:30px">
        <div v-if="refCode" style="margin:-6px -6px 14px;padding:8px 12px;background:var(--rose-pale);border-radius:10px;font-size:12.5px;color:var(--plum);font-weight:600">
          🎁 {{ tt(`Invited by a friend (${refCode}) — you both get 1000 points after their first order`, `受好友邀请（${refCode}）——注册下单后双方各得 1000 积分`) }}
        </div>
        <h1 style="font-family:var(--font-title);font-size:26px;margin-bottom:4px">{{ tt('Join GLOWMAG ✨', '加入 GLOWMAG ✨') }}</h1>
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:20px">{{ tt('Member-only drops · birthday gift · points on every order.', '会员限定上新 · 生日礼 · 每单攒积分。') }}</p>
        <form @submit.prevent="submit">
          <div class="field">
            <label>{{ tt('Name 昵称', '昵称 Name') }}</label>
            <input v-model="name" class="input" autocomplete="name" maxlength="100" placeholder="Glam Queen">
          </div>
          <div class="field">
            <label>{{ tt('Email', '邮箱') }}</label>
            <input v-model="email" class="input" type="email" autocomplete="email" placeholder="you@example.com">
          </div>
          <div class="field">
            <label>{{ tt('Password (8-128 chars)', '密码（8-128 位）') }}</label>
            <input v-model="password" class="input" type="password" autocomplete="new-password" :placeholder="tt('At least 8 characters', '至少 8 位')">
            <div v-if="password" class="field-msg" :style="{ display: 'block', color: pwOk ? 'var(--success)' : 'var(--error)' }">
              {{ pwOk ? '✓ ' + tt('Length OK', '长度符合要求') : tt(`还需 ${8 - pwLen} 位`, `还需 ${8 - pwLen} 位`) }}
            </div>
            <div v-if="pwWeak" class="field-msg" style="display:block;color:var(--warn)">
              ⚠️ {{ tt('All-digit passwords are easy to crack — mix in letters or symbols', '纯数字密码容易被破解，建议加入字母/符号') }}
            </div>
          </div>
          <div v-if="err" class="field-msg" style="display:block;margin-bottom:10px">{{ err }}</div>
          <button class="btn btn-primary btn-block btn-lg" :class="{ loading: busy }" :disabled="busy">{{ tt('Create Account 注册', '注册 Create Account') }}</button>
        </form>
        <div style="text-align:center;margin-top:14px;font-size:13px;color:var(--gray)">
          {{ tt('Already a member?', '已是会员？') }}
          <router-link :to="{ path: '/login', query: route.query.next ? { next: String(route.query.next) } : undefined }" style="color:var(--plum);font-weight:600">{{ tt('Sign in', '直接登录') }}</router-link>
        </div>
      </div>
    </div>
  </section>
</template>
