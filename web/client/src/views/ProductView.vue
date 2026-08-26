<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req, wishlistAdd, wishlistHas, wishlistRemove } from '../api/client'
import { i18n, tt } from '../i18n'
import { catalogById } from '../data/catalog'
import { fmtDate } from '../composables/datetime'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'
import ProductCard from '../components/ProductCard.vue'

const route = useRoute()
const router = useRouter()
const cart = useCartStore()
const ui = useUiStore()
const auth = useAuthStore()

const p = ref(null)                 /* 商品详情 */
const loading = ref(true)
const loadErr = ref(false)          /* 网络/超时/5xx 失败态（非 404）：可重试，区别于商品不存在 */
const vIdx = ref(0)
const qty = ref(1)
const galIdx = ref(0)
const reviews = ref([])
const rvTotal = ref(0)
const rvPage = ref(1)
const rvMore = ref(false)
const adding = ref(false)
const notifyEmail = ref('')
const notifyState = ref(0)          /* 0 未订阅 / 1 提交中 / 2 已订阅 */
const lightbox = ref(null)          /* { src, caption } */
const zh = computed(() => i18n.lang === 'zh')
/* 全站统一邮箱校验（对齐 CheckoutView EMAIL_RE） */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/* 主图/缩略图加载失败兜底：回落 placehold 常量 + dataset 守卫防循环（对齐 HomeView heroFallback） */
const IMG_FALLBACK = 'https://placehold.co/600x600/E8B4B8/552338?text=GLOWMAG'
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = IMG_FALLBACK
}

const locale = computed(() => (zh.value ? 'zh-CN' : null))
const variant = computed(() => (p.value?.variants || [])[vIdx.value] || null)
const noVariants = computed(() => !!p.value && !(p.value.variants || []).length)
const stockStatus = computed(() => (variant.value ? (variant.value.stock_status || 'in') : 'out'))
const maxQty = computed(() => Math.max(1, Math.min(10, variant.value?.stock ?? 10)))

const media = computed(() => {
  const list = []
  const seen = new Set()
  for (const url of [p.value?.hero_image, ...((variant.value?.images || [])), ...(p.value?.images || [])]) {
    if (url && !seen.has(url)) { seen.add(url); list.push(url) }
  }
  return list.length ? list : ['https://placehold.co/600x600/E8B4B8/552338?text=GLOWMAG']
})
const showVideo = computed(() => galIdx.value >= media.value.length && !!p.value?.video_url)
const mainIdx = computed(() => Math.min(galIdx.value, media.value.length - 1))
const filled = computed(() => Math.max(0, Math.min(5, Math.round(rvAvg.value))))
const hasReviews = computed(() => rvCount.value > 0)
/* 评分口径：优先分布接口实时聚合（rating_avg 为百分制 480=4.8），
   回落商品冗余列 p.rating（已是 0-5 浮点，×100 对齐量纲再 /100），避免 0.05 级错值 */
const rvCount = computed(() => (distData.value && distData.value.rating_count) || (p.value?.rating_count || 0))
const rvAvg = computed(() => ((distData.value?.rating_avg ?? Math.round((p.value?.rating || 0) * 100)) / 100))

/* 评分分布：优先服务端聚合（已发布全量），未拉到时回退按已加载评价页估算 */
const distData = ref(null)
const dist = computed(() => {
  const d = distData.value
  if (d && d.distribution) {
    const total = Object.values(d.distribution).reduce((a, b) => a + b, 0) || 1
    return [5, 4, 3, 2, 1].map((star) => ({
      star, count: d.distribution[star] || 0,
      pct: Math.round((d.distribution[star] || 0) * 100 / total),
    }))
  }
  const buckets = [0, 0, 0, 0, 0]
  reviews.value.forEach((r) => {
    const i = Math.min(5, Math.max(1, Math.round(r.rating)))
    buckets[i - 1]++
  })
  const n = reviews.value.length || 1
  return [5, 4, 3, 2, 1].map((star) => ({ star, count: buckets[star - 1], pct: Math.round(buckets[star - 1] * 100 / n) }))
})

function pushRecent(d) {
  try {
    const arr = JSON.parse(localStorage.getItem('gm_recent') || '[]')
    const local = catalogById(d.id)
    const next = [{ id: d.id, title: d.title, titleZh: local && local.titleZh },
      ...arr.filter((x) => x && x.id !== d.id)].slice(0, 8)
    localStorage.setItem('gm_recent', JSON.stringify(next))
  } catch (_) { /* 隐私模式等 */ }
}

const rvRating = ref(0)             /* 评价星级筛选（0 = 全部） */
let rvSeq = 0                       /* 评价请求独立序号：星级筛选连点/加载更多与商品切换(ldSeq)互不污染 */
async function fetchReviews(reset) {
  if (!p.value) return
  const seq = ++rvSeq
  if (reset) { rvPage.value = 1; reviews.value = []; rvTotal.value = 0 }
  try {
    const d = await req('GET', `/api/catalog/reviews?product_id=${p.value.id}&page=${rvPage.value}&size=6` + (rvRating.value ? `&rating=${rvRating.value}` : ''))
    if (seq !== rvSeq) return
    reviews.value = reset ? (d.items || []) : reviews.value.concat(d.items || [])
    rvTotal.value = d.total || 0
  } catch (_) { if (seq === rvSeq && reset) reviews.value = [] }
  if (seq !== rvSeq) return
  rvMore.value = reviews.value.length < rvTotal.value
}
function toggleRvStar(star) {
  rvRating.value = (rvRating.value === star) ? 0 : star
  fetchReviews(true)
}

let ldSeq = 0
let lastKey = ''
/* keep=true 局部刷新（加购耗尽/409 回货）：保留选中变体/数量/图位，仅刷新数据 */
async function load(keep) {
  const seq = ++ldSeq
  rvSeq++ /* 作废在途评价请求（切商品瞬间旧响应不得写入新状态） */
  const key = String(route.query.slug || route.query.id || '')
  if (lastKey && key && key !== lastKey) window.scrollTo({ top: 0 })
  lastKey = key
  const prevVid = keep && variant.value ? variant.value.id : null
  const prevQty = keep ? qty.value : 1
  const prevGal = keep ? galIdx.value : 0
  vIdx.value = 0
  qty.value = 1
  galIdx.value = 0
  loading.value = true
  loadErr.value = false
  notifyState.value = 0
  wlDone.value = false
  rvRating.value = 0
  distData.value = null /* 重置评分分布：防上一商品数据残留 */
  const id = parseInt(route.query.id, 10)
  const slug = route.query.slug
  /* 无 id/slug 参数：直接渲染商品不存在态，不兜底请求 */
  if (!slug && !id) { p.value = null; loading.value = false; return }
  try {
    const d = slug
      ? await req('GET', '/api/catalog/products/' + encodeURIComponent(slug) + (locale.value ? '?locale=' + locale.value : ''))
      : await req('GET', '/api/catalog/products-by-id/' + id + (locale.value ? '?locale=' + locale.value : ''))
    if (seq !== ldSeq) return
    p.value = d
    /* 保留态恢复：按变体 id 找回 vIdx（找不到归 0）；qty/图位在 nextTick 覆写
       （先让 vIdx watcher 的 qty=1/图位同步先跑，保留值最终生效） */
    if (keep) {
      const vi = (d.variants || []).findIndex((v) => v.id === prevVid)
      vIdx.value = vi >= 0 ? vi : 0
      nextTick(() => {
        if (seq !== ldSeq) return
        qty.value = Math.min(prevQty, maxQty.value)
        galIdx.value = Math.min(prevGal, Math.max(0, media.value.length - 1))
      })
    }
    pushRecent(p.value)
    /* 心愿单初始态：登录时并发查是否已收藏（client.js 带布尔结果缓存，命中不再发请求） */
    if (auth.isLoggedIn) {
      wishlistHas(p.value.id)
        .then((hit) => { if (hit && seq === ldSeq) wlDone.value = true })
        .catch(() => { /* 未登录态/接口失败忽略 */ })
    }
    /* 动态 SEO：OG/JSON-LD（seo.js 监听 gm:seo 事件，路由切换自动复位） */
    try {
      window.dispatchEvent(new CustomEvent('gm:seo', { detail: {
        title: p.value.title + ' · GLOWMAG',
        description: (p.value.subtitle || p.value.description_md || '').slice(0, 160),
        image: p.value.hero_image, type: 'product',
        jsonLd: {
          '@context': 'https://schema.org', '@type': 'Product',
          name: p.value.title, image: [p.value.hero_image, ...(p.value.images || [])].filter(Boolean).slice(0, 4),
          description: (p.value.subtitle || '').slice(0, 300),
          sku: (p.value.variants && p.value.variants[0] && p.value.variants[0].sku) || undefined,
          offers: {
            '@type': 'Offer', priceCurrency: 'USD',
            price: ((p.value.price_min || 0) / 100).toFixed(2),
            availability: (p.value.stock_summary && p.value.stock_summary.out)
              ? 'https://schema.org/OutOfStock' : 'https://schema.org/InStock',
          },
          ...(p.value.rating_count ? {
            aggregateRating: { '@type': 'AggregateRating',
              ratingValue: (p.value.rating || 0).toFixed(1),
              reviewCount: p.value.rating_count },
          } : {}),
        },
      } }))
    } catch (_) { /* SEO 失败不影响页面 */ }
    /* 评价为首屏下方次要内容：不阻塞骨架屏撤除（慢/挂起时详情主体先行渲染） */
    fetchReviews(true).catch(() => {})
    req('GET', '/api/catalog/reviews/distribution?product_id=' + p.value.id)
      .then((dist) => { if (seq === ldSeq) distData.value = dist })
      .catch(() => { if (seq === ldSeq) distData.value = null })
  } catch (e) {
    if (seq !== ldSeq) return
    p.value = null
    /* 仅 404 视为商品不存在；网络/超时/5xx 等一律进失败态可重试 */
    if (!(e && e.status === 404)) loadErr.value = true
  }
  loading.value = false
}
watch(() => [route.query.slug, route.query.id].join('|'), () => load())
/* 站内切换语言：重拉详情（locale 翻译口径），标题/描述即时跟随 */
watch(locale, () => { if (p.value || route.query.id || route.query.slug) load() })
onMounted(load)

watch(vIdx, () => {
  qty.value = 1
  const vimg = (variant.value?.images || [])[0]
  if (vimg) {
    const idx = media.value.indexOf(vimg)
    if (idx >= 0) galIdx.value = idx
  }
})

/* v16 移动端图廊：主图为横滑 scroll-snap 容器（.pdp-main），滑动↔galIdx 双向同步；
   桌面容器不可滚动（overflow:hidden），两个函数均为 no-op，行为与改造前一致 */
const mainScrollEl = ref(null)
let galScrollT = null
const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches
function onGalScroll() {
  const el = mainScrollEl.value
  if (!el || el.scrollWidth <= el.clientWidth) return
  clearTimeout(galScrollT)
  galScrollT = setTimeout(() => {
    const max = media.value.length + (p.value?.video_url ? 1 : 0) - 1
    const i = Math.max(0, Math.min(max, Math.round(el.scrollLeft / el.clientWidth)))
    if (i !== galIdx.value) galIdx.value = i
  }, 80)
}
function syncGalScroll() {
  const el = mainScrollEl.value
  if (!el || el.scrollWidth <= el.clientWidth) return
  const t = galIdx.value * el.clientWidth
  if (Math.abs(el.scrollLeft - t) > 4) el.scrollTo({ left: t, behavior: reduceMotion() ? 'auto' : 'smooth' })
}
watch(galIdx, syncGalScroll)

/* 已订阅状态查询按 variant_id 内存缓存（promise 级）：售罄变体间快速切换不重复请求，防 429 限流 */
const notifyHasCache = {}
watch(variant, async (v) => {
  notifyState.value = 0
  /* 仅清自动填充形态的邮箱（空 / 等于当前登录用户 email），保留用户手输的其它邮箱 */
  if (!notifyEmail.value || notifyEmail.value === (auth.user && auth.user.email)) notifyEmail.value = ''
  const em = auth.user && auth.user.email
  if (v && v.stock_status === 'out' && em) {
    if (!notifyHasCache[v.id]) {
      notifyHasCache[v.id] = req('GET', `/api/catalog/stock-notify?variant_id=${v.id}&email=${encodeURIComponent(em)}`)
        .catch(() => ({ watching: false }))
    }
    const d = await notifyHasCache[v.id]
    if (variant.value && variant.value.id === v.id && d.watching) notifyState.value = 2
  }
})

const basePrice = computed(() => (p.value?.variants?.[0]?.price ?? 0) / 100)
const unit = computed(() => variant.value ? variant.value.price / 100 : basePrice.value)
/* 组合折扣后端仅统计 press-on-nails 类目：字段缺失时缺省不显示按钮 */
const bundleable = computed(() => p.value?.category_slug === 'press-on-nails')
/* 面包屑分类可读名（后端只回 slug，前端就近映射；未知 slug 不渲染该级） */
const CAT_NAME = { 'press-on-nails': ['Press-on Nails', '穿戴甲'], 'magnetic-lashes': ['Magnetic Lashes', '磁性睫毛'] }
const catLabel = computed(() => {
  const row = CAT_NAME[p.value?.category_slug || '']
  return row ? tt(row[0], row[1]) : ''
})

function mdHtml(mdText) {
  /* 先整体转义再做 markdown 替换：后台录入的 HTML 不进入 v-html（参考 MarketingPopups） */
  const esc = (s) => String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
  return String(mdText || '').split(/\n{2,}/).map((block) => {
    const lines = block.split('\n').filter((l) => l.trim())
    if (lines.length && lines.every((l) => /^\s*[-*]\s+/.test(l))) {
      return '<ul>' + lines.map((l) => `<li>${inline(l.replace(/^\s*[-*]\s+/, ''))}</li>`).join('') + '</ul>'
    }
    return `<p>${lines.map(inline).join('<br>')}</p>`
  }).join('')
}

function onQtyChange(e) {
  const n = parseInt(e.target.value, 10)
  qty.value = Number.isFinite(n) ? Math.max(1, Math.min(maxQty.value, n)) : qty.value
  e.target.value = qty.value
}

async function addToCart() {
  if (!variant.value || variant.value.stock <= 0) {
    ui.toast(zh.value ? '该商品已售罄' : 'Sold out', 'error')
    return
  }
  /* 数量被钳制时明确告知（仅剩 N 件） */
  if (qty.value > maxQty.value) {
    ui.toast(zh.value ? `库存仅剩 ${maxQty.value} 件` : `Only ${maxQty.value} left in stock`, 'error')
    qty.value = maxQty.value
  }
  adding.value = true
  /* cart.add 失败已由 store toast + refresh，这里吞掉避免全局 errorHandler 重复弹错 */
  let ok = false
  try {
    ok = await cart.add(variant.value.id, Math.min(qty.value, maxQty.value), ui)
  } catch (e) { console.debug('[ProductView] add to cart failed:', e) }
  if (ok && variant.value.stock - qty.value <= 0) await load(true)
  adding.value = false
}

const bundling = ref(false)
async function bundleAdd() {
  if (bundling.value || !variant.value) return
  if (variant.value.stock < 2) {
    ui.toast(zh.value ? '库存不足两套，无法享受组合价' : 'Not enough stock for the bundle deal', 'error')
    return
  }
  bundling.value = true
  /* 屏蔽 cart.add 通用成功 toast（保留错误 toast），仅弹组合折扣说明一条 */
  const quietUi = Object.assign({}, ui, {
    toast: (msg, type) => { if (type !== 'success' || !/added to cart|已加入购物车/i.test(String(msg))) ui.toast(msg, type) },
    openCart: () => {},
  })
  let ok = false
  try {
    ok = await cart.add(variant.value.id, 2, quietUi)
  } catch (e) { console.debug('[ProductView] bundle add failed:', e) }
  if (ok) {
    ui.toast(zh.value ? '已加 2 套 — 15% 折扣结算时自动生效 🎁' : '2 sets in cart — 15% off applied at checkout 🎁', 'success')
    if (variant.value.stock - 2 <= 0) await load(true)
  }
  bundling.value = false
}

/* 心愿单：登录调 API + 角标事件；未登录跳登录并带回跳；已收藏可再点移除（toggle） */
const wlBusy = ref(false)
const wlDone = ref(false)
async function toggleWishlist() {
  if (wlBusy.value || !p.value) return
  if (!auth.isLoggedIn) {
    router.push({ path: '/login', query: { next: route.fullPath } })
    return
  }
  wlBusy.value = true
  try {
    if (wlDone.value) {
      await wishlistRemove(p.value.id)
      wlDone.value = false
      try {
        const n = Math.max(0, (parseInt(localStorage.getItem('gm_wl_count'), 10) || 1) - 1)
        localStorage.setItem('gm_wl_count', String(n))
      } catch (_) { /* 隐私模式等 */ }
      window.dispatchEvent(new Event('gm:wl-changed'))
      ui.toast(zh.value ? '已从心愿单移除' : 'Removed from wishlist', 'success')
      return
    }
    await wishlistAdd(p.value.id)
    wlDone.value = true
    try {
      const n = (parseInt(localStorage.getItem('gm_wl_count'), 10) || 0) + 1
      localStorage.setItem('gm_wl_count', String(n))
    } catch (_) { /* 隐私模式等 */ }
    window.dispatchEvent(new Event('gm:wl-changed'))
    ui.toast(zh.value ? '已加入心愿单 ♥' : 'Added to wishlist ♥', 'success')
  } catch (e) {
    if (!wlDone.value && e && e.status === 409) {
      wlDone.value = true
      ui.toast(zh.value ? '已在心愿单中 ♥' : 'Already in your wishlist ♥', 'success')
    } else if (wlDone.value && e && e.status === 404) {
      /* 心愿单本就没有它：本地态直接拉平 */
      wlDone.value = false
    } else {
      ui.toast(zh.value
        ? (wlDone.value ? '移除失败，请重试' : '加入心愿单失败，请重试')
        : (wlDone.value ? 'Could not remove — try again' : 'Could not add to wishlist — try again'), 'error')
    }
  } finally { wlBusy.value = false }
}

function notifyEmailValue() {
  return (notifyEmail.value || '').trim().toLowerCase() || (auth.user && auth.user.email) || ''
}

async function notifyMe() {
  if (!variant.value) return
  const em = notifyEmailValue()
  if (!em) {
    ui.toast(zh.value ? '请先填写邮箱地址' : 'Enter your email first', 'error')
    return
  }
  if (!EMAIL_RE.test(em)) {
    ui.toast(zh.value ? '邮箱格式不正确' : 'Enter a valid email address', 'error')
    return
  }
  notifyState.value = 1
  try {
    await req('POST', '/api/catalog/stock-notify', { variant_id: variant.value.id, email: em })
    notifyHasCache[variant.value.id] = Promise.resolve({ watching: true })
    notifyState.value = 2
    ui.toast(zh.value ? '到货后第一时间邮件通知你' : "We'll email you when it's back in stock", 'success')
  } catch (e) {
    notifyState.value = 0
    if (e.status === 400) ui.toast(zh.value ? '邮箱格式不正确' : 'Enter a valid email address', 'error')
    else if (e.status === 409) { ui.toast(zh.value ? '该款刚回货啦，快下单！' : 'Just restocked — grab it now!', 'success'); load(true) }
    else ui.toast(zh.value ? '订阅失败，请稍后再试' : 'Subscribe failed, try again', 'error')
  }
}

async function cancelNotify() {
  const em = notifyEmailValue()
  if (!variant.value || !em) { notifyState.value = 0; return }
  try {
    await req('DELETE', `/api/catalog/stock-notify?variant_id=${variant.value.id}&email=${encodeURIComponent(em)}`)
    notifyHasCache[variant.value.id] = Promise.resolve({ watching: false })
  } catch (_) { /* 幂等 */ }
  notifyState.value = 0
  ui.toast(zh.value ? '已取消到货通知' : 'Restock alert cancelled')
}

function moreReviews() { rvPage.value++; fetchReviews(false) }
function openLightbox(src, caption) { lightbox.value = { src, caption } }
function closeLightbox() { lightbox.value = null }
/* Escape 关闭 / ←→ 在媒体列表内切换（评价晒图不在 media 内则忽略） */
function onKey(e) {
  if (!lightbox.value) return
  if (e.key === 'Escape') { closeLightbox(); return }
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const i = media.value.indexOf(lightbox.value.src)
    if (i < 0) return
    const n = e.key === 'ArrowRight' ? Math.min(media.value.length - 1, i + 1) : Math.max(0, i - 1)
    if (n !== i) lightbox.value = { src: media.value[n], caption: lightbox.value.caption }
  }
}
/* Lightbox 滚动锁走 ui.lightboxOpen 全局通道（anyOverlay → StoreLayout gm-locked 统一驱动，
   消除与 StoreLayout watch 的 gm-locked 双写竞态） */
watch(lightbox, (v) => { ui.lightboxOpen = !!v })
/* v16: PDP 在场标记（style.css v16 据此让返回顶部避开粘性加购栏） */
onMounted(() => { document.body.classList.add('gm-pdp'); window.addEventListener('keydown', onKey) })
onUnmounted(() => {
  document.body.classList.remove('gm-pdp')
  if (ui.lightboxOpen) ui.lightboxOpen = false /* 卸载时释放浮层位，防 anyOverlay 卡死 */
  window.removeEventListener('keydown', onKey)
})

const gmEta = () => {
  const M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const d1 = new Date(Date.now() + 3 * 864e5), d2 = new Date(Date.now() + 6 * 864e5)
  return d1.getMonth() === d2.getMonth()
    ? `${M[d1.getMonth()]} ${d1.getDate()}–${d2.getDate()}`
    : `${M[d1.getMonth()]} ${d1.getDate()} – ${M[d2.getMonth()]} ${d2.getDate()}`
}
</script>

<template>
  <section v-if="loading" class="section">
    <div class="container">
        <div class="grid-m-1 pdp-grid">
          <div class="sk-block sk-shimmer" style="aspect-ratio:1;border-radius:18px"></div>
          <div style="display:grid;gap:14px">
            <div class="sk-line sk-shimmer" style="width:70%;height:34px"></div>
            <div class="sk-line sk-shimmer" style="width:40%;height:16px"></div>
            <div class="sk-line sk-shimmer" style="width:30%;height:30px"></div>
            <div class="sk-line sk-shimmer" style="width:100%;height:44px"></div>
            <div class="sk-line sk-shimmer" style="width:100%;height:52px"></div>
          </div>
        </div>
    </div>
  </section>

  <section class="section pdp-page" v-else-if="p">
    <div class="container">
      <nav style="font-size:12.5px;color:var(--gray);margin-bottom:16px">
        <router-link to="/" style="color:var(--gray)">{{ i18n.t('crumb.home') }}</router-link> /
        <router-link to="/store" style="color:var(--gray)">{{ i18n.t('footer.all') }}</router-link>
        <template v-if="catLabel"> /
          <router-link :to="'/store?cat=' + p.category_slug" style="color:var(--gray)">{{ catLabel }}</router-link>
        </template>
        / <span style="color:var(--plum)">{{ p.title }}</span>
      </nav>
      <div class="grid-m-1 pdp-grid">
        <!-- 左：媒体（v16：主图区改造为 scroll-snap 滑轨——移动端横滑切图，桌面仅显示 .on 单图与原实现一致） -->
        <div>
          <div style="position:relative">
            <div
              ref="mainScrollEl"
              class="pdp-main"
              style="position:relative;border-radius:18px;overflow:hidden;aspect-ratio:1;background:var(--rose-pale)"
              @scroll.passive="onGalScroll"
            >
              <div v-for="(im, i) in media" :key="im" class="pdp-slide" :class="{ on: !showVideo && mainIdx === i }">
                <img :src="im" :alt="p.title" style="width:100%;height:100%;object-fit:cover" @error="imgFallback">
              </div>
              <div v-if="p.video_url" class="pdp-slide" :class="{ on: showVideo }">
                <video :src="p.video_url" controls playsinline style="width:100%;height:100%;object-fit:cover;background:#000"></video>
              </div>
            </div>
            <span v-if="p.is_new" class="badge badge-new" style="position:absolute;top:14px;left:14px">NEW</span>
            <span v-else-if="p.is_best_seller" class="badge badge-best" style="position:absolute;top:14px;left:14px">BEST</span>
            <span v-if="p.compare_at_price && p.compare_at_price > (variant?.price ?? p.price_min)" class="badge badge-sale" style="position:absolute;top:14px;right:14px">
              -{{ Math.max(1, Math.round((1 - (variant?.price ?? p.price_min) / p.compare_at_price) * 100)) }}%
            </span>
            <button v-if="!showVideo && media.length > 1" class="pdp-zoom" :aria-label="zh ? '放大查看' : 'Zoom image'" @click="openLightbox(media[mainIdx], p.title)">⤢</button>
          </div>
          <div v-if="media.length > 1 || p.video_url" class="pdp-thumbs" style="display:flex;gap:8px;margin-top:10px;overflow-x:auto;padding-bottom:2px">
            <button
              v-for="(im, i) in media" :key="im"
              class="pdp-thumb" :class="{ on: mainIdx === i }" :aria-label="tt(`${p.title} view ${i + 1}`, `${p.title} 图片 ${i + 1}`)" @click="galIdx = i"
            >
              <img :src="im" :alt="tt(`${p.title} view ${i + 1}`, `${p.title} 图片 ${i + 1}`)" loading="lazy" @error="imgFallback">
            </button>
            <button v-if="p.video_url" class="pdp-thumb" :class="{ on: showVideo }" :aria-label="zh ? '观看视频' : 'Watch video'" @click="galIdx = media.length">
              <img :src="media[0]" alt="" loading="lazy" @error="imgFallback">
              <span class="pdp-play">▶</span>
            </button>
          </div>
        </div>

        <!-- 右：购买面板 -->
        <div>
          <!-- v16: clamp——≥486px 恒为 34px 与桌面一致，移动端随宽收缩 -->
          <h1 style="font-family:var(--font-title);font-size:clamp(24px,7vw,34px);margin-bottom:6px">{{ p.title }}</h1>
          <div v-if="p.subtitle" style="color:var(--gray);font-size:14.5px;margin-bottom:12px">{{ p.subtitle }}</div>
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            <template v-if="hasReviews">
              <span class="stars" style="color:var(--gold)">{{ '★'.repeat(filled) }}<span class="off">{{ '★'.repeat(5 - filled) }}</span></span>
              <span style="font-size:13px;color:var(--gray)">{{ rvAvg.toFixed(1) }} · {{ rvCount.toLocaleString() }} {{ zh ? '条评价' : 'reviews' }}</span>
            </template>
            <span v-else style="font-size:13px;color:var(--gray)">✨ {{ zh ? '全新上架 · 抢先体验' : 'Just launched — be the first to review' }}</span>
          </div>
          <div class="pdp-price-row" style="display:flex;align-items:baseline;gap:10px;margin-bottom:18px">
            <template v-if="noVariants">
              <span style="font-size:20px;font-weight:700;color:var(--plum)">✨ {{ zh ? '即将上架 · 敬请期待' : 'Coming soon' }}</span>
            </template>
            <template v-else>
              <span style="font-size:32px;font-weight:800;color:var(--plum);font-variant-numeric:tabular-nums">
                ${{ unit.toFixed(2) }}
              </span>
              <span v-if="variant && p.compare_at_price && p.compare_at_price > variant.price" style="color:var(--gray);text-decoration:line-through">
                ${{ (p.compare_at_price / 100).toFixed(2) }}
              </span>
              <span v-if="variant && p.compare_at_price && p.compare_at_price > variant.price" class="save-pill">
                {{ tt('SAVE', '省') }} ${{ ((p.compare_at_price - variant.price) / 100).toFixed(2) }}
              </span>
              <span v-if="variant?.sku" class="pdp-sku" style="font-size:11.5px;color:var(--gray-light);font-weight:600">SKU {{ variant.sku }}</span>
            </template>
          </div>

          <!-- 变体选择 -->
          <div v-if="!noVariants" style="margin-bottom:18px">
            <div style="font-size:12.5px;font-weight:700;letter-spacing:1px;color:var(--gray);margin-bottom:10px">
              {{ zh ? '甲型' : 'SHAPE' }} — <span>{{ variant?.option1_value }}</span>
              <span v-if="variant?.option2_value" style="margin-left:8px;font-weight:500;letter-spacing:0">· {{ variant.option2_value }}</span>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <!-- 售罄变体保持可选（置灰视觉+aria 后缀），选中即到货通知表单（不再 disabled 拦截） -->
              <button
                v-for="(v, i) in p.variants" :key="v.id"
                class="vbtn" :class="{ sel: vIdx === i, out: v.stock_status === 'out' }"
                :aria-label="v.option1_value + (v.stock_status === 'out' ? tt(' (sold out)', '（已售罄）') : '')"
                @click="vIdx = i"
              >
                {{ v.option1_value }}
                <!-- 与首变体的价差双向展示（+/−），价格感知对称 -->
                <b v-if="i > 0 && v.price !== p.variants[0].price" :style="{ color: v.price > p.variants[0].price ? 'var(--plum)' : 'var(--success)' }">
                  {{ v.price > p.variants[0].price ? '+' : '−' }}${{ (Math.abs(v.price - p.variants[0].price) / 100).toFixed(2) }}
                </b>
                <i v-if="v.stock_status === 'out'">{{ zh ? '售罄' : 'Sold out' }}</i>
                <i v-else-if="v.stock_status === 'low'" style="color:var(--warn)">{{ zh ? `仅剩 ${v.stock}` : `${v.stock} left` }}</i>
              </button>
            </div>
          </div>

          <!-- 库存提示 -->
          <div v-if="!noVariants" style="margin-bottom:18px;font-size:13.5px">
            <template v-if="stockStatus === 'out'">
              <b style="color:var(--error)">{{ zh ? '已售罄' : 'Out of stock' }}</b>
              <div v-if="notifyState !== 2" style="display:flex;gap:8px;margin-top:10px;max-width:360px">
                <!-- v16: 尺寸上收为类规则（桌面 40px/13px 原样复现，移动端 44px/16px 防缩放） -->
                <input
                  v-model="notifyEmail" class="input pdp-notify" type="email"
                  :placeholder="zh ? '输入邮箱，到货通知你' : 'Email me when back in stock'"
                  @keyup.enter="notifyMe"
                >
                <button type="button" class="btn btn-secondary pdp-notify-btn" :disabled="notifyState === 1" @click="notifyMe">
                  {{ notifyState === 1 ? '…' : (zh ? '到货通知' : 'Notify me') }}
                </button>
              </div>
              <div v-else style="margin-top:10px;display:flex;align-items:center;gap:10px;color:var(--success);font-size:13px">
                <b>✓ {{ zh ? '已订阅到货通知' : 'You\'re on the restock list' }}</b>
                <button type="button" style="color:var(--gray);text-decoration:underline;font-size:12px" @click="cancelNotify">{{ zh ? '取消' : 'Cancel' }}</button>
              </div>
            </template>
            <template v-else-if="stockStatus === 'low'">
              ⚡ <b style="color:var(--warn)">{{ zh ? `仅剩 ${variant.stock} 件` : `Only ${variant.stock} left` }}</b>
              <span style="color:var(--gray)">{{ zh ? '— 手慢无' : '— selling fast' }}</span>
              <div class="stock-track"><div class="stock-fill" :style="{ width: Math.min(variant.stock * 2, 100) + '%' }"></div></div>
            </template>
            <template v-else>🚚 <b style="color:var(--success)">{{ zh ? '现货 · 即刻发出' : 'In stock & ready to ship' }}</b></template>
          </div>

          <!-- 数量 + 加购 + 心愿单 -->
          <div v-if="!noVariants" style="display:flex;gap:12px;margin-bottom:14px;align-items:stretch">
            <div style="display:flex;align-items:center;border:1.5px solid var(--gray-light);border-radius:12px">
              <button class="qbtn" :disabled="qty <= 1" @click="qty = Math.max(1, qty - 1)">−</button>
              <input
                class="pdp-qty-input" type="text" inputmode="numeric" :value="qty"
                :aria-label="zh ? '数量' : 'Quantity'" @change="onQtyChange" @focus="$event.target.select()"
              >
              <button class="qbtn" :disabled="qty >= maxQty" @click="qty = Math.min(maxQty, qty + 1)">＋</button>
            </div>
            <button class="btn btn-primary btn-lg" style="flex:1" :disabled="stockStatus === 'out' || adding" :class="{ loading: adding }" @click="addToCart">
              {{ zh ? '加入购物车' : 'Add to Cart' }} · ${{ (unit * qty).toFixed(2) }}
            </button>
            <button
              type="button" class="wl-btn" :class="{ active: wlDone }" :disabled="wlBusy"
              :aria-label="wlDone ? (zh ? '移出心愿单' : 'Remove from wishlist') : (zh ? '加入心愿单' : 'Add to wishlist')"
              :title="wlDone ? (zh ? '移出心愿单' : 'Remove from wishlist') : (zh ? '加入心愿单' : 'Add to wishlist')"
              @click="toggleWishlist"
            ><span aria-hidden="true">{{ wlDone ? '♥' : '♡' }}</span></button>
          </div>
          <button v-if="bundleable && !noVariants" class="btn btn-secondary btn-block" :disabled="bundling" :class="{ loading: bundling }" @click="bundleAdd">
            🎁 {{ zh ? '买 2 件享 85 折' : 'Buy 2 & save 15%' }}（{{ zh ? '省' : 'save' }} ${{ (unit * 2 * 0.15).toFixed(2) }}）— {{ zh ? '结算自动生效' : 'applied in cart' }}
          </button>

          <div style="font-size:12.5px;color:var(--gray);margin:16px 0 0;display:grid;gap:6px">
            <span>🚚 {{ tt('Free shipping over $35', '满 $35 包邮') }} · {{ zh ? '预计送达' : 'Est. delivery' }} {{ gmEta() }}</span>
            <span>↩️ 30-day returns · {{ zh ? '换货永久免费' : 'exchanges always free' }}</span>
            <span>🔒 {{ zh ? '安全支付' : 'Secure checkout' }} · VISA / MC / PAYPAL / KLARNA</span>
          </div>
        </div>
      </div>

      <!-- 商品描述 -->
      <section v-if="p.description_md" class="section" style="padding-top:44px">
        <div class="section-head">
          <h2 class="section-title">{{ zh ? '商品详情' : 'About this set' }}</h2>
        </div>
        <div class="pdp-desc" style="max-width:760px" v-html="mdHtml(p.description_md)"></div>
      </section>

      <!-- 评价 -->
      <section class="section" style="padding-top:44px">
        <div class="section-head">
          <h2 class="section-title">
            {{ zh ? '买家评价' : 'Reviews' }} ({{ rvCount.toLocaleString() }})
            <span v-if="rvRating" style="font-size:14px;font-weight:600;color:var(--plum);vertical-align:middle">
              · {{ rvRating }}★ · {{ zh ? `当前 ${rvTotal} 条` : `${rvTotal} shown` }}
              <button type="button" class="rv-clear" @click="toggleRvStar(rvRating)">{{ zh ? '清除' : 'clear' }}</button>
            </span>
          </h2>
          <span v-if="hasReviews" style="font-size:14px;color:var(--gray)">{{ rvAvg.toFixed(1) }} / 5</span>
        </div>
        <div v-if="hasReviews || reviews.length" class="grid-m-1" style="display:grid;grid-template-columns:240px 1fr;gap:36px;align-items:start">
          <div class="card" style="padding:20px">
            <div style="font-family:var(--font-title);font-size:40px;font-weight:700;color:var(--plum)">{{ rvAvg.toFixed(1) }}</div>
            <div class="stars" style="margin:4px 0 6px">{{ '★'.repeat(filled) }}<span class="off">{{ '★'.repeat(5 - filled) }}</span></div>
            <div style="font-size:12px;color:var(--gray);margin-bottom:12px">{{ rvCount.toLocaleString() }} {{ zh ? '条已审核评价' : 'verified reviews' }}</div>
            <button
              v-for="d in dist" :key="d.star" type="button" class="dist-row"
              :class="{ on: rvRating === d.star, dim: !!rvRating && rvRating !== d.star }"
              :aria-pressed="rvRating === d.star ? 'true' : 'false'"
              :aria-label="zh ? `筛选 ${d.star} 星评价` : `Filter ${d.star}-star reviews`"
              @click="toggleRvStar(d.star)"
            >
              <span style="width:26px;flex:none">{{ d.star }}★</span>
              <span style="flex:1;height:5px;background:var(--gray-light);border-radius:3px;overflow:hidden"><span style="display:block;height:100%;background:var(--gold);border-radius:3px" :style="{ width: d.pct + '%' }"></span></span>
              <span class="dist-n">{{ d.count }}</span>
            </button>
          </div>
          <div>
            <div class="grid grid-2 rv-list">
              <div v-for="rv in reviews" :key="rv.id" class="card card-lift" style="padding:18px">
                <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px">
                  <span class="rv-ava" aria-hidden="true"><span>{{ (rv.user || rv.user_name || 'A').charAt(0).toUpperCase() }}</span></span>
                  <b style="font-size:13px">{{ rv.user || rv.user_name || 'Glowmag Fan' }}</b>
                  <span style="font-size:10.5px;font-weight:700;color:var(--success);background:rgba(62,189,147,.10);border:1px solid rgba(62,189,147,.35);border-radius:999px;padding:1.5px 9px;white-space:nowrap">✓ {{ zh ? '已验证购买' : 'Verified Buyer' }}</span>
                  <span v-if="rv.created_at" style="font-size:11.5px;color:var(--gray-light);margin-left:auto;white-space:nowrap">{{ fmtDate(rv.created_at) }}</span>
                </div>
                <div class="stars" style="margin:8px 0">{{ '★'.repeat(Math.min(5, Math.max(0, rv.rating))) }}<span class="off">{{ '★'.repeat(5 - Math.min(5, Math.max(0, rv.rating))) }}</span></div>
                <p style="font-size:14px">{{ rv.content }}</p>
                <div v-if="(rv.images || []).length" style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap">
                  <img
                    v-for="im in rv.images.slice(0, 4)" :key="im" :src="im" loading="lazy"
                    :alt="zh ? '买家晒图' : 'Customer photo'" style="width:56px;height:56px;border-radius:8px;object-fit:cover;cursor:zoom-in;border:1px solid var(--gray-light)"
                    @error="imgFallback"
                    @click="openLightbox(im, rv.user || rv.user_name || '')"
                  >
                </div>
              </div>
            </div>
            <div v-if="rvMore" style="text-align:center;margin-top:20px">
              <button class="btn btn-secondary" @click="moreReviews">
                {{ zh ? `加载更多（还有 ${rvTotal - reviews.length} 条）` : `Load more (${rvTotal - reviews.length} left)` }}
              </button>
            </div>
          </div>
        </div>
        <div v-else style="text-align:center;color:var(--gray);padding:30px 0">
          💅 {{ zh ? '第一个来评价吧' : 'Be the first to review this set' }} — <router-link to="/account/orders" style="color:var(--plum)">{{ tt('view my orders', '查看我的订单') }}</router-link>
        </div>
      </section>

      <!-- 相关推荐 -->
      <section v-if="(p.related || []).length" class="section" style="padding-top:20px">
        <div class="section-head">
          <h2 class="section-title">{{ zh ? '猜你也喜欢' : 'You may also like' }}</h2>
        </div>
        <div class="grid grid-4">
          <ProductCard v-for="r in p.related" :key="r.id" :p="r" />
        </div>
      </section>
    </div>

    <!-- v16 移动端粘性加购栏：价格 + 加购（≤768 显示，fixed 于 tabbar 之上；复用 addToCart，SEO/既有交互零改动） -->
    <div v-if="!noVariants" class="pdp-buybar">
      <div class="pdp-buybar-info">
        <Transition name="tick" mode="out-in">
          <b :key="unit.toFixed(2) + ':' + qty" class="pdp-buybar-price">{{ qty > 1 ? qty + ' × $' + unit.toFixed(2) + ' · ' : '' }}${{ (unit * qty).toFixed(2) }}</b>
        </Transition>
        <s v-if="variant && p.compare_at_price && p.compare_at_price > variant.price">${{ (p.compare_at_price / 100).toFixed(2) }}</s>
        <span class="pdp-buybar-title">{{ p.title }}</span>
      </div>
      <button v-if="stockStatus === 'out'" class="btn btn-secondary" disabled>{{ zh ? '已售罄' : 'Sold out' }}</button>
      <button v-else class="btn btn-primary" :class="{ loading: adding }" :disabled="adding" @click="addToCart">
        {{ zh ? '加入购物车' : 'Add to Cart' }}
      </button>
    </div>
  </section>

  <section v-else-if="loadErr" class="section">
    <div class="container" style="text-align:center;padding:60px 0;color:var(--gray)">
      <div style="font-size:44px;margin-bottom:10px">⚠️</div>
      {{ tt('Failed to load this product', '商品加载失败，请重试') }}
      <div style="margin-top:14px"><button class="btn btn-secondary btn-sm" @click="load">↻ {{ tt('Retry', '重试') }}</button></div>
    </div>
  </section>

  <section v-else class="section">
    <div class="container" style="text-align:center;padding:80px 0;color:var(--gray)">
      <div style="font-size:44px;margin-bottom:10px">💅</div>
      {{ zh ? '商品不存在或已下架' : 'Product not found' }} — <router-link to="/store" style="color:var(--plum)">{{ zh ? '回商店逛逛' : 'back to store' }}</router-link>
    </div>
  </section>

  <div v-if="lightbox" class="lb-overlay" role="dialog" aria-modal="true" :aria-label="lightbox.caption || (zh ? '查看大图' : 'Image viewer')" @click.self="closeLightbox">
    <button class="lb-x" :aria-label="zh ? '关闭' : 'Close'" @click="closeLightbox">×</button>
    <img :src="lightbox.src" :alt="lightbox.caption || 'GLOWMAG'" @error="closeLightbox">
    <div v-if="lightbox.caption" class="lb-cap">{{ lightbox.caption }}</div>
  </div>
</template>

<style scoped>
.pdp-grid { display: grid; grid-template-columns: 1.05fr .95fr; gap: 44px; }
.vbtn { display: inline-flex; align-items: center; gap: 8px; border: 1.5px solid var(--gray-light); background: #fff; border-radius: 12px; padding: 10px 16px; font-size: 13.5px; font-weight: 600; color: var(--ink); transition: all .15s; }
.vbtn:hover:not(:disabled) { border-color: var(--rose); background: var(--rose-pale); }
.vbtn.sel { border-color: var(--rose); background: var(--rose-pale); color: var(--ink); box-shadow: 0 3px 10px rgba(232,180,184,.45); }
.vbtn.sel b { color: var(--plum); }
.vbtn i { font-style: normal; font-size: 11px; color: var(--gray); }
/* 售罄变体可选（点击展示到货通知）：保留置灰+删除线视觉，光标改 pointer */
.vbtn.out { color: var(--gray); background: var(--gray-light); border-color: var(--gray-light); cursor: pointer; text-decoration: line-through; }
.vbtn.out i { color: var(--error); text-decoration: none; font-weight: 700; }
.vbtn.sel i { color: var(--gray); }
/* 选中态优先于置灰：售罄变体被选中时仍显示 plum 选中框（通知表单归属可见） */
.vbtn.sel.out { border-color: var(--rose); background: var(--rose-pale); color: var(--gray); box-shadow: none; }
.qbtn { width: 34px; height: 38px; font-size: 17px; font-weight: 600; color: var(--plum); }
.qbtn:disabled { color: var(--gray-light); cursor: not-allowed; }
.pdp-qty-input { width: 44px; border: none; background: transparent; text-align: center; font-family: inherit; font-size: 15px; font-weight: 600; color: var(--ink); outline: none; }
.wl-btn { flex: none; width: 54px; border: 1.5px solid var(--gray-light); border-radius: 12px; background: #fff; color: var(--plum); font-size: 22px; line-height: 1; cursor: pointer; transition: all .15s; }
.wl-btn:hover:not(:disabled) { border-color: var(--rose); background: var(--rose-pale); }
.wl-btn.active { color: var(--rose); border-color: var(--rose); background: var(--rose-pale); }
.wl-btn:disabled { opacity: .55; cursor: wait; }
.stock-track { height: 5px; background: var(--gray-light); border-radius: 3px; margin-top: 8px; max-width: 260px; overflow: hidden; }
.stock-fill { height: 100%; background: linear-gradient(90deg, var(--warn), var(--coral)); border-radius: 3px; transition: width .4s ease-out; }
.pdp-thumb { position: relative; flex: none; width: 64px; height: 64px; border-radius: 10px; overflow: hidden; border: 1.5px solid var(--gray-light); padding: 0; transition: border-color .15s; }
.pdp-thumb.on { border-color: var(--plum); box-shadow: 0 0 0 2px rgba(138,74,99,.15); }
.pdp-thumb img { width: 100%; height: 100%; object-fit: cover; }
.pdp-play { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: rgba(31,27,30,.42); color: #fff; font-size: 16px; }
.pdp-zoom { position: absolute; bottom: 12px; right: 12px; width: 34px; height: 34px; border-radius: 50%; background: rgba(255,255,255,.92); color: var(--plum); font-size: 15px; font-weight: 700; box-shadow: var(--shadow-card); transition: transform .15s; }
.pdp-zoom:hover { transform: scale(1.08); }
.pdp-desc { font-size: 14.5px; line-height: 1.75; color: var(--ink); }
.pdp-desc p { margin-bottom: 12px; }
.pdp-desc ul { margin: 0 0 12px 20px; }
.pdp-desc li { margin-bottom: 4px; }
.rv-list { gap: 16px; }
/* 评价人头像渐变描边（rose→plum，对齐 HomeView .rev-ava） */
.rv-ava { width: 32px; height: 32px; padding: 2px; border-radius: 50%; background: linear-gradient(135deg, var(--rose), var(--plum)); flex: none; }
.rv-ava span { width: 100%; height: 100%; border-radius: 50%; background: var(--plum); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
.rv-clear { border: none; background: none; padding: 0; color: var(--plum); text-decoration: underline; font-size: 14px; font-weight: 600; cursor: pointer; }
.rv-clear:hover { opacity: .75; }
.dist-row { display: flex; align-items: center; gap: 8px; width: 100%; font-size: 12px; color: var(--gray); margin-bottom: 4px; padding: 3px 6px; border: none; background: none; border-radius: 8px; cursor: pointer; transition: background .15s, opacity .15s; }
.dist-row:hover { background: var(--rose-pale); color: var(--plum); }
.dist-row.on { background: var(--rose-pale); color: var(--plum); font-weight: 700; box-shadow: inset 3px 0 0 var(--plum); }
/* 星级筛选态：非选中行降透明度弱化 */
.dist-row.dim { opacity: .45; }
.dist-n { flex: none; min-width: 22px; text-align: right; font-variant-numeric: tabular-nums; font-size: 11px; }
.save-pill { background: var(--coral); color: #fff; font-size: 11px; font-weight: 700; letter-spacing: .5px; padding: 3px 10px; border-radius: 999px; white-space: nowrap; }
/* 价格行 375px 防溢出：允许换行，SKU 独立成行（≤480px） */
.pdp-price-row { flex-wrap: wrap; }
.pdp-sku { white-space: nowrap; }
@media (max-width: 480px) { .pdp-sku { flex-basis: 100%; } }
.tick-enter-active { animation: popTick .3s ease-out; }
.lb-overlay { position: fixed; inset: 0; z-index: 320; background: rgba(31,27,30,.82); display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px 20px; animation: popIn .2s ease-out; }
.lb-overlay img { max-width: min(88vw, 720px); max-height: 78vh; border-radius: 14px; object-fit: contain; box-shadow: var(--shadow-pop); }
.lb-x { position: absolute; top: 18px; right: 22px; width: 40px; height: 40px; border-radius: 50%; background: rgba(255,255,255,.14); color: #fff; font-size: 24px; }
.lb-x:hover { background: rgba(255,255,255,.28); }
.lb-cap { margin-top: 14px; color: rgba(255,255,255,.85); font-size: 13px; }
.sk-block { border-radius: 18px; }
.sk-line { border-radius: 8px; }
@media (max-width: 900px) {
  .pdp-grid { grid-template-columns: 1fr; gap: 28px; }
}

/* ===== v16 移动端深化 ===== */
/* 图廊滑轨：桌面仅显示 .on 单图（display 切换，与改造前单 <img> 渲染一致） */
.pdp-slide { display: none; height: 100%; }
.pdp-slide.on { display: block; }
/* 到货通知行：桌面复现原 inline 尺寸（40px/13px） */
.pdp-notify { height: 40px; font-size: 13px; }
.pdp-notify-btn { height: 40px; padding: 0 16px; font-size: 13px; flex: none; }
/* 粘性加购栏：桌面隐藏 */
.pdp-buybar { display: none; }

@media (max-width: 768px) {
  /* 图廊横滑：scroll-snap 逐张吸附（无依赖）；徽标/放大钮在滑轨外层不随滚动 */
  .pdp-main { display: flex; overflow-x: auto; scroll-snap-type: x mandatory; scrollbar-width: none; -ms-overflow-style: none; -webkit-overflow-scrolling: touch; }
  .pdp-main::-webkit-scrollbar { display: none; }
  .pdp-slide { display: block; flex: 0 0 100%; scroll-snap-align: center; }
  .pdp-thumbs { scroll-snap-type: x proximity; -webkit-overflow-scrolling: touch; }
  .pdp-thumb { scroll-snap-align: start; }
  /* 触摸区：规格钮 ≥44px 高、数量器步进钮 44×44、缩放钮 44 */
  .vbtn { min-height: 44px; min-width: 44px; }
  .qbtn { width: 44px; height: 44px; }
  .pdp-qty-input { font-size: 16px; }
  .pdp-zoom { width: 44px; height: 44px; }
  /* 到货通知：44px 触摸标准 + 16px 防 iOS 聚焦缩放 */
  .pdp-notify { height: 44px; font-size: 16px; }
  .pdp-notify-btn { height: 44px; }
  /* 粘性加购栏：fixed 叠于 tabbar（62px + 安全区）之上，z 低于 tabbar(150)/chat(160) */
  .pdp-buybar {
    position: fixed; left: 0; right: 0; bottom: calc(62px + env(safe-area-inset-bottom, 0px));
    z-index: 140; display: flex; align-items: center; gap: 12px;
    padding: 10px 16px; background: rgba(255,255,255,.96);
    backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
    border-top: 1px solid var(--gray-light); box-shadow: 0 -6px 24px rgba(31,27,30,.08);
  }
  .pdp-buybar-info { flex: 1; min-width: 0; display: flex; align-items: baseline; gap: 8px; }
  .pdp-buybar-price { font-size: 20px; font-weight: 800; color: var(--plum); font-variant-numeric: tabular-nums; }
  .pdp-buybar-info s { color: var(--gray); font-size: 12.5px; }
  .pdp-buybar-title { font-size: 12.5px; color: var(--gray); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pdp-buybar .btn { height: 46px; padding: 0 22px; flex: none; }
  /* 让位：tabbar(62+safe) + 加购栏(约 67px) */
  .pdp-page { padding-bottom: calc(129px + env(safe-area-inset-bottom, 0px)); }
}
</style>
