<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { firstAllowedPath } from '../constants/nav'
import { toast } from '../composables/toast'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()

const email = ref('')
const emailEl = ref(null)
const password = ref('')
const showPass = ref(false)
const busy = ref(false)
/* 字段级 inline 错误（.field.error + .field-msg）+ 表单级错误横幅（服务端失败） */
const emailErr = ref('')
const passErr = ref('')
const formErr = ref('')
/* 演示账号/密码提示仅 DEV 出现，生产构建不泄露种子账号 */
const DEV = import.meta.env.DEV

/* 已登录访问 /login：回第一个有权页面（客服/美甲师无看板权限，不再固定 '/'） */
onMounted(() => {
  if (session.user) { router.replace(firstAllowedPath(session.hasPerm)); return }
  nextTick(() => emailEl.value?.focus())
})

/* 输入即清除对应字段错误 */
watch(email, () => { emailErr.value = '' })
watch(password, () => { passErr.value = '' })

function normEmail() {
  let v = (email.value || '').trim().replace(/\s+/g, '')
  v = v.replace(/[\uFF01-\uFF5E]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xFEE0))
  /* 快捷名自动补全仅 DEV 生效（与底部种子账号提示条一致），生产不泄露快捷账号 */
  if (DEV && /^(admin|ops|cs|emma)$/i.test(v)) v += '@glowmag.com'
  email.value = v.toLowerCase()
}

/* 服务端错误映射（横幅与 toast 共用同一文案） */
function srvMsg(e) {
  return e.status === 422 ? '邮箱格式无效——请用半角 @' + (DEV ? '（或直接填 ops / admin 快捷名）' : '')
    : e.status === 401 ? '邮箱或密码错误' + (DEV ? '（密码统一 glowmag123）' : '')
      : e.status === 403 ? '该账号无后台权限（需后台角色账号）'
        : e.status === 429 ? '尝试过于频繁，请稍后再试'
          : '登录失败：' + (e.message || '请稍后重试')
}

async function submit() {
  normEmail()
  emailErr.value = ''
  passErr.value = ''
  formErr.value = ''
  if (!email.value.includes('@')) { emailErr.value = DEV ? '邮箱无法识别——直接填 ops 或 admin 即可' : '邮箱格式无效，请输入完整邮箱'; return }
  if (!password.value) { passErr.value = DEV ? '请输入密码（演示密码统一 glowmag123）' : '请输入密码'; return }
  busy.value = true
  try {
    /* 登录响应已含 user + permissions（后台角色由后端闸门保证），无需再 verify() 探测 */
    await session.login(email.value, password.value)
    toast('登录成功，进入管理控制台…', 'success')
    /* next 白名单校验：仅接受站内单斜杠路径（拒绝 //evil.com 协议相对与 \ ? # 起始），
     * 含控制字符的输入一并拒绝；默认落地 = 第一个有权菜单（客服→工单面等） */
    const n = String(route.query.next || '')
    router.push(/^\/[^/\\?#]/.test(n) && !/[\x00-\x1f\x7f]/.test(n)
      ? n : firstAllowedPath(session.hasPerm))
  } catch (e) {
    console.error('[admin] 登录失败：', e)
    formErr.value = srvMsg(e)
    toast(srvMsg(e), 'error')
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
      <form @submit.prevent="submit" novalidate>
        <div v-if="formErr" class="err-banner login-err" role="alert">{{ formErr }}</div>
        <div class="field" :class="{ error: !!emailErr }">
          <label for="loginEmail">邮箱</label>
          <input ref="emailEl" id="loginEmail" v-model="email" class="input" autofocus autocomplete="username" :placeholder="DEV ? 'ops / admin / 完整邮箱' : '管理员邮箱'">
          <div class="field-msg">{{ emailErr }}</div>
        </div>
        <div class="field" :class="{ error: !!passErr }">
          <label for="loginPass">密码</label>
          <div class="pw-wrap">
            <input id="loginPass" v-model="password" class="input" :type="showPass ? 'text' : 'password'" autocomplete="current-password" :placeholder="DEV ? 'glowmag123' : '密码'">
            <button type="button" class="pw-eye" :aria-label="showPass ? '隐藏密码' : '显示密码'" @click="showPass = !showPass">
              <svg v-if="showPass" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /><path d="m4 4 16 16" /></svg>
              <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>
            </button>
          </div>
          <div class="field-msg">{{ passErr }}</div>
        </div>
        <button class="btn btn-primary btn-block" :class="{ loading: busy }" :disabled="busy" style="margin-top:16px">登录后台</button>
      </form>
      <div v-if="DEV" id="demoTip" style="margin-top:16px;padding:10px 12px;background:var(--rose-pale);border-radius:10px;font-size:12px;color:var(--gray);text-align:center">
        🧪 种子账号：直接填 <b>ops</b> 或 <b>admin</b>（自动补全邮箱）· 密码取 <b>GM_SEED_PASSWORD</b>（未设置时 seed 随机生成并打印一次）
      </div>
      <div style="margin-top:14px;text-align:center;font-size:12px;color:var(--gray)">
        HttpOnly Cookie 会话 · 后台专用短时效令牌（后台角色账号）
      </div>
      <div style="text-align:center;margin-top:16px">
        ← <a href="/" style="color:var(--plum)">返回店铺前台</a>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 表单顶错误横幅：复用全局 .err-banner 视觉，收窄外边距适配登录卡 */
.login-err{margin:0 0 14px}
/* 字段错误时输入框同步红边（.field-msg 的显隐由 style.css .field.error 接管） */
.field.error .input{border-color:var(--error)}
</style>
