<script setup>
/* 密码重置落地页：邮件链接 /reset-password?token=…（确认端点需 email + token + new_password） */
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { useUiStore } from '../stores/ui'
import { i18n } from '../i18n'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const token = ref(String(route.query.token || ''))
const email = ref(String(route.query.email || ''))
const password = ref('')
const password2 = ref('')
const showPw = ref(false)
const showPw2 = ref(false)
const busy = ref(false)
const err = ref('')
const done = ref(false)

function fieldCheck() {
  if (!EMAIL_RE.test(email.value.trim())) return tt('Enter a valid email', '请输入有效邮箱')
  if (password.value.length < 8) return tt('Password must be at least 8 characters', '密码至少 8 位')
  if (password.value !== password2.value) return tt('Passwords do not match', '两次输入的密码不一致')
  return ''
}

async function submit() {
  err.value = fieldCheck()
  if (err.value) return
  busy.value = true
  try {
    await req('POST', '/api/account/password-reset/confirm', {
      email: email.value.trim(),
      token: token.value,
      new_password: password.value,
    })
    done.value = true
    ui.toast(tt('Password reset — please sign in with your new password', '密码已重置，请使用新密码登录'), 'success')
    setTimeout(() => router.push('/login'), 1200)
  } catch (e) {
    const d = e && e.data && e.data.detail
    if (e && e.status === 400 && d === 'invalid_token') {
      err.value = tt('This reset link is invalid or expired — please request a new one.', '重置链接无效或已过期，请重新申请。')
      token.value = ''
    } else if (e && e.status === 422) {
      err.value = tt('Please check: valid email + password of 8-128 characters', '请检查：有效邮箱 + 8-128 位密码')
    } else {
      err.value = tt('Reset failed — please retry', '重置失败，请稍后再试')
    }
  } finally { busy.value = false }
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:420px">
      <div class="card" style="padding:30px">
        <!-- 无 token / token 失效：链接无效引导 -->
        <template v-if="!token">
          <div style="font-size:40px;text-align:center;margin-bottom:10px">🔗</div>
          <h1 style="font-family:var(--font-title);font-size:22px;margin-bottom:8px;text-align:center">
            {{ tt('Invalid reset link', '链接无效') }}
          </h1>
          <p style="font-size:13.5px;color:var(--gray);text-align:center;margin-bottom:18px">
            {{ tt('This password reset link is invalid or has expired (links are valid for 15 minutes). Please request a new one on the sign-in page.', '该密码重置链接无效或已过期（链接 15 分钟内有效），请在登录页重新申请。') }}
          </p>
          <router-link class="btn btn-primary btn-block" to="/login">{{ tt('← Back to sign in', '← 返回登录') }}</router-link>
        </template>

        <!-- 重置成功：提示并跳登录 -->
        <template v-else-if="done">
          <div style="font-size:40px;text-align:center;margin-bottom:10px">✅</div>
          <h1 style="font-family:var(--font-title);font-size:22px;margin-bottom:8px;text-align:center">
            {{ tt('Password updated', '密码已更新') }}
          </h1>
          <p style="font-size:13.5px;color:var(--gray);text-align:center;margin-bottom:18px">
            {{ tt('Redirecting you to sign in…', '正在跳转到登录页…') }}
          </p>
          <router-link class="btn btn-primary btn-block" to="/login">{{ tt('Go to sign in', '去登录') }}</router-link>
        </template>

        <!-- 有效 token：新密码表单 -->
        <template v-else>
          <h1 style="font-family:var(--font-title);font-size:24px;margin-bottom:4px">{{ tt('Set a new password', '设置新密码') }}</h1>
          <p style="font-size:13.5px;color:var(--gray);margin-bottom:20px">
            {{ tt('Enter the account email and a new password (at least 8 characters).', '请输入账户邮箱与新密码（至少 8 位）。') }}
          </p>
          <form @submit.prevent="submit">
            <div class="field">
              <label>{{ tt('Email', '邮箱') }}</label>
              <input v-model="email" class="input" type="email" autocomplete="email" placeholder="you@example.com">
            </div>
            <div class="field">
              <label>{{ tt('New password', '新密码') }}（≥8）</label>
              <div class="pw-wrap">
                <input v-model="password" class="input" :type="showPw ? 'text' : 'password'" autocomplete="new-password" placeholder="••••••••">
                <button type="button" class="pw-eye" :aria-label="tt('Toggle password visibility', '切换密码可见')" @click="showPw = !showPw">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
                </button>
              </div>
              <div v-if="password && password.length < 8" class="field-msg" style="display:block">
                {{ tt('At least 8 characters', '至少 8 位') }}
              </div>
            </div>
            <div class="field">
              <label>{{ tt('Confirm password', '确认新密码') }}</label>
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
            <div v-if="err" class="field-msg" style="display:block;margin-bottom:10px">{{ err }}</div>
            <button class="btn btn-primary btn-block btn-lg" :class="{ loading: busy }" :disabled="busy">
              {{ tt('Reset password', '重置密码') }}
            </button>
          </form>
          <div style="text-align:center;margin-top:14px;font-size:13px">
            <router-link to="/login" style="color:var(--plum);font-weight:600">{{ tt('← Back to sign in', '← 返回登录') }}</router-link>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>
