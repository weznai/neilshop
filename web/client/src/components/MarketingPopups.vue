<script setup>
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { i18n } from '../i18n'
import { useUiStore } from '../stores/ui'
import { req } from '../api/client'

const ui = useUiStore()

const welcome = ref(null)
const exitPop = ref(null)
const showWelcome = ref(false)
const showExit = ref(false)
const email = ref('')
const emailErr = ref(false)
const wBusy = ref(false) /* 订阅提交中（防双击） */

function isMobile() { return window.matchMedia('(max-width: 768px)').matches }
function today() { return new Date().toISOString().slice(0, 10) }
function capKey(p) { return 'gm_popup_' + p.id + '_' + p.scene }
function seenToday(p) { return localStorage.getItem(capKey(p)) === today() }
function markSeen(p) { localStorage.setItem(capKey(p), today()) }
function exitSeen() { return !!sessionStorage.getItem('gm_exit') }
function markExitSeen() { sessionStorage.setItem('gm_exit', '1') }
function consentReady() { return !!localStorage.getItem('gm_consent') }

function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
function mdHtml(s) {
  return esc(s).replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/\n{2,}/g, '<br><br>').replace(/\n/g, '<br>')
}
const zh = () => i18n.lang === 'zh'

async function fetchPopup(scene) {
  try { return await req('GET', '/api/promo/popup?scene=' + scene) } catch (_) { return null }
}

/* 曝光/转化上报（后端原子自增 stats_shown/stats_converted；失败静默不打扰用户） */
function report(kind, id) {
  if (!id) return
  req('POST', `/api/promo/popup/${id}/${kind}`).catch(() => { /* 静默 */ })
}

function closeWelcome() {
  showWelcome.value = false
  restoreFocus(welcomeFrom)
  welcomeFrom = null
}
function closeExit() {
  showExit.value = false
  restoreFocus(exitFrom)
  exitFrom = null
}

/* ===== a11y：dialog 焦点管理（开→入框 / Esc 关 / 关→还焦）+ 简易 focus trap ===== */
const welcomeBox = ref(null)
const exitBox = ref(null)
const emailInput = ref(null)
const exitCloseBtn = ref(null)
let welcomeFrom = null
let exitFrom = null

function restoreFocus(el) {
  if (el && el !== document.body && document.contains(el)) {
    try { el.focus({ preventScroll: true }) } catch (_) { /* 触发元素已卸载 */ }
  }
}
function dialogFocusables(root) {
  if (!root) return []
  return [...root.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
}
function trapKeydown(e, boxEl) {
  if (e.key === 'Tab') {
    const f = dialogFocusables(boxEl)
    if (!f.length) return
    const first = f[0]
    const last = f[f.length - 1]
    const inBox = boxEl.contains(document.activeElement)
    if (e.shiftKey && (document.activeElement === first || !inBox)) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && (document.activeElement === last || !inBox)) { e.preventDefault(); first.focus() }
  }
}
function onEscKey(e) {
  if (e.key !== 'Escape') return
  if (showWelcome.value) closeWelcome()
  else if (showExit.value) closeExit()
}
watch(showWelcome, async (v) => {
  if (!v) return
  welcomeFrom = document.activeElement
  await nextTick()
  if (emailInput.value) emailInput.value.focus({ preventScroll: true })
})
watch(showExit, async (v) => {
  if (!v) return
  exitFrom = document.activeElement
  await nextTick()
  if (exitCloseBtn.value) exitCloseBtn.value.focus({ preventScroll: true })
})
/* 弹窗开合上报 ui store：body 滚动锁由 StoreLayout 统一 watch anyOverlay 处理 */
watch([showWelcome, showExit], ([w, x]) => { ui.popupsOpen = !!(w || x) })
async function welcomeSubmit() {
  if (wBusy.value) return
  const v = email.value.trim()
  if (!v || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) { emailErr.value = true; return }
  emailErr.value = false
  wBusy.value = true
  try {
    await req('POST', '/api/account/newsletter', { email: v, source: 'welcome_popup' })
    /* 转化上报仅在订阅成功后发 */
    report('convert', welcome.value && welcome.value.id)
    ui.toast(i18n.t('welcome.toast'), 'success')
    closeWelcome()
  } catch (_) {
    ui.toast(zh() ? '订阅失败，请稍后再试' : 'Subscribe failed — please try again', 'error')
  } finally { wBusy.value = false }
}

async function copyCode(code, popupId) {
  try { await navigator.clipboard.writeText(code) } catch (_) {
    const ta = document.createElement('textarea')
    ta.value = code; document.body.appendChild(ta); ta.select()
    try { document.execCommand('copy') } catch (__) { /* noop */ }
    document.body.removeChild(ta)
  }
  report('convert', popupId)
  ui.toast((zh() ? '已复制 ' : 'Copied ') + code, 'success')
}

function fireWelcome(p) {
  if (seenToday(p) || showExit.value) return
  welcome.value = p
  markSeen(p)
  showWelcome.value = true
  report('shown', p.id)
}
function onConsentThen(p) {
  window.addEventListener('gm:consent-saved', () => fireWelcome(p), { once: true })
}
function onExitOut(e) {
  if (e.relatedTarget || e.clientY > 0) return
  const p = exitPop.value
  if (!p || exitSeen() || showWelcome.value) return
  markExitSeen()
  exitPop.value = p
  showExit.value = true
  report('shown', p.id)
}

onMounted(async () => {
  document.addEventListener('keydown', onEscKey)
  /* 两个弹窗配置并行拉取（互不阻塞） */
  const [w, e] = await Promise.all([fetchPopup('welcome'), fetchPopup('exit_intent')])

  if (e) {
    const r = e.trigger_rules || {}
    if (!(r.mobileOnly && !isMobile())) {
      exitPop.value = e
      document.addEventListener('mouseout', onExitOut)
    }
  }

  if (w) {
    const r = w.trigger_rules || {}
    if (r.mobileOnly && !isMobile()) return
    if (r.exitIntent) return
    const delay = Math.max(0, Number(r.delaySec == null ? 7 : r.delaySec)) * 1000
    setTimeout(() => {
      if (showExit.value || seenToday(w)) return
      if (!consentReady()) { onConsentThen(w); return }
      fireWelcome(w)
    }, delay)
  }
})
onUnmounted(() => {
  document.removeEventListener('mouseout', onExitOut)
  document.removeEventListener('keydown', onEscKey)
  ui.popupsOpen = false
})
</script>

<template>
  <div v-if="showWelcome && welcome" class="modal open" @click.self="closeWelcome">
    <div
      ref="welcomeBox" class="modal-box welcome-box" style="max-width:420px;padding:0;overflow:hidden"
      role="dialog" aria-modal="true" :aria-label="welcome.title"
      @keydown="trapKeydown($event, welcomeBox)"
    >
      <button
        class="modal-x" style="font-size:22px;color:#fff"
        :aria-label="zh() ? '关闭' : 'Close'"
        @click="closeWelcome()"
      >×</button>
      <div class="welcome-hero">
        <div style="font-size:40px;line-height:1">💅</div>
        <div class="welcome-brand">GLOWMAG</div>
      </div>
      <div style="padding:26px 28px 24px">
        <h3 style="font-family:var(--font-title);font-size:23px;margin-bottom:6px">{{ welcome.title }}</h3>
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:14px;line-height:1.6" v-html="mdHtml(welcome.content_md)" />
        <div v-if="welcome.coupon_code" style="display:flex;align-items:center;justify-content:space-between;gap:10px;background:var(--rose-pale);border:1.5px dashed var(--rose);border-radius:10px;padding:10px 14px;margin-bottom:16px">
          <b style="font-size:17px;letter-spacing:2px;color:var(--plum)">{{ welcome.coupon_code }}</b>
          <button class="btn btn-secondary btn-sm" style="height:32px;padding:0 12px" @click="copyCode(welcome.coupon_code, welcome.id)">
            {{ zh() ? '复制' : 'Copy' }}
          </button>
        </div>
        <input
          ref="emailInput" v-model="email" class="input" :class="{ error: emailErr }" type="email"
          :placeholder="i18n.t('welcome.ph')" autocomplete="email"
          :aria-label="i18n.t('welcome.ph')" :aria-invalid="emailErr || undefined"
          :aria-describedby="emailErr ? 'gm-welcome-err' : undefined"
        >
        <div v-if="emailErr" id="gm-welcome-err" class="field-msg" style="display:block" role="alert">{{ i18n.t('welcome.err') }}</div>
        <button class="btn btn-block welcome-btn" style="margin-top:12px" :disabled="wBusy" @click="welcomeSubmit">{{ wBusy ? '…' : i18n.t('welcome.btn') }}</button>
        <div style="text-align:center;margin-top:10px">
          <button
            type="button"
            style="font-size:12.5px;color:var(--gray);text-decoration:underline"
            @click="closeWelcome()"
          >{{ i18n.t('welcome.no') }}</button>
        </div>
      </div>
    </div>
  </div>

  <div v-if="showExit && exitPop" class="modal open" @click.self="closeExit">
    <div
      ref="exitBox" class="modal-box" style="text-align:center;max-width:420px"
      role="dialog" aria-modal="true" :aria-label="exitPop.title"
      @keydown="trapKeydown($event, exitBox)"
    >
      <button
        ref="exitCloseBtn" class="modal-x" style="font-size:22px"
        :aria-label="zh() ? '关闭' : 'Close'"
        @click="closeExit()"
      >×</button>
      <div style="font-size:40px;margin-bottom:6px">💅</div>
      <h3 style="font-family:var(--font-title);font-size:23px;margin-bottom:6px">{{ exitPop.title }}</h3>
      <p style="font-size:13.5px;color:var(--gray);margin-bottom:14px;line-height:1.6" v-html="mdHtml(exitPop.content_md)" />
      <div v-if="exitPop.coupon_code" style="display:flex;align-items:center;justify-content:center;gap:12px;background:var(--rose-pale);border:1.5px dashed var(--rose);border-radius:10px;padding:12px;margin-bottom:16px">
        <b style="font-size:22px;letter-spacing:3px;color:var(--plum)">{{ exitPop.coupon_code }}</b>
        <button class="btn btn-secondary btn-sm" style="height:32px;padding:0 12px" @click="copyCode(exitPop.coupon_code, exitPop.id)">
          {{ zh() ? '复制' : 'Copy' }}
        </button>
      </div>
      <router-link to="/store" class="btn btn-primary btn-block" @click="closeExit()">
        {{ zh() ? '去逛逛 →' : 'Shop now →' }}
      </router-link>
      <button class="btn btn-ghost btn-sm" style="margin-top:8px" @click="closeExit()">
        {{ zh() ? '不用了，谢谢' : 'No thanks' }}
      </button>
    </div>
  </div>
</template>
