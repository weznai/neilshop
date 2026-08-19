<script setup>
/* 欢迎订阅弹窗（7s 后 · 一次）+ EXIT intent（每会话一次 · SAVE10 倒计时）——合并一个组件互斥 */
import { onMounted, onUnmounted, ref } from 'vue'
import { i18n } from '../i18n'
import { useUiStore } from '../stores/ui'
import { useCartStore } from '../stores/cart'
import { req } from '../api/client'

const ui = useUiStore()
const cart = useCartStore()

const welcome = ref(false)
const exit = ref(false)
const email = ref('')
const emailErr = ref(false)
const cd = ref('14:59')
let cdTimer = null

function closeWelcome() {
  welcome.value = false
  localStorage.setItem('gm_welcome', '1')
}
async function welcomeSubmit() {
  const v = email.value.trim()
  if (!v || !v.includes('@')) { emailErr.value = true; return }
  emailErr.value = false
  try { await req('POST', '/api/account/newsletter', { email: v }) } catch (_) { /* 演示容错 */ }
  ui.toast(i18n.t('welcome.toast'), 'success')
  closeWelcome()
}

function fireExit() {
  if (sessionStorage.getItem('gm_exit') || exit.value) return
  sessionStorage.setItem('gm_exit', '1')
  welcome.value = false
  exit.value = true
  let s = 15 * 60 - 1
  cdTimer = setInterval(() => {
    cd.value = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
    if (s-- <= 0) { clearInterval(cdTimer); exit.value = false }
  }, 1000)
}
function onMouseOut(e) {
  if (!e.relatedTarget && e.clientY <= 0) fireExit()
}

onMounted(() => {
  document.addEventListener('mouseout', onMouseOut)
  if (!localStorage.getItem('gm_welcome')) {
    setTimeout(() => {
      if (!localStorage.getItem('gm_welcome') && !exit.value && !localStorage.getItem('gm_consent')) return /* 横幅在场推迟 */
      if (!localStorage.getItem('gm_welcome') && !exit.value) welcome.value = true
    }, 7000)
  }
})
onUnmounted(() => {
  document.removeEventListener('mouseout', onMouseOut)
  if (cdTimer) clearInterval(cdTimer)
})
</script>

<template>
  <div v-if="welcome" class="modal open" @click.self="closeWelcome">
    <div class="modal-box welcome-box" style="max-width:420px;padding:0;overflow:hidden">
      <button class="modal-x" style="font-size:22px;color:#fff" @click="closeWelcome()">×</button>
      <div class="welcome-hero">
        <div style="font-size:40px;line-height:1">💅</div>
        <div class="welcome-brand">GLOWMAG</div>
      </div>
      <div style="padding:26px 28px 24px">
        <h3 style="font-family:var(--font-title);font-size:23px;margin-bottom:6px">{{ i18n.t('welcome.title') }}</h3>
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:16px">{{ i18n.t('welcome.sub') }}</p>
        <input v-model="email" class="input" :class="{ error: emailErr }" type="email" :placeholder="i18n.t('welcome.ph')" autocomplete="email">
        <div v-if="emailErr" class="field-msg">{{ i18n.t('welcome.err') }}</div>
        <button class="btn btn-block welcome-btn" style="margin-top:12px" @click="welcomeSubmit">{{ i18n.t('welcome.btn') }}</button>
        <div style="text-align:center;margin-top:10px">
          <a style="font-size:12.5px;color:var(--gray);text-decoration:underline" @click.prevent="closeWelcome()">{{ i18n.t('welcome.no') }}</a>
        </div>
      </div>
    </div>
  </div>

  <div v-if="exit" class="modal open" @click.self="exit = false">
    <div class="modal-box" style="text-align:center;max-width:420px">
      <button class="modal-x" style="font-size:22px" @click="exit = false">×</button>
      <div style="font-size:46px;margin-bottom:6px"> wait! 💅</div>
      <h3 style="font-family:var(--font-title);font-size:24px;margin-bottom:6px">
        {{ i18n.lang === 'zh' ? '走之前领个 9 折吧' : 'Take 10% off before you go' }}</h3>
      <p style="font-size:13.5px;color:var(--gray);margin-bottom:16px">
        {{ i18n.lang === 'zh' ? '专属折扣码 <b style="color:var(--plum)">SAVE10</b>，15 分钟内下单有效' : 'Code <b style="color:var(--plum)">SAVE10</b> — yours for the next 15 minutes' }}
      </p>
      <div style="background:var(--rose-pale);border-radius:10px;padding:14px;font-variant-numeric:tabular-nums;margin-bottom:16px">
        <b style="font-size:26px;letter-spacing:3px;color:var(--plum)">{{ cd }}</b>
      </div>
      <router-link to="/store" class="btn btn-primary btn-block" @click="exit = false">
        {{ i18n.lang === 'zh' ? '用掉它 →' : 'Use it now →' }}
      </router-link>
      <button class="btn btn-ghost btn-sm" style="margin-top:8px" @click="exit = false">
        {{ i18n.lang === 'zh' ? '不用了，谢谢' : 'No thanks' }}
      </button>
    </div>
  </div>
</template>
