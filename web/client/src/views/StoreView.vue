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
/* 深链补载判据：首屏 ?cat= 若不在兜底分类表中，首次 load() 实际未按分类过滤；
   cats 树加载完成后若该参数仍未被消费过，则补一次 load */
let catConsumed = !route.query.cat
onMounted(async () => {
  try {
    const tree = await req('GET', '/api/catalog/categories')
    const flat = []
    const walk = (nodes) => nodes.forEach((n) => { flat.push(n); walk(n.children || []) })
    walk(tree || [])
    if (flat.length) cats.value = flat
  } catch (_) { /* 保留兜底 */ }
})
watch(cats, () => {
  if (catConsumed || !route.query.cat || !activeCat()) return
  catConsumed = true
  load()
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

/* 甲型筛选 chips（后端 GET /products?shape= 精确匹配变体 option1_value） */
const SHAPE_CHIPS = [
  ['almond', 'Almond', '短杏仁'],
  ['square', 'Square', '中方头'],
  ['stiletto', 'Stiletto', '尖头'],
  ['coffin', 'Coffin', '棺材头'],
]
const shapeLabel = (v) => {
  const hit = SHAPE_CHIPS.find((x) => x[0] === v)
  return hit ? tt(hit[1], hit[2]) : String(v)
}

let ldSeq = 0
const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
async function load() {
  loaded.value = false
  loadError.value = false
  const seq = ++ldSeq
  const params = {
    page: state.page, size: state.size, sort: curSort(),
  }
  const cat = activeCat()
  if (cat) params.category = cat.slug
  if (cat && route.query.cat) catConsumed = true
  const tag = activeTag()
  if (tag) params.tag = tag
  if (route.query.q) params.q = route.query.q
  /* 甲型筛选（后端 shape 参数，支持 almond/square/stiletto/coffin） */
  if (route.query.shape) params.shape = String(route.query.shape)
  /* 价格区间（后端 min_price/max_price 美分，交集语义；NaN 不发送） */
  const minV = parseFloat(route.query.min)
  if (Number.isFinite(minV)) params.min_price = Math.round(minV * 100)
  const maxV = parseFloat(route.query.max)
  if (Number.isFinite(maxV)) params.max_price = Math.round(maxV * 100)
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
    nextTick(() => gridEl.value && gridEl.value.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' }))
  }
}

/* page 同步 route.query.page：筛选变化回第 1 页（replace 清掉 URL 中的 page），翻页 replace 不产生历史 */
watch(() => route.query, (nq, oq) => {
  const sig = (qq) => JSON.stringify({ ...(qq || {}), page: 0 })
  if (sig(nq) !== sig(oq)) {
    /* 筛选变化不滚动（保持当前位置）；仅翻页滚回网格顶 */
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
  let base = cat ? cat.name : (route.query.tag ? `#${route.query.tag}` : i18n.t('footer.all'))
  if (route.query.shape) base += ' · ' + shapeLabel(route.query.shape)
  return base
}

/* 空态回显：逐条列出当前生效筛选（pill 带 × 单独移除）+ 清除全部 */
const activeFilters = () => {
  const out = []
  if (route.query.q) out.push({ keys: ['q'], label: `"${route.query.q}"` })
  const cat = activeCat()
  if (cat) out.push({ keys: ['cat'], label: cat.name })
  const st = route.query.style || route.query.tag
  if (st) out.push({ keys: ['style', 'tag'], label: '#' + st })
  if (route.query.shape) out.push({ keys: ['shape'], label: shapeLabel(route.query.shape) })
  const lo = parseFloat(route.query.min), hi = parseFloat(route.query.max)
  if (Number.isFinite(lo) || Number.isFinite(hi)) {
    const label = Number.isFinite(lo) && Number.isFinite(hi)
      ? `$${lo} – $${hi}`
      : Number.isFinite(hi) ? `${tt('Under', '低于')} $${hi}` : `$${lo}+`
    out.push({ keys: ['min', 'max'], label })
  }
  if (route.query.sale) out.push({ keys: ['sale'], label: i18n.t('store.chip.sale') })
  return out
}
function dropFilter(f) {
  const query = { ...route.query }
  f.keys.forEach((k) => delete query[k])
  router.push({ path: '/store', query })
}
function clearAllFilters() { router.push({ path: '/store' }) }

/* 空态热词（品牌化回逛路径） */
const HOT_LINKS = [
  ['French', { cat: 'press-on-nails', style: 'french' }],
  ['Glitter', { cat: 'press-on-nails', style: 'glitter' }],
  ['Cat-Eye', { cat: 'magnetic-lashes', tag: 'cat-eye' }],
].map(([label, query]) => ({ label, to: { path: '/store', query } }))
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="section-head store-head">
        <h1 class="section-title">{{ heading() }}</h1>
        <div class="seg" :aria-label="tt('Sort by', '排序')">
          <router-link
            v-for="[v, label] in SORTS" :key="v"
            class="seg-btn" :class="{ on: curSort() === v }"
            :to="{ path: '/store', query: { ...route.query, sort: v } }"
          >{{ i18n.t(label) }}</router-link>
        </div>
      </div>

      <div class="store-filters">
        <div class="sf-row">
          <span class="sf-label">{{ tt('Category', '分类') }}</span>
          <div class="sf-chips">
            <router-link class="trend-chip" :class="{ on: !route.query.cat }" :to="{ path: '/store', query: { ...route.query, cat: undefined } }">
              {{ i18n.t('store.cat.all') }}
            </router-link>
            <router-link
              v-for="c in cats" :key="c.slug" class="trend-chip"
              :class="{ on: (route.query.cat === c.slug) || (route.query.cat && CAT_ALIAS[route.query.cat] === c.slug) }"
              :to="{ path: '/store', query: { ...route.query, cat: c.slug } }"
            >{{ c.name }}</router-link>
          </div>
        </div>
        <div class="sf-row">
          <span class="sf-label">{{ tt('Style', '风格') }}</span>
          <div class="sf-chips">
            <router-link class="trend-chip" :class="{ on: !route.query.style && !route.query.tag }" :to="{ path: '/store', query: { ...route.query, style: undefined, tag: undefined } }">
              {{ tt('All', '全部') }}
            </router-link>
            <router-link class="trend-chip" :class="{ on: route.query.style === 'french' }" :to="{ path: '/store', query: { ...route.query, cat: route.query.cat || 'nails', style: 'french', tag: undefined } }">
              {{ i18n.t('store.style.french') }}
            </router-link>
            <router-link class="trend-chip" :class="{ on: route.query.style === 'glitter' }" :to="{ path: '/store', query: { ...route.query, cat: route.query.cat || 'nails', style: 'glitter', tag: undefined } }">
              {{ i18n.t('store.style.glitter') }}
            </router-link>
            <router-link class="trend-chip" :class="{ on: !!route.query.sale }" :to="route.query.sale ? { path: '/store', query: { ...route.query, sale: undefined } } : { path: '/store', query: { ...route.query, sale: 1 } }">
              🔥 {{ i18n.t('store.chip.sale') }}
            </router-link>
          </div>
        </div>
        <div class="sf-row">
          <span class="sf-label">{{ tt('Shape', '甲型') }}</span>
          <div class="sf-chips">
            <router-link class="trend-chip" :class="{ on: !route.query.shape }" :to="{ path: '/store', query: { ...route.query, shape: undefined } }">
              {{ tt('All', '全部') }}
            </router-link>
            <router-link
              v-for="[v, en, cn] in SHAPE_CHIPS" :key="v" class="trend-chip"
              :class="{ on: route.query.shape === v }"
              :to="{ path: '/store', query: { ...route.query, shape: v } }"
            >{{ tt(en, cn) }}</router-link>
          </div>
        </div>
        <div class="sf-row sf-last">
          <span class="sf-label">{{ tt('Price', '价格') }}</span>
          <div class="sf-chips">
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
        </div>
      </div>

      <p v-if="loaded && !loadError" class="store-count">
        {{ i18n.t(state.total === 1 ? 'store.count.one' : 'store.count.many', state.total) }}
      </p>

      <div ref="gridEl" class="grid grid-4">
        <template v-if="!loaded">
          <div v-for="i in 8" :key="'sk' + i" class="sk-card">
            <div class="sk-img sk-shimmer"></div>
            <div class="sk-line sk-shimmer" style="width:70%;height:14px;margin-top:10px"></div>
            <div class="sk-line sk-shimmer" style="width:40%;height:14px;margin-top:8px"></div>
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
      <div v-else-if="loaded && !state.items.length" class="store-empty">
        <div class="se-icon" aria-hidden="true">▣</div>
        <p style="margin:12px 0 0;font-weight:600;color:var(--ink)">{{ i18n.t('store.empty') }}</p>
        <div v-if="activeFilters().length" class="se-filters" role="list" :aria-label="tt('Active filters', '生效筛选')">
          <span v-for="f in activeFilters()" :key="f.keys.join('-')" class="se-pill" role="listitem">
            {{ f.label }}
            <button type="button" class="se-x" :aria-label="tt('Remove filter', '移除筛选') + ': ' + f.label" @click="dropFilter(f)">×</button>
          </span>
          <button type="button" class="btn btn-secondary btn-sm se-clear" @click="clearAllFilters">
            {{ tt('Clear all filters', '清除全部筛选') }}
          </button>
        </div>
        <div class="se-trend">
          <span style="font-size:12px;color:var(--gray);font-weight:700">{{ tt('Trending', '热门') }}</span>
          <router-link v-for="h in HOT_LINKS" :key="h.label" class="trend-chip" :to="h.to">🔥 {{ h.label }}</router-link>
        </div>
      </div>

      <div v-if="pages > 1" style="display:flex;justify-content:center;gap:8px;margin-top:32px">
        <button class="btn btn-secondary btn-sm" :disabled="state.page <= 1" :aria-label="tt('Previous page', '上一页')" @click="goPage(state.page - 1)">←</button>
        <button v-if="pageWindow()[0] > 1" class="btn btn-secondary btn-sm" disabled>…</button>
        <button
          v-for="p in pageWindow()" :key="p" class="btn btn-sm pg"
          :class="p === state.page ? 'btn-primary' : 'btn-secondary'" @click="goPage(p)"
        >{{ p }}</button>
        <button v-if="pageWindow()[pageWindow().length - 1] < pages" class="btn btn-secondary btn-sm" disabled>…</button>
        <button class="btn btn-secondary btn-sm" :disabled="state.page >= pages" :aria-label="tt('Next page', '下一页')" @click="goPage(state.page + 1)">→</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sk-card { border-radius: 12px; }
.sk-img { aspect-ratio: 1; border-radius: 12px; }
.sk-line { border-radius: 8px; }
/* 筛选卡片 v2：行式分组 + 彩点标签 + 奶油底 chips（hover 粉化、选中 plum 浮起） */
.store-filters {
  background: linear-gradient(180deg, #fff 0%, #FFFDFA 100%);
  border: 1px solid rgba(31,27,30,.06);
  border-radius: 16px;
  padding: 8px 22px;
  margin-bottom: 22px;
  box-shadow: 0 1px 2px rgba(31,27,30,.03), 0 10px 28px rgba(31,27,30,.05);
}
.sf-row {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 13px 0;
  border-bottom: 1px solid rgba(31,27,30,.05);
}
.sf-last { border-bottom: none; }
.sf-label {
  flex: none;
  width: 64px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .3px;
  color: var(--gray);
}
/* 每行标签前置彩点：分类 rose / 风格 plum / 甲型 gold / 价格 success */
.sf-label::before {
  content: "";
  flex: none;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--rose);
  box-shadow: 0 0 0 3px rgba(232,180,184,.22);
}
.sf-row:nth-of-type(2) .sf-label::before { background: var(--plum); box-shadow: 0 0 0 3px rgba(138,74,99,.12); }
.sf-row:nth-of-type(3) .sf-label::before { background: var(--gold); box-shadow: 0 0 0 3px rgba(201,162,39,.16); }
.sf-row:nth-of-type(4) .sf-label::before { background: var(--success); box-shadow: 0 0 0 3px rgba(62,189,147,.16); }
.sf-chips { display: flex; flex-wrap: wrap; gap: 7px; min-width: 0; flex: 1; }
.sf-chips .trend-chip {
  margin: 0;
  padding: 5px 14px;
  font-size: 12.5px;
  color: #6B6167;
  background: #F7F3F5;
  border: 1px solid transparent;
  transition: all .15s ease-out;
}
.sf-chips .trend-chip:hover {
  background: var(--rose-pale);
  border-color: rgba(232,180,184,.6);
  color: var(--plum);
  transform: translateY(-1px);
}
.sf-chips .trend-chip.on {
  background: var(--plum);
  border-color: var(--plum);
  color: #fff;
  box-shadow: 0 3px 10px rgba(138,74,99,.3);
}
.trend-chip.on { background: var(--plum); border-color: var(--plum); color: #fff; }

.store-head { margin-bottom: 18px; }
.store-count { font-size: 12.5px; color: var(--gray); margin-bottom: 14px; }

@media (max-width: 768px) {
  .store-filters { padding: 4px 16px; border-radius: 12px; }
  .sf-row { flex-direction: column; align-items: flex-start; gap: 8px; padding: 11px 0; }
  .sf-label { width: auto; }
  .sf-chips { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; -webkit-overflow-scrolling: touch; }
  .sf-chips::-webkit-scrollbar { display: none; }
  .sf-chips .trend-chip { flex: none; }
}

/* 排序分段控件：容器圆角边框内分段按钮，选中段 plum 底白字 */
.seg { display: inline-flex; flex-wrap: wrap; gap: 2px; padding: 3px; border: 1.5px solid var(--gray-light); border-radius: 999px; background: #fff; }
.seg-btn { padding: 6px 14px; border-radius: 999px; font-size: 12.5px; font-weight: 600; color: var(--gray); transition: all .15s; }
.seg-btn:hover { color: var(--plum); background: var(--rose-pale); }
.seg-btn.on { background: var(--plum); color: #fff; }
/* 分页非当前页 hover 微上浮 */
.pg { transition: transform .15s ease-out, background .15s, color .15s, border-color .15s; }
.pg:not(.btn-primary):not(:disabled):hover { transform: translateY(-1px); }
/* 空态品牌化：44px 甲型符号 + 生效筛选 pill（可单独移除）+ 热词回逛 */
.store-empty { text-align: center; padding: 56px 0 40px; color: var(--gray); }
.se-icon { font-size: 44px; line-height: 1; color: var(--plum); opacity: .5; }
.se-filters { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; align-items: center; margin: 16px 0 4px; }
.se-pill { display: inline-flex; align-items: center; gap: 6px; background: var(--rose-pale); color: var(--plum); font-size: 12.5px; font-weight: 600; padding: 4px 6px 4px 12px; border-radius: 999px; }
.se-x { border: none; background: rgba(138,74,99,.12); color: var(--plum); width: 20px; height: 20px; border-radius: 50%; font-size: 12px; line-height: 1; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
.se-x:hover { background: var(--plum); color: #fff; }
.se-clear { margin-top: 2px; }
.se-trend { display: flex; flex-wrap: wrap; gap: 4px 8px; justify-content: center; align-items: center; margin-top: 20px; }
</style>
