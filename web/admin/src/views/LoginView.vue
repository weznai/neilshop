<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { toast } from '../composables/toast'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const email = ref('')
const emailEl = ref(null)
const password = ref('')
const showPass = ref(false)
const busy = ref(false)
/* 演示账号/密码提示仅 DEV 出现，生产构建不泄露种子账号 */
const DEV = import.meta.env.DEV

onMounted(() => nextTick(() => emailEl.value?.focus()))

function normEmail() {
  let v = (email.value || '').trim().replace(/\s+/g, '')
  v = v.replace(/[\uFF01-\uFF5E]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xFEE0))
  if (/^(admin|ops|cs|emma)$/i.test(v)) v += '@glowmag.com'
  email.value = v.toLowerCase()
}

async function submit() {
  normEmail()
  if (!email.value.includes('@')) { toast(DEV ? '邮箱无法识别——直接填 ops 或 admin 即可' : '邮箱格式无效，请输入完整邮箱', 'error'); return }
  if (!password.value) { toast(DEV ? '请输入密码（演示密码统一 glowmag123）' : '请输入密码', 'error'); return }
  busy.value = true
  try {
    /* 登录响应已含 user（role/id/email），无需再 verify() 探测 */
    const u = await session.login(email.value, password.value)
    if ((u.role | 0) < 2) {
      toast('该账号无后台权限（需管理员账号）', 'error')
      await session.logout()
      return
    }
    toast('登录成功，进入管理控制台…', 'success')
    /* next 白名单校验：仅接受站内单斜杠路径，拒绝 //evil.com 类协议相对跳转 */
    const n = String(route.query.next || '/')
    router.push(/^\/[^/]/.test(n) ? n : '/')
  } catch (e) {
    console.error('[admin] 登录失败：', e)
    toast(
      e.status === 422 ? '邮箱格式无效——请用半角 @' + (DEV ? '（或直接填 ops / admin 快捷名）' : '')
        : e.status === 401 ? '邮箱或密码错误' + (DEV ? '（密码统一 glowmag123）' : '')
          : e.status === 403 ? '该账号无后台权限（需管理员账号）'
            : e.status === 429 ? '尝试过于频繁，请稍后再试'
              : '登录失败：' + (e.message || '请稍后重试'),
      'error',
    )
  } finally { busy.value = false }
}
</script>

<template>
  <div class="alogin-page">
    <div class="card" style="max-width:400px;width:100%;padding:34px 32px">
      <div style="text-align:center;margin-bottom:22px">
        <div class="logo" style="font-size:26px;color:var(--ink)">GLOW<span style="color:var(--rose)">MAG</span></div>
        <div style="font-size:11px;letter-spacing:3px;color:var(--gray);margin-top:6px">管理控制台 · ADMIN</div>
      </div>
      <form @submit.prevent="submit">
        <div class="field">
          <label>邮箱</label>
          <input ref="emailEl" v-model="email" class="input" autofocus autocomplete="username" :placeholder="DEV ? 'ops / admin / 完整邮箱' : '管理员邮箱'">
        </div>
        <div class="field">
          <label>密码</label>
          <div class="pw-wrap">
            <input v-model="password" class="input" :type="showPass ? 'text' : 'password'" autocomplete="current-password" :placeholder="DEV ? 'glowmag123' : '密码'">
            <button type="button" class="pw-eye" :aria-label="showPass ? '隐藏密码' : '显示密码'" @click="showPass = !showPass">
              <svg v-if="showPass" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /><path d="m4 4 16 16" /></svg>
              <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
            </button>
          </div>
        </div>
        <button class="btn btn-primary btn-block" :class="{ loading: busy }" :disabled="busy" style="margin-top:16px">登录后台</button>
      </form>
      <div v-if="DEV" id="demoTip" style="margin-top:16px;padding:10px 12px;background:var(--rose-pale);border-radius:10px;font-size:12px;color:var(--gray);text-align:center">
        🧪 种子账号：直接填 <b>ops</b> 或 <b>admin</b>（自动补全邮箱）· 密码 <b>glowmag123</b>
      </div>
      <div style="margin-top:14px;text-align:center;font-size:12px;color:var(--gray)">
        HttpOnly Cookie 会话 · 后台专用短时效令牌（需 role ≥ 2）
      </div>
      <div style="text-align:center;margin-top:16px">
        ← <a href="/" style="color:var(--plum)">返回店铺前台</a>
      </div>
    </div>
  </div>
</template>
