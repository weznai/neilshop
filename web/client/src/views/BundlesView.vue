<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'

const cart = useCartStore()
const ui = useUiStore()
const items = ref([])
onMounted(async () => {
  try { items.value = (await req('GET', '/api/catalog/products?size=6&sort=best')).items || [] } catch (_) { /* */ }
})
const BUNDLES = [
  { name: 'Date Night Duo', items: [1, 4], save: 15, img: 'https://placehold.co/300x200/F5D8DA/6D2E46?text=Date+Night' },
  { name: 'Everyday Trio', items: [3, 9, 7], save: 20, img: 'https://placehold.co/300x200/DDD6E8/552338?text=Everyday' },
  { name: 'Full Glam Set', items: [6, 10, 8], save: 20, img: 'https://placehold.co/300x200/FBEBD4/8A6D3B?text=Full+Glam' },
]
async function addBundle(ids) {
  for (const id of ids) {
    try {
      const d = await req('GET', '/api/catalog/products-by-id/' + id)
      const v = d.variants && d.variants[0]
      if (v) await req('POST', '/api/cart/items', { variant_id: v.id, qty: 1 })
    } catch (_) { /* */ }
  }
  await cart.refresh()
  ui.toast('Bundle added — discount auto-applied 🎁', 'success')
  ui.openCart()
}
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:30px">
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">Bundles & Save</h1>
        <p style="color:var(--gray)">2 sets = 15% off · 3+ sets = 20% off — applied automatically in cart.</p>
      </div>
      <div class="grid grid-3">
        <div v-for="b in BUNDLES" :key="b.name" class="card" style="padding:0;overflow:hidden">
          <img :src="b.img" :alt="b.name" style="width:100%;height:200px;object-fit:cover">
          <div style="padding:18px">
            <b style="font-family:var(--font-title);font-size:18px">{{ b.name }}</b>
            <div style="font-size:13px;color:var(--gray);margin:6px 0 12px">{{ b.items.length }} sets · hand-picked combos</div>
            <button class="btn btn-primary btn-block" @click="addBundle(b.items)">Add bundle · save {{ b.save }}%</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
