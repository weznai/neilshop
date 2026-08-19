<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { i18n } from '../i18n'
import { useUiStore } from '../stores/ui'

const ui = useUiStore()
const banner = ref(!localStorage.getItem('gm_consent'))
const settings = ref(false)
const model = reactive({
  ana: !!(JSON.parse(localStorage.getItem('gm_consent') || '{}').ana),
  mar: !!(JSON.parse(localStorage.getItem('gm_consent') || '{}').mar),
  per: !!(JSON.parse(localStorage.getItem('gm_consent') || '{}').per),
})
const ROWS = ['ana', 'mar', 'per']

function openSettings() {
  banner.value = false
  settings.value = true
}
function onOpenReq() { openSettings() }
onMounted(() => window.addEventListener('gm:open-consent', onOpenReq))
onUnmounted(() => window.removeEventListener('gm:open-consent', onOpenReq))

function save(c) {
  localStorage.setItem('gm_consent', JSON.stringify({ ...c, at: Date.now() }))
  banner.value = false
  settings.value = false
  ui.toast(i18n.t('consent.saved'), 'success')
}
function saveFromModal() {
  save({ nec: true, ana: model.ana, mar: model.mar, per: model.per })
}
</script>

<template>
  <div v-if="banner" class="consent-banner">
    <p style="font-size:13px;line-height:1.5;margin:0 0 12px" v-html="i18n.t('consent.text')" />
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn btn-primary btn-sm" @click="save({ nec: true, ana: true, mar: true, per: true })">
        {{ i18n.t('consent.accept') }}
      </button>
      <button class="btn btn-secondary btn-sm" @click="save({ nec: true, ana: false, mar: false, per: false })">
        {{ i18n.t('consent.reject') }}
      </button>
      <button class="btn btn-ghost btn-sm" @click="settings = true">{{ i18n.t('consent.manage') }}</button>
    </div>
  </div>

  <div v-if="settings" class="modal open" @click.self="settings = false">
    <div class="modal-box" style="max-width:520px">
      <button class="modal-x" style="font-size:22px" @click="settings = false">×</button>
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
        <div class="switch" :class="{ on: model[k] }" @click="model[k] = !model[k]"></div>
      </div>
      <button class="btn btn-primary btn-block" style="margin-top:18px" @click="saveFromModal">
        {{ i18n.t('consent.save') }}
      </button>
    </div>
  </div>
</template>
