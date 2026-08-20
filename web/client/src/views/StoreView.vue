<script setup>
import { nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { i18n } from '../i18n'
import ProductCard from '../components/ProductCard.vue'

const route = useRoute()
const router = useRouter()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
const state = reactive({ items: [], total: 0, page: parseInt(route.query.page, 10) || 1, size: 12 })
const loaded = ref(false)
const loadError = ref(false)
const pendingScroll = ref(false)
const gridEl = ref(null)

/* 导航/旧链接使用短别名（nails/lashes），后端真实 slug 为 press-on-nails / magnetic-lashes */
const CAT_ALIAS = { nails: 'press-on-nails', lashes: 'magnetic-lashes' }
const FALLBACK_CATS = [
  { slug: 'press-on-nails', name: 'Press-on Nails' },
  { slug: 'magnetic-lashes', name: 'Magnetic Lashes' },
]
const cats = ref(FALLBACK_CATS)
onMounted(async () => {
  try {
    const tree = await req('GET', '/api/catalog/categories')
    const flat = []
    const walk = (nodes) => nodes.forEach((n) => { flat.push(n); walk(n.children || []) })
    walk(tree || [])
    if (flat.length) cats.value = flat
  } catch (_) { /* 保留兜底 */ }
})

const SORTS = [
  ['new', 'store.sort.new'], ['best', 'store.sort.best'],
  ['price_asc', 'store.sort.priceAsc'], ['price_desc', 'store.sort.priceDesc'],
]
const SORT_KEYS = ['new', 'best', 'price_asc', 'price_desc']
/* sort 白名单：缺省 new，非法值回落 best */
const curSort = () => {
  const s = route.query.sort
  if (!s) return 'new'
  return SORT_KEYS.includes(s) ? s : 'best'
}

const activeCat = () => {
  const c = route.query.cat
  if (!c) return null
  return cats.value.find((x) => x.slug === c) || cats.value.find((x) => x.slug === CAT_ALIAS[c]) || null
}
const activeTag = () => route.query.tag || route.query.style || ''

let ldSeq = 0
async function load() {
  loaded.value = false
  loadError.value = false
  const seq = ++ldSeq
  const params = {
    page: state.page, size: state.size, sort: curSort(),
  }
  const cat = activeCat()
  if (cat) params.category = cat.slug
  const tag = activeTag()
  if (tag) params.tag = tag
  if (route.query.q) params.q = route.query.q
  /* 价格区间（后端 min_price/max_price 美分，交集语义） */
  if (route.query.min) params.min_price = Math.round(parseFloat(route.query.min) * 100)
  if (route.query.max) params.max_price = Math.round(parseFloat(route.query.max) * 100)
  if (route.query.sale) params.on_sale = 1
  const qs = new URLSearchParams(params).toString()
  try {
    const d = await req('GET', '/api/catalog/products?' + qs)
    if (seq !== ldSeq) return
    state.items = d.items || []
    state.total = d.total ?? state.items.length
  } catch (_) {
    if (seq !== ldSeq) return
    state.items = []; state.total = 0; loadError.value = true
  }
  loaded.value = true
  if (pendingScroll.value) {
    pendingScroll.value = false
    nextTick(() => gridEl.value && gridEl.value.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }
}

/* page 同步 route.query.page：筛选变化回第 1 页（replace 清掉 URL 中的 page），翻页 replace 不产生历史 */
watch(() => route.query, (nq, oq) => {
  const sig = (qq) => JSON.stringify({ ...(qq || {}), page: 0 })
  if (sig(nq) !== sig(oq)) {
    if (nq.page) { router.replace({ query: { ...nq, page: undefined } }); return }
    state.page = 1
  } else {
    state.page = parseInt(nq.page, 10) || 1
  }
  load()
})
onMounted(load)

const pages = ref(1)
watch(() => state.total, (t) => { pages.value = Math.max(1, Math.ceil(t / state.size)) })
function goPage(p) {
  if (p < 1 || p > pages.value || p === state.page) return
  pendingScroll.value = true
  router.replace({ query: { ...route.query, page: p > 1 ? String(p) : undefined } })
}
const pageWindow = () => {
  const w = []
  const from = Math.max(1, state.page - 2), to = Math.min(pages.value, state.page + 2)
  for (let i = from; i <= to; i++) w.push(i)
  return w
}

const heading = () => {
  if (route.query.q) return `"${route.query.q}"`
  if (route.query.sale) return i18n.t('footer.sale')
  const cat = activeCat()
  if (cat) return cat.name
  if (route.query.tag) return `#${route.query.tag}`
  return i18n.t('footer.all')
}
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head store-head">
        <h2 class="section-title">{{ heading() }}</h2>
        <div class="store-chiprow" style="gap:6px">
          <router-link
            v-for="[v, label] in SORTS" :key="v"
            class="trend-chip" :class="{ on: curSort() === v }"
            :to="{ path: '/store', query: { ...route.query, sort: v } }"
          >{{ i18n.t(label) }}</router-link>
        </div>
      </div>

      <div class="store-chiprow" style="margin-bottom:8px">
        <router-link class="trend-chip" :class="{ on: !route.query.cat }" :to="{ path: '/store', query: { ...route.query, cat: undefined } }">
          {{ i18n.t('store.cat.all') }}
        </router-link>
        <router-link
          v-for="c in cats" :key="c.slug" class="trend-chip"
          :class="{ on: (route.query.cat === c.slug) || (route.query.cat && CAT_ALIAS[route.query.cat] === c.slug) }"
          :to="{ path: '/store', query: { ...route.query, cat: c.slug } }"
        >{{ c.name }}</router-link>
      </div>
      <div class="store-chiprow" style="margin-bottom:22px">
        <router-link class="trend-chip" :class="{ on: route.query.style === 'french' }" :to="{ path: '/store', query: { ...route.query, cat: route.query.cat || 'nails', style: 'french', tag: undefined } }">
          {{ i18n.t('store.style.french') }}
        </router-link>
        <router-link class="trend-chip" :class="{ on: route.query.style === 'glitter' }" :to="{ path: '/store', query: { ...route.query, cat: route.query.cat || 'nails', style: 'glitter', tag: undefined } }">
          {{ i18n.t('store.style.glitter') }}
        </router-link>
        <router-link class="trend-chip" :class="{ on: !!route.query.sale }" :to="route.query.sale ? { path: '/store', query: { ...route.query, sale: undefined } } : { path: '/store', query: { ...route.query, sale: 1 } }">
          🔥 {{ i18n.t('store.chip.sale') }}
        </router-link>
        <span v-if="route.query.shape" class="trend-chip on" style="cursor:default">
          {{ i18n.t('store.chip.shape', route.query.shape) }}
        </span>
      </div>
      <!-- 价格区间（后端 min_price/max_price 交集筛选） -->
      <div class="store-chiprow" style="margin-bottom:22px">
        <router-link class="trend-chip" :class="{ on: !route.query.min && !route.query.max }" :to="{ path: '/store', query: { ...route.query, min: undefined, max: undefined } }">
          {{ i18n.t('store.price.any') }}
        </router-link>
        <router-link class="trend-chip" :class="{ on: route.query.max === '15' }" :to="{ path: '/store', query: { ...route.query, min: undefined, max: 15 } }">
          {{ i18n.t('store.price.under') }}
        </router-link>
        <router-link class="trend-chip" :class="{ on: route.query.min === '15' && route.query.max === '18' }" :to="{ path: '/store', query: { ...route.query, min: 15, max: 18 } }">
          $15 – $18
        </router-link>
        <router-link class="trend-chip" :class="{ on: route.query.min === '18' }" :to="{ path: '/store', query: { ...route.query, min: 18, max: undefined } }">
          $18+
        </router-link>
      </div>

      <p v-if="loaded" style="font-size:13px;color:var(--gray);margin-bottom:16px">
        {{ i18n.t(state.total === 1 ? 'store.count.one' : 'store.count.many', state.total) }}
      </p>

      <div ref="gridEl" class="grid grid-4">
        <template v-if="!loaded">
          <div v-for="i in 8" :key="'sk' + i" class="sk-card">
            <div class="sk-img"></div>
            <div class="sk-line" style="width:70%;height:14px;margin-top:10px"></div>
            <div class="sk-line" style="width:40%;height:14px;margin-top:8px"></div>
          </div>
        </template>
        <ProductCard v-for="p in state.items" :key="p.id" :p="p" />
      </div>
      <div v-if="loaded && loadError" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">⚠️</div>
        {{ tt('Failed to load products', '商品加载失败，请重试') }}
        <div style="margin-top:14px">
          <button class="btn btn-secondary btn-sm" @click="load">↻ {{ tt('Retry', '重试') }}</button>
        </div>
      </div>
      <div v-else-if="loaded && !state.items.length" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">🔍</div>
        {{ i18n.t('store.empty') }} —
        <router-link to="/store" style="color:var(--plum)">{{ i18n.t('store.clear') }}</router-link>
      </div>

      <div v-if="pages > 1" style="display:flex;justify-content:center;gap:8px;margin-top:32px">
        <button class="btn btn-secondary btn-sm" :disabled="state.page <= 1" @click="goPage(state.page - 1)">←</button>
        <button v-if="pageWindow()[0] > 1" class="btn btn-secondary btn-sm" disabled>…</button>
        <button
          v-for="p in pageWindow()" :key="p" class="btn btn-sm"
          :class="p === state.page ? 'btn-primary' : 'btn-secondary'" @click="goPage(p)"
        >{{ p }}</button>
        <button v-if="pageWindow()[pageWindow().length - 1] < pages" class="btn btn-secondary btn-sm" disabled>…</button>
        <button class="btn btn-secondary btn-sm" :disabled="state.page >= pages" @click="goPage(state.page + 1)">→</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sk-card { border-radius: 12px; }
.sk-img { aspect-ratio: 1; border-radius: 12px; }
.sk-img, .sk-line { background: linear-gradient(100deg, var(--gray-light) 40%, #f7f3f5 50%, var(--gray-light) 60%); background-size: 200% 100%; animation: skShimmer 1.2s infinite; }
@keyframes skShimmer { to { background-position: -200% 0; } }
.trend-chip.on { background: var(--plum); border-color: var(--plum); color: #fff; }
</style>
