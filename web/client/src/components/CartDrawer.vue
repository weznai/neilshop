<script setup>
import { computed, ref, watch } from 'vue'
import { i18n } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { req } from '../api/client'
import { catalogById } from '../data/catalog'

const cart = useCartStore()
const ui = useUiStore()

const FREE_SHIP = 35
const GWP_AT = 45

const zh = computed(() => i18n.lang === 'zh')
const recs = ref([])
let recSeq = 0

watch(
  () => cart.items.map((i) => i.pid || i.id).join(','),
  async (ids) => {
    const seq = ++recSeq
    try {
      const path = ids
        ? '/api/ai/recommend?cart_ids=' + encodeURIComponent(ids) + '&size=4'
        : '/api/ai/hot?size=4'
      const d = await req('GET', path)
      if (seq !== recSeq) return
      const inCart = new Set(cart.items.map((i) => i.pid || i.id))
      const seen = new Set()
      recs.value = (d.items || [])
        .filter((p) => p && p.id != null && !inCart.has(p.id) && !seen.has(p.id) && seen.add(p.id))
        .slice(0, 4)
    } catch (_) { recs.value = [] }
  },
  { immediate: true },
)

const shipHtml = computed(() =>
  cart.subtotal >= FREE_SHIP
    ? i18n.t('ship.unlocked')
    : i18n.t('ship.away', (FREE_SHIP - cart.subtotal).toFixed(2)))
const gwpHtml = computed(() =>
  cart.subtotal >= GWP_AT
    ? i18n.t('gwp.unlocked')
    : i18n.t('gwp.away', (GWP_AT - cart.subtotal).toFixed(2)))
const shipPct = computed(() => Math.min(100, (cart.subtotal / FREE_SHIP) * 100))
const gwpPct = computed(() => Math.min(100, (cart.subtotal / GWP_AT) * 100))

function recTitle(p) {
  if (zh.value) {
    const hit = catalogById(p.id)
    if (hit && hit.titleZh) return hit.titleZh
  }
  return p.title
}
</script>

<template>
  <div class="overlay" :class="{ open: ui.cartDrawer }" @click="ui.closeCart()"></div>
  <aside class="drawer" :class="{ open: ui.cartDrawer }" :aria-label="i18n.t('aria.cartDrawer')">
    <div class="drawer-head">
      {{ i18n.t('cart.title') }}
      <button style="font-size:22px" @click="ui.closeCart()">×</button>
    </div>
    <div class="drawer-body">
      <div v-if="!cart.items.length" style="text-align:center;padding:48px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:12px">🛒</div>
        <p style="margin-bottom:16px">{{ i18n.t('cart.empty') }}</p>
        <router-link class="btn btn-primary btn-sm" to="/" @click="ui.closeCart()">{{ i18n.t('cart.shop') }}</router-link>
      </div>
      <div
        v-for="i in cart.items" :key="i.id"
        style="display:flex;gap:12px;padding:12px 0;border-bottom:1px solid var(--gray-light)"
      >
        <img :src="i.img" style="width:72px;height:72px;border-radius:8px;object-fit:cover" :alt="i.title">
        <div style="flex:1">
          <div style="font-weight:600;font-size:14px">{{ i.title }}</div>
          <div style="font-size:12px;color:var(--gray)">{{ i.variant }}</div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
            <div style="display:flex;align-items:center;gap:0;border:1px solid var(--gray-light);border-radius:8px">
              <button class="qbtn" @click="cart.setQty(i.vid, i.qty - 1, ui)">−</button>
              <span style="width:32px;text-align:center;font-size:13px;font-weight:600">{{ i.qty }}</span>
              <button class="qbtn" @click="cart.setQty(i.vid, i.qty + 1, ui)">＋</button>
            </div>
            <div style="font-weight:700;color:var(--plum)">${{ (i.price * i.qty).toFixed(2) }}</div>
          </div>
        </div>
        <button style="color:var(--gray);font-size:18px;align-self:flex-start" @click="cart.remove(i.vid, ui)">×</button>
      </div>
    </div>
    <div v-if="cart.items.length" class="drawer-foot">
      <div v-if="recs.length" class="rec-wrap">
        <div class="rec-head">{{ i18n.t('cart.pairs') }}</div>
        <div class="rec-row">
          <div v-for="p in recs" :key="p.id" class="rec-card">
            <img :src="p.hero_image" :alt="p.title">
            <div class="rec-info">
              <div class="rec-title">{{ recTitle(p) }}</div>
              <div class="rec-price">${{ (p.price_min / 100).toFixed(2) }}</div>
            </div>
            <button class="rec-add" :aria-label="i18n.t('cart.add')" @click="cart.addByProductId(p.id, 1, ui)">⊕</button>
          </div>
        </div>
      </div>
      <div class="ship-bar" :class="{ 'gwp-bar': cart.subtotal >= FREE_SHIP }" v-html="shipHtml"></div>
      <div class="ship-track" style="margin-bottom:10px"><div class="ship-fill" :style="{ width: shipPct + '%' }"></div></div>
      <div class="ship-bar gwp-bar" :class="{ 'gwp-unlocked': cart.subtotal >= GWP_AT }" v-html="gwpHtml"></div>
      <div class="ship-track" style="margin-bottom:12px"><div class="ship-fill" :style="{ width: gwpPct + '%' }"></div></div>
      <div style="display:flex;justify-content:space-between;margin-bottom:12px;font-size:15px">
        <span>{{ i18n.t('cart.subtotal') }}</span>
        <b style="font-variant-numeric:tabular-nums">${{ cart.subtotal.toFixed(2) }}</b>
      </div>
      <router-link to="/checkout" class="btn btn-primary btn-block" @click="ui.closeCart()">
        {{ i18n.t('cart.checkout') }} · ${{ cart.subtotal.toFixed(2) }}
      </router-link>
      <div style="text-align:center;margin-top:10px">
        <router-link to="/cart" style="font-size:13px;color:var(--gray);text-decoration:underline" @click="ui.closeCart()">
          {{ i18n.t('cart.view') }}
        </router-link>
      </div>
    </div>
  </aside>
</template>
