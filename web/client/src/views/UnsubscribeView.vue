<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import { useUiStore } from '../stores/ui'

const route = useRoute()
const ui = useUiStore()
const email = ref(String(route.query.email || ''))
const token = ref(String(route.query.token || ''))
const prefs = ref(null)
const saved = ref(false)

onMounted(async () => {
  try {
    prefs.value = await req('GET', '/api/account/email-preferences?email=' + encodeURIComponent(email.value) + '&token=' + encodeURIComponent(token.value))
  } catch (_) { /* 无 token 时提示登录 */ }
})

async function save() {
  try {
    await req('PUT', '/api/account/email-preferences?email=' + encodeURIComponent(email.value) + '&token=' + encodeURIComponent(token.value), {
      newsletter: prefs.value.newsletter ? 1 : 0,
      order_updates: prefs.value.order_updates ? 1 : 0,
      marketing: prefs.value.marketing ? 1 : 0,
    })
    saved.value = true
    ui.toast('Preferences saved ✓', 'success')
  } catch (e) {
    ui.toast(e.status === 401 ? 'Invalid or expired link — sign in to manage' : 'Save failed', 'error')
  }
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:560px">
      <div class="section-head"><h2 class="section-title">Email Preferences ✉️</h2></div>
      <div v-if="prefs" class="card" style="padding:22px">
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:16px">Managing preferences for <b>{{ email }}</b>. Turn everything off to unsubscribe from all mail.</p>
        <label v-for="k in ['newsletter', 'order_updates', 'marketing']" :key="k" style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--gray-light);font-size:14px">
          <span>{{ { newsletter: '📰 Newsletter & drops', order_updates: '📦 Order updates', marketing: '🎁 Offers & campaigns' }[k] }}</span>
          <input v-model="prefs[k]" type="checkbox" style="width:18px;height:18px">
        </label>
        <button class="btn btn-primary btn-block" style="margin-top:16px" @click="save">Save preferences</button>
        <p v-if="saved" style="font-size:12.5px;color:var(--success);text-align:center;margin-top:10px">Saved — changes apply to future sends immediately.</p>
      </div>
      <div v-else class="card" style="padding:22px;text-align:center;color:var(--gray)">
        This unsubscribe link is invalid or expired.
        <br><router-link to="/account/settings" style="color:var(--plum)">Manage from account settings</router-link> instead.
      </div>
    </div>
  </section>
</template>
