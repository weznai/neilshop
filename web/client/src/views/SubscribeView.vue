<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'

const auth = useAuthStore()
const ui = useUiStore()
const sub = ref(null)
const PLANS = [
  { code: 'duo', name: 'The Duo', price: 27.98, per: 'every month', items: '2 sets of your choice', save: 'Save 10%' },
  { code: 'trio', name: 'The Trio', price: 38.97, per: 'every month', items: '3 sets + free shipping', save: 'Save 15%', best: true },
  { code: 'queen', name: 'Queen Box', price: 49.96, per: 'every 2 months', items: '4 sets + lashes + VIP gifts', save: 'Save 20%' },
]
const picked = ref('trio')

onMounted(async () => {
  if (auth.isLoggedIn) {
    try { sub.value = await req('GET', '/api/subscriptions/me') } catch (_) { /* */ }
  }
})
async function subscribe() {
  try {
    await req('POST', '/api/subscriptions', { plan: picked.value })
    sub.value = await req('GET', '/api/subscriptions/me')
    ui.toast('Welcome to the Nail Club! 💅', 'success')
  } catch (e) {
    ui.toast(e.status === 401 ? 'Sign in first to subscribe' : 'Subscribe failed', 'error')
  }
}
async function cancel() {
  try {
    await req('DELETE', '/api/subscriptions/' + (sub.value.id || sub.value.sub.id))
    sub.value = null
    ui.toast('Subscription cancelled', 'success')
  } catch (_) { ui.toast('Cancel failed', 'error') }
}
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:46px">📦</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Nail Club Subscription</h1>
        <p style="color:var(--gray)">Fresh sets on autopilot. Skip, swap or cancel anytime.</p>
      </div>

      <div v-if="sub && (sub.plan || sub.sub)" class="card" style="max-width:520px;margin:0 auto 26px;padding:20px">
        <b>Your subscription: {{ (sub.plan || sub.sub?.plan) || '—' }}</b>
        <div style="font-size:13px;color:var(--gray);margin:6px 0 12px">
          Next box {{ (sub.next_ship_at || sub.sub?.next_ship_at || '').slice(0, 10) || '—' }} · status {{ sub.status ?? sub.sub?.status }}
        </div>
        <button class="btn btn-ghost btn-sm" style="color:var(--error)" @click="cancel">Cancel subscription</button>
      </div>

      <div class="grid grid-3">
        <div
          v-for="p in PLANS" :key="p.code" class="card" style="padding:22px;cursor:pointer;position:relative"
          :style="{ outline: picked === p.code ? '2px solid var(--plum)' : '' }" @click="picked = p.code"
        >
          <span v-if="p.best" class="badge badge-best" style="position:absolute;top:-10px;right:14px">MOST LOVED</span>
          <b style="font-family:var(--font-title);font-size:20px">{{ p.name }}</b>
          <div style="margin:10px 0 4px"><b style="font-size:28px">${{ p.price.toFixed(2) }}</b> <span style="color:var(--gray);font-size:13px">{{ p.per }}</span></div>
          <div style="font-size:13.5px;color:var(--gray);margin-bottom:12px">{{ p.items }}</div>
          <span class="tag tag-paid">{{ p.save }}</span>
        </div>
      </div>
      <div style="text-align:center;margin-top:22px">
        <button class="btn btn-primary btn-lg" @click="subscribe">Subscribe · {{ picked }}</button>
      </div>
    </div>
  </section>
</template>
