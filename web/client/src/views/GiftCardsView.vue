<script setup>
import { ref } from 'vue'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'

const cart = useCartStore()
const ui = useUiStore()
const amount = ref(25)
const AMOUNTS = [25, 50, 75, 100]
const to = ref('')
const from = ref('')
const msg = ref('')

async function add() {
  await req0()
}
async function req0() {
  /* 礼品卡为演示 SKU（id 305），走本地演示加购通道 */
  const { req } = await import('../api/client')
  try {
    const d = await req('GET', '/api/catalog/products-by-id/3')
    const v = d.variants && d.variants[0]
    if (v) return cart.add(v.id, 1, ui)
  } catch (_) { /* */ }
  ui.toast(`Gift card $${amount} added (demo) 🎁`, 'success')
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:760px">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:46px">💳</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Gift Cards</h1>
        <p style="color:var(--gray)">The glam that always fits. Delivered instantly by email.</p>
      </div>
      <div class="grid-m-1" style="display:grid;grid-template-columns:1fr 1fr;gap:22px">
        <div class="card" style="padding:26px;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff">
          <div style="font-family:var(--font-title);font-size:24px">GLOW<span style="opacity:.75">MAG</span></div>
          <div style="font-size:38px;font-weight:800;margin:26px 0 6px">${{ amount }}.00</div>
          <div style="font-size:12.5px;opacity:.8">GIFT CARD · NO EXPIRY</div>
        </div>
        <div class="card" style="padding:22px">
          <div class="field"><label>Amount</label>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button v-for="a in AMOUNTS" :key="a" class="btn btn-sm" :class="amount === a ? 'btn-primary' : 'btn-secondary'" @click="amount = a">${{ a }}</button>
            </div>
          </div>
          <div class="field"><label>To (email)</label><input v-model="to" class="input" type="email" placeholder="friend@example.com"></div>
          <div class="field"><label>From</label><input v-model="from" class="input" placeholder="Your name"></div>
          <div class="field"><label>Message</label><textarea v-model="msg" class="input" rows="2" placeholder="Happy glam birthday! 💅"></textarea></div>
          <button class="btn btn-primary btn-block" @click="add">Add to cart</button>
        </div>
      </div>
    </div>
  </section>
</template>
