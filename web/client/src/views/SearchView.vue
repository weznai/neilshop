<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import ProductCard from '../components/ProductCard.vue'

const route = useRoute()
const q = ref(String(route.query.q || ''))
const items = ref([])
const loaded = ref(false)

async function search() {
  loaded.value = false
  try {
    const d = await req('GET', '/api/catalog/search?q=' + encodeURIComponent(q.value))
    items.value = d.products || []
  } catch (_) { items.value = [] }
  loaded.value = true
}
onMounted(search)
watch(() => route.query.q, (v) => { q.value = String(v || ''); search() })
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head"><h2 class="section-title">Search</h2></div>
      <form @submit.prevent="$router.push({ path: '/search', query: q ? { q } : {} })" style="display:flex;gap:10px;margin-bottom:24px">
        <input v-model="q" class="input" placeholder="Try 'french', 'glitter', 'short almond'...">
        <button class="btn btn-primary">Search</button>
      </form>
      <p v-if="q" style="font-size:13.5px;color:var(--gray);margin-bottom:18px">
        {{ items.length }} result{{ items.length === 1 ? '' : 's' }} for "<b>{{ q }}</b>"
      </p>
      <div class="grid grid-4">
        <ProductCard v-for="p in items" :key="p.id" :p="p" />
      </div>
      <div v-if="loaded && !items.length" style="text-align:center;padding:50px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">🔍</div>
        No matches — try a different keyword or <router-link to="/store" style="color:var(--plum)">browse all</router-link>
      </div>
    </div>
  </section>
</template>
