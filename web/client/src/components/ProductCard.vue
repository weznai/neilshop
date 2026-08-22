<script setup>
import { computed, ref } from 'vue'
import { i18n } from '../i18n'
import { catalogById } from '../data/catalog'
import { productDetail } from '../api/client'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'

const props = defineProps({
  p: { type: Object, required: true },   /* API 卡片：{id,slug,title,price_min,compare_at_price,hero_image,...} */
})

const cart = useCartStore()
const ui = useUiStore()

const PLACEHOLDER = 'https://placehold.co/400x400/E8B4B8/552338?text=%E2%9C%A8'

const href = computed(() => `/product?id=${props.p.id}`)
const local = computed(() => catalogById(props.p.id))
const zh = computed(() => i18n.lang === 'zh')
const title = computed(() => (zh.value && local.value && local.value.titleZh) || props.p.title)
const minCents = computed(() => props.p.price_min ?? props.p.price ?? 0)
const price = computed(() => (minCents.value / 100).toFixed(2))
const hasRange = computed(() => (props.p.price_max ?? 0) > minCents.value)
const compare = computed(() =>
  props.p.compare_at_price && props.p.compare_at_price > minCents.value
    ? (props.p.compare_at_price / 100).toFixed(2) : '')
const off = computed(() =>
  props.p.compare_at_price && props.p.compare_at_price > minCents.value
    ? Math.round((1 - minCents.value / props.p.compare_at_price) * 100)
    : 0)
/* hover 副图缺省回落主图（不再跳占位图；无 images[1] 时与主图同图，hover 无感切换） */
const hoverImg = computed(() => (props.p.images || [])[1] || props.p.hero_image)
const soldOut = computed(() => !!(props.p.stock_summary && props.p.stock_summary.out))
const lowStock = computed(() => {
  const s = props.p.stock_summary
  return s && s.total > 0 && s.low > 0 && s.total <= 10 ? s.total : null
})
const ratingCount = computed(() => props.p.rating_count || 0)
const filledStars = computed(() => Math.max(0, Math.min(5, Math.round(props.p.rating || 0))))
const ratingLabel = computed(() => zh.value
  ? `评分 ${(props.p.rating || 0).toFixed(1)}，共 ${ratingCount.value.toLocaleString()} 条评价`
  : `Rated ${(props.p.rating || 0).toFixed(1)} from ${ratingCount.value.toLocaleString()} reviews`)
const soldLabel = computed(() => {
  const n = props.p.sold_count || 0
  return n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : null
})

/* 兜底占位：dataset 守卫防循环（对齐 HomeView heroFallback / ProductView imgFallback） */
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = PLACEHOLDER
}

const busy = ref(false)
async function quickAdd() {
  if (soldOut.value || busy.value) return
  busy.value = true
  try {
    const d = await productDetail(props.p.id)
    const v = (d.variants || []).find((x) => x.stock > 0)
    if (!v) {
      ui.toast(zh.value ? '该商品已售罄' : 'Sold out', 'error')
      return
    }
    const label = [v.option1_value, v.option2_value].filter(Boolean).join(' · ')
    const ok = await cart.add(v.id, 1, label ? { ...ui, toast: (m, t) => { if (t !== 'success') ui.toast(m, t) } } : ui)
    if (ok && label) ui.toast(zh.value ? `已加入 ${label}` : `Added ${label}`, 'success')
  } catch (_) {
    ui.toast(zh.value ? '加购失败，请稍后再试' : 'Could not add, try again', 'error')
  } finally { busy.value = false }
}
</script>

<template>
  <div class="pcard" :class="{ 'pcard-sold': soldOut }">
    <div class="pcard-img">
      <span v-if="p.is_new" class="badge badge-new">NEW</span>
      <span v-else-if="p.is_best_seller" class="badge badge-best">BEST</span>
      <span v-if="off" class="badge badge-sale" style="left:auto;right:10px">-{{ off }}%</span>
      <router-link :to="href"><img class="img-main" :src="p.hero_image" :alt="title" loading="lazy" @error="imgFallback"></router-link>
      <router-link :to="href"><img class="img-hover" :src="hoverImg" :alt="title + (zh ? ' 效果图' : ' styled')" loading="lazy" @error="imgFallback"></router-link>
      <button
        v-if="!soldOut" type="button" class="pcard-quick" :disabled="busy"
        :aria-label="zh ? '快速加购' + title : 'Quick add ' + title"
        @click="quickAdd"
      >+ {{ busy ? '…' : (zh ? '快速加购' : 'Quick Add') }}</button>
      <div v-if="soldOut" class="pcard-soldout" aria-disabled="true"><span>{{ zh ? '已售罄' : 'SOLD OUT' }}</span></div>
    </div>
    <div class="pcard-info">
      <div class="pcard-title"><router-link :to="href">{{ title }}</router-link></div>
      <div class="pcard-price">${{ price }}<span v-if="hasRange" class="range">+</span> <span v-if="compare" class="compare">${{ compare }}</span>
        <span v-if="off" class="off">-{{ off }}%</span></div>
      <div v-if="lowStock && !soldOut" class="pcard-stock">⚡ {{ zh ? `仅剩 ${lowStock} 件` : `Only ${lowStock} left` }}</div>
      <div v-if="ratingCount" class="stars" role="img" :aria-label="ratingLabel">
        <span aria-hidden="true">{{ '★'.repeat(filledStars) }}<span class="off">{{ '★'.repeat(5 - filledStars) }}</span></span>
        <span class="cnt" aria-hidden="true">({{ ratingCount.toLocaleString() }})</span>
      </div>
      <div v-else class="pcard-newline">✨ {{ zh ? '新品上架' : 'New arrival' }}</div>
      <div v-if="soldLabel" class="pcard-soldcount">🔥 {{ soldLabel }}+ {{ zh ? '已售' : 'sold' }}</div>
    </div>
  </div>
</template>

<style scoped>
.pcard-sold .pcard-img img { filter: grayscale(.6); }
.pcard-soldout { position: absolute; inset: 0; z-index: 1; background: rgba(251,240,241,.6); backdrop-filter: blur(1.5px); display: flex; align-items: center; justify-content: center; }
.pcard-soldout span { background: rgba(31,27,30,.78); color: #fff; font-size: 11px; font-weight: 700; letter-spacing: 1.2px; padding: 7px 16px; border-radius: 999px; }
.pcard-price .range { color: var(--plum); font-size: 13px; }
.pcard-newline { font-size: 12px; color: var(--gray); margin-top: 2px; }
.pcard-soldcount { font-size: 12px; color: var(--gray); margin-top: 2px; }
/* 整卡链接/快速加购的键盘焦点环：实色描边，图片上依然清晰（全局 rgba 半透明环的加强） */
.pcard a:focus-visible { outline: 2px solid var(--plum); outline-offset: 2px; border-radius: 4px; }
/* 快速加购为 hover 悬浮显现——键盘聚焦时也须可见（触屏 hover:none 下全局已是常显，此处兼容） */
.pcard-quick:focus-visible { opacity: 1; transform: none; background: var(--plum); color: #fff; }
.pcard-quick:disabled { opacity: .6; cursor: wait; }
@media (hover: none) {
  .pcard-quick { opacity: 1; transform: none; }
}
</style>
