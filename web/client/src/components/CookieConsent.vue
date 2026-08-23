<script setup>
import { nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { i18n } from '../i18n'
import { req } from '../api/client'
import { useUiStore } from '../stores/ui'

const ui = useUiStore()

function readConsent() {
  try { return JSON.parse(localStorage.getItem('gm_consent') || '{}') || {} } catch (_) { return {} }
}
const saved = readConsent()
const banner = ref(false)
try { banner.value = !localStorage.getItem('gm_consent') } catch (_) { banner.value = true }
const settings = ref(false)
const model = reactive({
  ana: !!saved.ana,
  mar: !!saved.mar,
  per: !!saved.per,
})
const ROWS = ['ana', 'mar', 'per']

function openSettings() {
  banner.value = false
  settings.value = true
}
function onOpenReq() { openSettings() }
function onEsc(e) { if (e.key === 'Escape' && settings.value) settings.value = false }

/* ===== a11y：settings 弹窗焦点管理（开→入框 / Esc 关 / 关→还焦）+ 简易 focus trap（对齐 MarketingPopups） ===== */
const settingsBox = ref(null)
let settingsFrom = null
function restoreFocus(el) {
  if (el && el !== document.body && document.contains(el)) {
    try { el.focus({ preventScroll: true }) } catch (_) { /* 触发元素已卸载 */ }
  }
}
function dialogFocusables(root) {
  if (!root) return []
  return [...root.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
}
function trapKeydown(e) {
  if (e.key !== 'Tab') return
  const box = settingsBox.value
  const f = dialogFocusables(box)
  if (!f.length) return
  const first = f[0]
  const last = f[f.length - 1]
  const inBox = box.contains(document.activeElement)
  if (e.shiftKey && (document.activeElement === first || !inBox)) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && (document.activeElement === last || !inBox)) { e.preventDefault(); first.focus() }
}
watch(settings, async (v) => {
  ui.consentOpen = v
  if (!v) {
    restoreFocus(settingsFrom)
    settingsFrom = null
    return
  }
  settingsFrom = document.activeElement
  await nextTick()
  const f = dialogFocusables(settingsBox.value)
  if (f.length) f[0].focus({ preventScroll: true })
})
onUnmounted(() => { ui.consentOpen = false })
onMounted(() => {
  window.addEventListener('gm:open-consent', onOpenReq)
  window.addEventListener('keydown', onEsc)
})
onUnmounted(() => {
  window.removeEventListener('gm:open-consent', onOpenReq)
  window.removeEventListener('keydown', onEsc)
})

/* 后台上报同意记录（POST /api/account/consent）：fire-and-forget，失败静默不打扰 UI */
function reportConsent(c) {
  let sid = ''
  try { sid = localStorage.getItem('gm_consent_sid') || '' } catch (_) { /* 隐私模式 */ }
  if (!sid) {
    sid = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : 'gm-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10)
    try { localStorage.setItem('gm_consent_sid', sid) } catch (_) { /* 隐私模式 */ }
  }
  req('POST', '/api/account/consent', {
    session_id: sid.slice(0, 36),
    necessary: true,
    analytics: !!c.ana,
    marketing: !!c.mar,
  }).catch(() => {})
}

function save(c) {
  try { localStorage.setItem('gm_consent', JSON.stringify({ ...c, at: Date.now() })) } catch (_) { /* 隐私模式等写入失败即弃 */ }
  reportConsent(c)
  banner.value = false
  settings.value = false
  window.dispatchEvent(new CustomEvent('gm:consent-saved'))
  ui.toast(i18n.t('consent.saved'), 'success')
}
function saveFromModal() {
  save({ nec: true, ana: model.ana, mar: model.mar, per: model.per })
}
</script>

<template>
  <div v-if="banner" class="consent-banner" role="region" :aria-label="i18n.t('consent.title')">
    <p style="font-size:13px;line-height:1.5;margin:0 0 12px" v-html="i18n.t('consent.text')" />
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn btn-primary btn-sm" @click="save({ nec: true, ana: true, mar: true, per: true })">
        {{ i18n.t('consent.accept') }}
      </button>
      <button class="btn btn-secondary btn-sm" @click="save({ nec: true, ana: false, mar: false, per: false })">
        {{ i18n.t('consent.reject') }}
      </button>
      <button class="btn btn-ghost btn-sm" @click="openSettings">{{ i18n.t('consent.manage') }}</button>
    </div>
  </div>

  <div v-if="settings" class="modal open" role="dialog" aria-modal="true" :aria-label="i18n.t('consent.title')" @click.self="settings = false">
    <div ref="settingsBox" class="modal-box" style="max-width:520px" @keydown="trapKeydown">
      <button class="modal-x" style="font-size:22px" :aria-label="i18n.lang === 'zh' ? '关闭' : 'Close'" @click="settings = false">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">{{ i18n.t('consent.title') }}</h3>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;padding:12px 0;border-bottom:1px solid var(--gray-light)">
        <div><b style="font-size:14px">{{ i18n.t('consent.nec') }}</b>
          <div style="font-size:12px;color:var(--gray)">{{ i18n.t('consent.nec.d') }}</div></div>
        <span class="tag tag-done">ALWAYS ON</span>
      </div>
      <div
        v-for="k in ROWS" :key="k"
        style="display:flex;justify-content:space-between;align-items:center;gap:16px;padding:12px 0;border-bottom:1px solid var(--gray-light)"
      >
        <div><b style="font-size:14px">{{ i18n.t('consent.' + k) }}</b>
          <div style="font-size:12px;color:var(--gray)">{{ i18n.t('consent.' + k + '.d') }}</div></div>
        <button class="switch" :class="{ on: model[k] }" :aria-pressed="model[k] ? 'true' : 'false'" @click="model[k] = !model[k]" />
      </div>
      <button class="btn btn-primary btn-block" style="margin-top:18px" @click="saveFromModal">
        {{ i18n.t('consent.save') }}
      </button>
    </div>
  </div>
</template>
