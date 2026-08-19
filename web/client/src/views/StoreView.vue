<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import { i18n } from '../i18n'
import ProductCard from '../components/ProductCard.vue'

const route = useRoute()
const state = reactive({ items: [], total: 0, page: 1, size: 12 })
const loaded = ref(false)
const zh = () => i18n.lang === 'zh'

const CATS = { nails: 'Press-on Nails', lashes: 'Magnetic Lashes' }
const SORTS = [
  ['new', 'Newest'], ['best', 'Best selling'], ['price_asc', 'Price ↑'], ['price_desc', 'Price ↓'],
]

async function load() {
  loaded.value = false
  const params = {
    page: state.page, size: state.size, sort: route.query.sort || 'new',
  }
  if (route.query.cat) params.category = route.query.cat
  if (route.query.q) params.q = route.query.q
  const q = new URLSearchParams(params).toString()
  try {
    const d = await req('GET', '/api/catalog/products?' + q)
    state.items = d.items || []
    state.total = d.total ?? state.items.length
  } catch (_) { state.items = [] }
  loaded.value = true
}

watch(() => route.query, () => { state.page = 1; load() })
onMounted(load)

const pages = ref(1)
watch(() => state.total, (t) => { pages.value = Math.max(1, Math.ceil(t / state.size)) })
function goPage(p) {
  if (p < 1 || p > pages.value) return
  state.page = p
  load()
}
const heading = () => {
  if (route.query.q) return `"${route.query.q}"`
  if (route.query.sale) return zh() ? '促销专区' : 'Sale'
  return CATS[route.query.cat] || (zh() ? '全部商品' : 'All Products')
}
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head">
        <h2 class="section-title">{{ heading() }}</h2>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <router-link
            v-for="[v, label] in SORTS" :key="v"
            class="trend-chip" :class="{ on: (route.query.sort || 'new') === v }"
            :to="{ path: '/store', query: { ...route.query, sort: v } }"
          >{{ label }}</router-link>
        </div>
      </div>

      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:22px">
        <router-link class="trend-chip" :class="{ on: !route.query.cat }" :to="{ path: '/store', query: { ...route.query, cat: undefined } }">
          {{ zh() ? '全部' : 'All' }}
        </router-link>
        <router-link
          v-for="(label, key) in CATS" :key="key" class="trend-chip"
          :class="{ on: route.query.cat === key }"
          :to="{ path: '/store', query: { ...route.query, cat: key } }"
        >{{ label }}</router-link>
      </div>

      <div class="grid grid-4">
        <ProductCard v-for="p in state.items" :key="p.id" :p="p" />
      </div>
      <div v-if="loaded && !state.items.length" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">🔍</div>
        {{ zh() ? '没有找到商品' : 'No products found' }}
      </div>

      <div v-if="pages > 1" style="display:flex;justify-content:center;gap:8px;margin-top:32px">
        <button class="btn btn-secondary btn-sm" :disabled="state.page <= 1" @click="goPage(state.page - 1)">←</button>
        <button
          v-for="p in pages" :key="p" class="btn btn-sm"
          :class="p === state.page ? 'btn-primary' : 'btn-secondary'" @click="goPage(p)"
        >{{ p }}</button>
        <button class="btn btn-secondary btn-sm" :disabled="state.page >= pages" @click="goPage(state.page + 1)">→</button>
      </div>
    </div>
  </section>
</template>
