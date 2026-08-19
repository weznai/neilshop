<script setup>
import { onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { req } from '../api/client'

const auth = useAuthStore()
const pts = ref(null)
onMounted(async () => {
  if (auth.isLoggedIn) {
    try { pts.value = await req('GET', '/api/points') } catch (_) { /* */ }
  }
})
const TIERS = [
  ['Glow', '$0+', '1× pts · birthday gift'],
  ['Shimmer', '$50+', '1.25× pts · early drops'],
  ['Diva', '$150+', '1.5× pts · free express over $50'],
  ['Queen', '$300+', '2× pts · VIP box quarterly'],
]
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:46px">⭐</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Glow Rewards</h1>
        <p style="color:var(--gray)">100 pts = $1 · points never expire for members</p>
      </div>

      <div v-if="pts" class="card" style="max-width:460px;margin:0 auto 26px;padding:18px;text-align:center">
        <div style="font-size:12.5px;color:var(--gray)">Your balance</div>
        <b style="font-family:var(--font-title);font-size:36px;color:var(--plum)">{{ (pts.usable || 0).toLocaleString() }} pts</b>
        <div style="font-size:13px;color:var(--gray)">≈ ${{ ((pts.usable || 0) / 100).toFixed(2) }} off at checkout</div>
      </div>

      <div class="grid grid-4">
        <div v-for="(t, i) in TIERS" :key="t[0]" class="card" style="padding:20px;text-align:center" :style="{ background: i === (auth.user?.tier || 0) ? 'var(--rose-pale)' : '' }">
          <b style="font-family:var(--font-title);font-size:19px">{{ t[0] }}</b>
          <div style="font-size:12.5px;color:var(--plum);margin:4px 0 8px">{{ t[1] }} spent</div>
          <div style="font-size:12.5px;color:var(--gray)">{{ t[2] }}</div>
          <div v-if="i === (auth.user?.tier || 0)" class="tag tag-paid" style="margin-top:8px">YOUR TIER</div>
        </div>
      </div>

      <div class="card" style="margin-top:22px;padding:20px">
        <h3 style="font-size:15px;margin-bottom:10px">How to earn</h3>
        <div style="display:grid;gap:8px;font-size:13.5px">
          <div style="display:flex;justify-content:space-between"><span>Place an order</span><b>+1 pt / $1</b></div>
          <div style="display:flex;justify-content:space-between"><span>Write a review</span><b>+50 pts</b></div>
          <div style="display:flex;justify-content:space-between"><span>Refer a friend</span><b>+500 pts</b></div>
          <div style="display:flex;justify-content:space-between"><span>Birthday month</span><b>+200 pts</b></div>
        </div>
      </div>
    </div>
  </section>
</template>
