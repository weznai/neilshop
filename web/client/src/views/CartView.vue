<script setup>
import { computed, ref } from 'vue'
import { i18n } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { req } from '../api/client'

const cart = useCartStore()
const ui = useUiStore()

const code = ref('')
const applied = ref(null) /* {code, disc, freeship} */
const DEMO_CODES = {
  WELCOME20: { type: 'pct', value: 20, max: 10, min: 0 },
  EARLYBIRD: { type: 'pct', value: 25, max: 15, min: 20 },
  FREESHIP: { type: 'ship', value: 0 },
  BYE2025: { type: 'pct', value: 25, max: 20, min: 30 },
  SAVE10: { type: 'pct', value: 10, max: 8, min: 0 },
}

const hasLash = computed(() => cart.items.some((i) => /lash/i.test(i.title)))
const hasNail = computed(() => cart.items.some((i) => !/lash/i.test(i.title)))
const bundleDisc = computed(() => {
  const n = cart.items.reduce((n, i) => n + i.qty, 0)
  if (n >= 3) return cart.subtotal * 0.2
  if (n >= 2) return cart.subtotal * 0.15
  return 0
})
const disc = computed(() => (applied.value?.disc || 0) + bundleDisc.value)
const freeship = computed(() => cart.subtotal >= 35 || applied.value?.freeship)
const total = computed(() => cart.subtotal - disc.value)

function applyCode() {
  const c = DEMO_CODES[code.value.toUpperCase().trim()]
  const sub = cart.subtotal
  if (!c) { ui.toast(`Code "${code.value.toUpperCase()}" not found`, 'error'); applied.value = null; return }
  if (sub < c.min) { ui.toast(`Spend $${(c.min - sub).toFixed(2)} more to use this code`, 'error'); applied.value = null; return }
  const d = c.type === 'pct' ? Math.min((sub * c.value) / 100, c.max) : 0
  applied.value = { code: code.value.toUpperCase(), disc: d, freeship: c.type === 'ship' }
  ui.toast(`${code.value.toUpperCase()} applied — you save $${d.toFixed(2)}`, 'success')
}
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head"><h2 class="section-title">{{ i18n.t('cart.title') }}</h2></div>

      <div v-if="!cart.items.length" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:52px;margin-bottom:12px">🛒</div>
        <p style="margin-bottom:18px">{{ i18n.t('cart.empty') }}</p>
        <router-link class="btn btn-primary" to="/">{{ i18n.t('cart.shop') }}</router-link>
      </div>

      <div v-else class="grid-m-1" style="display:grid;grid-template-columns:1.6fr 1fr;gap:32px;align-items:start">
        <div class="card" style="padding:8px 20px">
          <div
            v-for="i in cart.items" :key="i.id"
            style="display:flex;gap:14px;padding:18px 0;border-bottom:1px solid var(--gray-light)"
          >
            <router-link :to="`/product?id=${i.pid}`">
              <img :src="i.img" :alt="i.title" style="width:88px;height:88px;border-radius:12px;object-fit:cover">
            </router-link>
            <div style="flex:1">
              <div style="display:flex;justify-content:space-between;gap:10px">
                <div>
                  <b style="font-size:15px">{{ i.title }}</b>
                  <div style="font-size:12.5px;color:var(--gray)">{{ i.variant }}</div>
                </div>
                <b style="font-size:15px;color:var(--plum)">${{ (i.price * i.qty).toFixed(2) }}</b>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px">
                <div style="display:flex;align-items:center;border:1px solid var(--gray-light);border-radius:8px">
                  <button class="qbtn" @click="cart.setQty(i.vid, i.qty - 1, ui)">−</button>
                  <span style="width:34px;text-align:center;font-weight:600;font-size:13px">{{ i.qty }}</span>
                  <button class="qbtn" @click="cart.setQty(i.vid, i.qty + 1, ui)">＋</button>
                </div>
                <button
                  class="btn btn-ghost btn-sm"
                  :data-arm="i.vid" @click="cart.remove(i.vid, ui)"
                >Remove</button>
              </div>
            </div>
          </div>
          <div v-if="bundleDisc" style="padding:14px 0;font-size:13px;color:var(--success);font-weight:600">
            🎁 Bundle discount applied — save ${{ bundleDisc.toFixed(2) }}
          </div>
          <div v-if="hasLash && !hasNail" style="padding:14px 0;font-size:13px;color:var(--gray)">
            💅 Pairs perfectly with press-on nails — <router-link to="/store?cat=nails" style="color:var(--plum)">shop sets</router-link>
          </div>
        </div>

        <div class="card" style="padding:22px;position:sticky;top:20px">
          <div style="display:flex;gap:8px;margin-bottom:16px">
            <input v-model="code" class="input" placeholder="Discount code" style="text-transform:uppercase">
            <button class="btn btn-secondary" @click="applyCode">Apply</button>
          </div>
          <div id="summaryRows" style="display:grid;gap:10px;font-size:14px">
            <div class="srow"><span>{{ i18n.t('cart.subtotal') }}</span><span class="val">${{ cart.subtotal.toFixed(2) }}</span></div>
            <div v-if="disc" class="srow" style="color:var(--success)">
              <span>Discount</span><span>−${{ disc.toFixed(2) }}</span>
            </div>
            <div class="srow">
              <span>Shipping</span>
              <span class="val">
                <span v-if="freeship" style="color:var(--success)">FREE</span>
                <template v-else>$4.99</template>
              </span>
            </div>
            <div class="srow"><span>Est. tax</span><span class="val" style="color:var(--gray)">at checkout</span></div>
          </div>
          <div style="display:flex;justify-content:space-between;font-weight:800;font-size:17px;margin:16px 0;padding-top:14px;border-top:1px solid var(--gray-light)">
            <span>Total</span><span style="color:var(--plum);font-variant-numeric:tabular-nums">
              ${{ (total + (freeship ? 0 : 4.99)).toFixed(2) }}
            </span>
          </div>
          <router-link to="/checkout" class="btn btn-primary btn-block btn-lg">Checkout · ${{ (total + (freeship ? 0 : 4.99)).toFixed(2) }}</router-link>
          <router-link to="/store" style="display:block;text-align:center;margin-top:12px;font-size:13px;color:var(--gray);text-decoration:underline">
            Continue shopping
          </router-link>
        </div>
      </div>
    </div>
  </section>
</template>
