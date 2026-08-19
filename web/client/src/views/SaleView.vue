<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'
import ProductCard from '../components/ProductCard.vue'

const items = ref([])
const loaded = ref(false)
onMounted(async () => {
  try { items.value = (await req('GET', '/api/catalog/products?tag=sale&size=12')).items || [] } catch (_) { /* */ }
  loaded.value = true
})
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:26px">
        <div style="font-size:46px">🔥</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:6px">End of Season Sale</h1>
        <p style="color:var(--gray)">Up to 25% off — no code needed. While stocks last.</p>
      </div>
      <div class="grid grid-4">
        <ProductCard v-for="p in items" :key="p.id" :p="p" />
      </div>
      <div v-if="loaded && !items.length" style="text-align:center;color:var(--gray);padding:40px 0">
        Sale restocking — check back soon 💅
      </div>
    </div>
  </section>
</template>
