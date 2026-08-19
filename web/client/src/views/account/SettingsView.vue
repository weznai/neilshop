<script setup>
import { onMounted, reactive, ref } from 'vue'
import { req } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { useUiStore } from '../../stores/ui'

const auth = useAuthStore()
const ui = useUiStore()
const form = reactive({ name: '', birthday: '' })
const exporting = ref(false)
const deleting = ref(false)

onMounted(() => {
  if (auth.user) {
    form.name = auth.user.name || ''
    form.birthday = auth.user.birthday || ''
  }
})

async function save() {
  try {
    await req('PUT', '/api/account/me', { name: form.name, birthday: form.birthday || null })
    await auth.me()
    ui.toast('Profile saved ✓', 'success')
  } catch (_) { ui.toast('Save failed', 'error') }
}
async function exportData() {
  exporting.value = true
  try {
    const d = await req('GET', '/api/account/export')
    const blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `glowmag-my-data-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    ui.toast('Data exported ✓', 'success')
  } catch (_) { ui.toast('Export failed', 'error') }
  finally { exporting.value = false }
}
async function deleteAccount() {
  if (!confirm('Request account deletion? We anonymize your data within 30 days (GDPR).')) return
  deleting.value = true
  try {
    await req('POST', '/api/account/delete-request')
    ui.toast('Deletion requested — you can cancel within 30 days', 'success')
  } catch (_) { ui.toast('Request failed', 'error') }
  finally { deleting.value = false }
}
</script>

<template>
  <div style="display:grid;gap:16px">
    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:14px">Profile</h3>
      <div class="field"><label>Name</label><input v-model="form.name" class="input"></div>
      <div class="field"><label>Birthday</label><input v-model="form.birthday" class="input" type="date"></div>
      <div class="field"><label>Email</label><input :value="auth.user?.email" class="input" disabled style="background:var(--rose-pale)"></div>
      <button class="btn btn-primary" @click="save">Save profile</button>
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:8px">Privacy (GDPR / CCPA)</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:12px">Download everything we store about you, or request full anonymization.</p>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn btn-secondary btn-sm" :class="{ loading: exporting }" @click="exportData">⬇ Export my data</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--error)" :class="{ loading: deleting }" @click="deleteAccount">🗑 Delete account</button>
      </div>
    </div>
  </div>
</template>
