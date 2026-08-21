<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../api/client'
import { i18n } from '../i18n'
import ProductCard from '../components/ProductCard.vue'

const route = useRoute()
const router = useRouter()
const zh = () => i18n.lang === 'zh'

const q = ref(String(route.query.q || ''))
const items = ref([])
const total = ref(0)
const page = ref(1)
const loaded = ref(false)
const pages = ref(1)
const cats = ref([])
const recent = ref([])

/* 排序白名单（对齐 StoreView）：缺省 best，非法值回落 best */
const SORTS = [
  ['new', 'store.sort.new'], ['best', 'store.sort.best'],
  ['price_asc', 'store.sort.priceAsc'], ['price_desc', 'store.sort.priceDesc'],
]
const SORT_KEYS = ['new', 'best', 'price_asc', 'price_desc']
const curSort = () => {
  const s = route.query.sort
  if (!s) return 'best'
  return SORT_KEYS.includes(s) ? s : 'best'
}
/* 每页条数白名单：12（缺省）/24/48 */
const SIZES = [12, 24, 48]
const curSize = () => {
  const n = parseInt(route.query.size, 10)
  return SIZES.includes(n) ? n : 12
}

const RECENT_KEY = 'gm_recent_searches'
function loadRecent() {
  try { recent.value = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]').filter((s) => typeof s === 'string') }
  catch (_) { recent.value = [] }
}
function saveRecent(term) {
  const v = (term || '').trim()
  if (!v) return
  loadRecent()
  recent.value = [v, ...recent.value.filter((s) => s.toLowerCase() !== v.toLowerCase())].slice(0, 8)
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(recent.value)) } catch (_) { /* 隐私模式 */ }
}
function clearRecent() {
  recent.value = []
  try { localStorage.removeItem(RECENT_KEY) } catch (_) { /* 同上 */ }
}

let sSeq = 0
async function search() {
  const seq = ++sSeq
  loaded.value = false
  const term = q.value.trim()
  if (!term) {
    items.value = []; total.value = 0; cats.value = []; pages.value = 1
    loaded.value = true
    return
  }
  const sz = curSize()
  const params = new URLSearchParams({ q: term, page: page.value, size: sz, sort: curSort() })
  try {
    const [d, s] = await Promise.all([
      req('GET', '/api/catalog/products?' + params.toString()),
      req('GET', '/api/catalog/search?q=' + encodeURIComponent(term)).catch(() => null),
    ])
    if (seq !== sSeq) return
    items.value = d.items || []
    total.value = d.total ?? items.value.length
    pages.value = Math.max(1, Math.ceil(total.value / sz))
    cats.value = (s && s.categories) || []
  } catch (_) {
    if (seq !== sSeq) return
    items.value = []; total.value = 0; pages.value = 1
  }
  loaded.value = true
}

/* sort/size 走 URL query（replace 同步，不产生历史）；切换即回第 1 页 */
function setSort(v) {
  if (curSort() === v) return
  page.value = 1
  router.replace({ query: { ...route.query, sort: v === 'best' ? undefined : v, page: undefined } })
}
function setSize(n) {
  if (curSize() === n) return
  page.value = 1
  router.replace({ query: { ...route.query, size: n === 12 ? undefined : String(n), page: undefined } })
}

function submit() {
  saveRecent(q.value)
  page.value = 1
  router.push({ path: '/search', query: q.value.trim() ? { ...route.query, q: q.value.trim(), page: undefined } : {} })
  manualAt = Date.now()
  search()
}
function pickTerm(term) {
  q.value = term
  page.value = 1
  router.push({ path: '/search', query: { ...route.query, q: term, page: undefined } })
  manualAt = Date.now()
  search()
}

let timer = null
let manualAt = 0
watch(q, (v) => {
  clearTimeout(timer)
  if (!v.trim()) { items.value = []; total.value = 0; return }
  timer = setTimeout(() => {
    if (Date.now() - manualAt < 450) return
    page.value = 1
    search()
  }, 300)
})

onMounted(() => { loadRecent(); search() })
watch(() => route.query.q, (v) => {
  const term = String(v || '')
  if (term !== q.value) {
    q.value = term
    page.value = 1
    manualAt = Date.now()
    search()
  }
})

/* page/sort/size 全部双向同步 URL（replace 不产生历史）：query 变化回读驱动 search
   （浏览器前进/后退亦覆盖；q 的变化由上方独立 watcher 处理） */
watch(() => [route.query.page, route.query.sort, route.query.size].join('|'), () => {
  const p = parseInt(route.query.page, 10) || 1
  const changed = p !== page.value
  if (changed) page.value = p
  if (changed || q.value.trim()) search()
})
function goPage(p) {
  if (p < 1 || p > pages.value || p === page.value) return
  page.value = p
  router.replace({ query: { ...route.query, page: p > 1 ? String(p) : undefined } })
  /* search 由 page/sort/size watcher 统一驱动（避免双请求） */
}
const pageWindow = () => {
  const w = []
  const from = Math.max(1, page.value - 2), to = Math.min(pages.value, page.value + 2)
  for (let i = from; i <= to; i++) w.push(i)
  return w
}

const HOT = ['french', 'glitter', 'cat-eye', 'short almond', 'red', 'pastel']
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head search-head">
        <h2 class="section-title">{{ zh() ? '搜索' : 'Search' }}</h2>
        <div class="search-ctrl">
          <div class="seg" :aria-label="zh() ? '排序' : 'Sort by'">
            <button
              v-for="[v, label] in SORTS" :key="v" type="button"
              class="seg-btn" :class="{ on: curSort() === v }"
              @click="setSort(v)"
            >{{ i18n.t(label) }}</button>
          </div>
          <select
            class="input search-size" :aria-label="zh() ? '每页' : 'Per page'"
            :value="curSize()" @change="setSize(parseInt($event.target.value, 10))"
          >
            <option v-for="n in SIZES" :key="n" :value="n">{{ n }} / {{ zh() ? '页' : 'page' }}</option>
          </select>
        </div>
      </div>
      <form @submit.prevent="submit" style="display:flex;gap:10px;margin-bottom:14px">
        <input v-model="q" class="input" :placeholder="zh() ? '试试「french」「glitter」「short almond」…' : `Try 'french', 'glitter', 'short almond'...`" autocomplete="off">
        <button class="btn btn-primary" style="flex:none">{{ zh() ? '搜索' : 'Search' }}</button>
      </form>

      <div v-if="recent.length" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px">
        <span style="font-size:12px;color:var(--gray);font-weight:700">{{ zh() ? '最近搜索' : 'Recent' }}</span>
        <button v-for="r in recent" :key="r" class="trend-chip" style="margin:0" @click="pickTerm(r)">{{ r }}</button>
        <button style="font-size:12px;color:var(--gray);text-decoration:underline" @click="clearRecent">{{ zh() ? '清除' : 'Clear' }}</button>
      </div>
      <div v-else style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px">
        <span style="font-size:12px;color:var(--gray);font-weight:700">{{ zh() ? '热门' : 'Trending' }}</span>
        <button v-for="h in HOT" :key="h" class="trend-chip" style="margin:0" @click="pickTerm(h)">{{ h }}</button>
      </div>

      <div v-if="cats.length" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
        <span style="font-size:12px;color:var(--gray);font-weight:700;align-self:center">{{ zh() ? '相关分类' : 'Categories' }}</span>
        <router-link v-for="c in cats" :key="c.slug" class="trend-chip" style="margin:0" :to="'/store?cat=' + c.slug">{{ c.name }} →</router-link>
      </div>

      <p v-if="q && loaded" class="search-count">
        <span class="cnt-pill">{{ total }} {{ zh() ? '条结果' : (total === 1 ? 'result' : 'results') }}</span>
        {{ zh() ? '匹配' : 'for' }} "<mark class="cnt-mark">{{ q }}</mark>"
      </p>

      <div class="grid grid-4">
        <template v-if="!loaded">
          <div v-for="i in 8" :key="'sk' + i" class="sk-card">
            <div class="sk-img sk-shimmer"></div>
            <div class="sk-line sk-shimmer" style="width:70%;height:14px;margin-top:10px"></div>
            <div class="sk-line sk-shimmer" style="width:40%;height:14px;margin-top:8px"></div>
          </div>
        </template>
        <ProductCard v-for="p in items" :key="p.id" :p="p" />
      </div>
      <div v-if="loaded && !q.trim()" style="text-align:center;padding:50px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">🔍</div>
        {{ zh() ? '输入关键词开始搜索，或点上方热门词逛逛' : 'Type a keyword to start searching, or try the trending picks above' }} ·
        <router-link to="/store" style="color:var(--plum)">{{ zh() ? '浏览全部' : 'browse all' }}</router-link>
      </div>
      <div v-else-if="loaded && !items.length" style="text-align:center;padding:50px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">🔍</div>
        {{ zh() ? '没有匹配商品 — 换个关键词试试' : 'No matches — try a different keyword' }} ·
        <router-link to="/store" style="color:var(--plum)">{{ zh() ? '浏览全部' : 'browse all' }}</router-link>
        <div class="nores-chips">
          <span style="font-size:12px;color:var(--gray);font-weight:700">{{ zh() ? '试试热词' : 'Trending' }}</span>
          <button v-for="h in HOT" :key="h" class="trend-chip" style="margin:0" @click="pickTerm(h)">🔥 {{ h }}</button>
        </div>
      </div>

      <div v-if="pages > 1" style="display:flex;justify-content:center;gap:8px;margin-top:32px">
        <button class="btn btn-secondary btn-sm" :disabled="page <= 1" @click="goPage(page - 1)">←</button>
        <button v-if="pageWindow()[0] > 1" class="btn btn-secondary btn-sm" disabled>…</button>
        <button
          v-for="p in pageWindow()" :key="p" class="btn btn-sm"
          :class="p === page ? 'btn-primary' : 'btn-secondary'" @click="goPage(p)"
        >{{ p }}</button>
        <button v-if="pageWindow()[pageWindow().length - 1] < pages" class="btn btn-secondary btn-sm" disabled>…</button>
        <button class="btn btn-secondary btn-sm" :disabled="page >= pages" @click="goPage(page + 1)">→</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sk-card { border-radius: 12px; }
.sk-img { aspect-ratio: 1; border-radius: 12px; }
.sk-line { border-radius: 8px; }
/* 排序分段控件（复用 StoreView 样式）+ 每页 select */
.search-ctrl { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.search-size { height: 38px; padding: 0 10px; font-size: 12.5px; font-weight: 600; color: var(--plum); flex: none; }
.seg { display: inline-flex; flex-wrap: wrap; gap: 2px; padding: 3px; border: 1.5px solid var(--gray-light); border-radius: 999px; background: #fff; }
.seg-btn { padding: 6px 14px; border-radius: 999px; font-size: 12.5px; font-weight: 600; color: var(--gray); transition: all .15s; }
.seg-btn:hover { color: var(--plum); background: var(--rose-pale); }
.seg-btn.on { background: var(--plum); color: #fff; }
/* 计数 pill 化（rose-pale 底 plum 字）+ 关键词品牌色高亮 */
.search-count { font-size: 13.5px; color: var(--gray); margin-bottom: 18px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cnt-pill { display: inline-flex; align-items: center; background: var(--rose-pale); color: var(--plum); font-size: 12.5px; font-weight: 700; padding: 3px 12px; border-radius: 999px; }
.cnt-mark { background: var(--rose-pale); color: var(--plum); font-weight: 700; padding: 0 4px; border-radius: 4px; }
/* 无结果态热词 chips */
.nores-chips { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; align-items: center; margin-top: 18px; }
@media (max-width: 768px) {
  .search-head { flex-direction: column; align-items: stretch; gap: 10px; }
  .search-ctrl { justify-content: space-between; }
}
</style>
