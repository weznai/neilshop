<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const email = ref('admin@glowmag.com')
const password = ref('')
const showPass = ref(false)
const busy = ref(false)

function normEmail() {
  let v = (email.value || '').trim().replace(/\s+/g, '')
  v = v.replace(/[\uFF01-\uFF5E]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xFEE0))
  if (/^(admin|ops|cs|emma)$/i.test(v)) v += '@glowmag.com'
  email.value = v.toLowerCase()
}

async function submit() {
  normEmail()
  if (!email.value.includes('@')) { window.$gmToast('邮箱无法识别——直接填 ops 或 admin 即可', 'error'); return }
  if (!password.value) { window.$gmToast('请输入密码（演示密码统一 glowmag123）', 'error'); return }
  busy.value = true
  try {
    const u = await session.login(email.value, password.value)
    if ((u.role | 0) < 2) {
      window.$gmToast('该账号无后台权限（需管理员账号）', 'error')
      await session.logout()
      return
    }
    router.push(route.query.next ? String(route.query.next) : '/')
  } catch (e) {
    window.$gmToast(
      e.status === 422 ? '邮箱格式无效——请用半角 @（或直接填 ops / admin 快捷名）'
        : e.status === 401 ? '邮箱或密码错误（密码统一 glowmag123）'
          : e.status === 403 ? '该账号无后台权限（需管理员账号）'
            : '登录失败：' + (e.message || '请稍后重试'),
      'error',
    )
  } finally { busy.value = false }
}
</script>

<template>
  <div class="alogin-page">
    <div class="alogin card" style="max-width:400px;width:100%;padding:34px 32px">
      <div style="text-align:center;margin-bottom:22px">
        <div class="logo" style="font-size:26px;color:var(--ink)">GLOW<span style="color:var(--rose)">MAG</span></div>
        <div style="font-size:11px;letter-spacing:3px;color:var(--gray);margin-top:6px">管理控制台 · ADMIN</div>
      </div>
      <form @submit.prevent="submit">
        <div class="field">
          <label>邮箱</label>
          <input v-model="email" class="input" autocomplete="username" placeholder="ops / admin / 完整邮箱">
        </div>
        <div class="field">
          <label>密码</label>
          <div style="position:relative">
            <input v-model="password" class="input" :type="showPass ? 'text' : 'password'" autocomplete="current-password" placeholder="glowmag123" style="padding-right:44px">
            <button type="button" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:var(--gray);font-size:13px" @click="showPass = !showPass">
              {{ showPass ? '隐藏' : '显示' }}
            </button>
          </div>
        </div>
        <button class="btn btn-primary btn-block" :class="{ loading: busy }" :disabled="busy" style="margin-top:16px">登录后台</button>
      </form>
      <div id="demoTip" style="margin-top:16px;padding:10px 12px;background:var(--rose-pale);border-radius:10px;font-size:12px;color:var(--gray);text-align:center">
        🧪 种子账号：直接填 <b>ops</b> 或 <b>admin</b>（自动补全邮箱）· 密码 <b>glowmag123</b>
      </div>
      <div style="margin-top:14px;text-align:center;font-size:12px;color:var(--gray)">
        HttpOnly Cookie 会话 · 后台专用短时效令牌（需 role ≥ 2）
      </div>
      <div class="login-back" style="text-align:center;margin-top:16px">
        ← <a href="/" style="color:var(--plum)">返回店铺前台</a>
      </div>
    </div>
  </div>
</template>
