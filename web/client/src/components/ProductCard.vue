<script setup>
/* 商品卡（旧 pcard 结构 · API 卡片与本地演示卡片共用） */
import { computed } from 'vue'
import { i18n } from '../i18n'
import { catalogById } from '../data/catalog'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'

const props = defineProps({
  p: { type: Object, required: true },   /* API 卡片：{id,slug,title,price_min,compare_at_price,hero_image,...} */
})

const cart = useCartStore()
const ui = useUiStore()

const href = computed(() => `/product?id=${props.p.id}`)
const local = computed(() => catalogById(props.p.id))
const title = computed(() => (i18n.lang === 'zh' && local.value && local.value.titleZh) || props.p.title)
const price = computed(() => ((props.p.price_min ?? props.p.price ?? 0) / 100).toFixed(2))
const compare = computed(() =>
  props.p.compare_at_price ? (props.p.compare_at_price / 100).toFixed(2) : '')
const off = computed(() =>
  props.p.compare_at_price && props.p.compare_at_price > (props.p.price_min ?? props.p.price)
    ? Math.round((1 - (props.p.price_min ?? props.p.price) / props.p.compare_at_price) * 100)
    : 0)
const hoverImg = computed(() => {
  const imgs = props.p.images || []
  return imgs[1] || 'https://placehold.co/400x400/E8B4B8/552338?text=%E2%9C%A8'
})
const lowStock = computed(() => {
  const s = props.p.stock_summary
  return s && s.total > 0 && s.low > 0 && s.total <= 10 ? s.total : null
})

async function quickAdd() {
  await cart.addByProductId(props.p.id, 1, ui)
}
</script>

<template>
  <div class="pcard">
    <div class="pcard-img">
      <span v-if="p.is_new" class="badge badge-new">NEW</span>
      <span v-else-if="p.is_best_seller" class="badge badge-best">BEST</span>
      <router-link :to="href"><img class="img-main" :src="p.hero_image" :alt="p.title" loading="lazy"></router-link>
      <router-link :to="href"><img class="img-hover" :src="hoverImg" :alt="p.title + ' styled'" loading="lazy"></router-link>
      <span class="pcard-quick" role="button" tabindex="0" @click="quickAdd" @keydown.enter="quickAdd">+ Quick Add</span>
    </div>
    <div class="pcard-info">
      <div class="pcard-title"><router-link :to="href">{{ title }}</router-link></div>
      <div class="pcard-price">${{ price }} <span v-if="compare" class="compare">${{ compare }}</span>
        <span v-if="off" class="off">-{{ off }}%</span></div>
      <div v-if="lowStock" class="pcard-stock">⚡ Only {{ lowStock }} left</div>
      <div class="stars">★★★★★ <span class="cnt">({{ (p.rating_count || 0).toLocaleString() }})</span></div>
    </div>
  </div>
</template>
