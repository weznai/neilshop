<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'

const auth = useAuthStore()
const ui = useUiStore()
const me = ref(null)

onMounted(async () => {
  if (auth.isLoggedIn) {
    try { me.value = await req('GET', '/api/referrals/me') } catch (_) { /* */ }
  }
})
async function copyLink() {
  const link = me.value?.link || 'https://glowmag.com/r/GLOWMAG'
  try { await navigator.clipboard.writeText(link); ui.toast('Referral link copied 💜', 'success') }
  catch (_) { ui.toast(link, '') }
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:680px;text-align:center">
      <div style="font-size:46px;margin-bottom:6px">🎁</div>
      <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Give $10, Get $10</h1>
      <p style="color:var(--gray);margin-bottom:22px">
        Share your link — friend gets $10 off their first order, you get $10 in points (500 pts) once they order.
      </p>
      <div class="card" style="padding:20px;display:flex;gap:10px;align-items:center;max-width:480px;margin:0 auto 18px">
        <code style="flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          {{ me?.link || 'glowmag.com/r/…' }}
        </code>
        <button class="btn btn-primary btn-sm" @click="copyLink">Copy link</button>
      </div>
      <div v-if="me" class="grid grid-3" style="max-width:520px;margin:0 auto">
        <div class="card" style="padding:16px"><b style="font-size:24px">{{ me.invited || 0 }}</b><div style="font-size:12px;color:var(--gray)">Invited</div></div>
        <div class="card" style="padding:16px"><b style="font-size:24px;color:var(--plum)">{{ me.completed || 0 }}</b><div style="font-size:12px;color:var(--gray)">Converted</div></div>
        <div class="card" style="padding:16px"><b style="font-size:24px;color:var(--success)">{{ me.earned_pts || 0 }}</b><div style="font-size:12px;color:var(--gray)">Pts earned</div></div>
      </div>
      <p v-else style="font-size:13px;color:var(--gray)">
        <router-link :to="{ path: '/login', query: { next: '/refer' } }" style="color:var(--plum)">Sign in</router-link> to see your referral stats.
      </p>
    </div>
  </section>
</template>
