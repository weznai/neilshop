<script setup>
import { ref } from 'vue'
import { req } from '../api/client'

const no = ref('')
const email = ref('')
const result = ref(null)
const err = ref('')
const busy = ref(false)

const EVENTS = ['Order placed', 'Payment confirmed', 'Packing', 'Shipped', 'Out for delivery', 'Delivered']

async function track() {
  err.value = ''
  result.value = null
  if (!no.value.trim()) { err.value = 'Enter your order number (NS…)' ; return }
  busy.value = true
  try {
    result.value = await req('GET', '/api/orders/track?no=' + encodeURIComponent(no.value.trim()) + '&email=' + encodeURIComponent(email.value.trim()))
  } catch (e) {
    err.value = e.status === 404 ? 'Order not found — check the number & email' : 'Track failed, try later'
  } finally { busy.value = false }
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:560px">
      <div class="section-head"><h2 class="section-title">Track Order 🚚</h2></div>
      <div class="card" style="padding:24px">
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:16px">No login needed — order number + email used at checkout.</p>
        <form @submit.prevent="track">
          <div class="field"><label>Order number</label><input v-model="no" class="input" placeholder="NS260728D4E5F6"></div>
          <div class="field"><label>Email</label><input v-model="email" class="input" type="email" placeholder="you@example.com"></div>
          <div v-if="err" class="field-msg" style="color:var(--error)">{{ err }}</div>
          <button class="btn btn-primary btn-block" :class="{ loading: busy }" :disabled="busy">Track</button>
        </form>
      </div>

      <div v-if="result" class="card" style="padding:24px;margin-top:16px">
        <div style="display:flex;justify-content:space-between;margin-bottom:16px">
          <b>{{ result.order_no }}</b>
          <span class="tag" :class="result.status >= 3 ? 'tag-ship' : 'tag-pending'">
            {{ ['Pending', 'Paid', 'Packing', 'Shipped', 'Delivered', 'Done', 'Cancelled', 'Refunded', 'Expired', 'Refunded'][result.status] }}
          </span>
        </div>
        <div style="display:flex;gap:0">
          <div v-for="(l, i) in EVENTS.slice(0, result.status >= 4 ? 6 : 4)" :key="l" style="flex:1;text-align:center">
            <div :style="{ background: i <= result.status ? 'var(--success)' : 'var(--gray-light)' }"
                 style="width:24px;height:24px;border-radius:50%;margin:0 auto 6px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px">
              {{ i <= result.status ? '✓' : i + 1 }}
            </div>
            <div style="font-size:11px" :style="{ color: i <= result.status ? 'var(--ink)' : 'var(--gray)' }">{{ l }}</div>
          </div>
        </div>
        <div style="margin-top:14px;font-size:13.5px;color:var(--gray)">
          Carrier {{ result.carrier || 'USPS' }} · Tracking {{ result.tracking_no || '—' }}
        </div>
      </div>
    </div>
  </section>
</template>
