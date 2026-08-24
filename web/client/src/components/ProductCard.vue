<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { i18n } from '../i18n'
import { productDetail, wishlistAdd, wishlistHas, wishlistRemove } from '../api/client'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  p: { type: Object, required: true },   /* API 卡片：{id,slug,title,price_min,compare_at_price,hero_image,...} */
})

const cart = useCartStore()
const ui = useUiStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const PLACEHOLDER = 'https://placehold.co/400x400/E8B4B8/552338?text=%E2%9C%A8'

const href = computed(() => `/product?id=${props.p.id}`)
const zh = computed(() => i18n.lang === 'zh')
/* 统一展示 p.title：zh 列表/详情由服务端 locale 返回翻译，不再按 id 耦合种子译名 */
const title = computed(() => props.p.title)
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
/* 价格行 SAVE 胶囊（图片上已保留 -x% 徽标，行内不再重复百分比） */
const saveAmt = computed(() =>
  props.p.compare_at_price && props.p.compare_at_price > minCents.value
    ? ((props.p.compare_at_price - minCents.value) / 100).toFixed(2) : '')
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
/* 有均分无评价数：仅显示星级行（不误标 New arrival） */
const ratingSoloLabel = computed(() => zh.value
  ? `评分 ${(props.p.rating || 0).toFixed(1)}`
  : `Rated ${(props.p.rating || 0).toFixed(1)}`)
const soldLabel = computed(() => {
  const n = props.p.sold_count || 0
  if (n < 100) return null
  return n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : String(n)
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

/* 心愿单快捷钮：未登录跳登录（带回跳）；登录走 API toggle + gm_wl_count + 角标广播（对齐 ProductView） */
const wlDone = ref(false)
const wlBusy = ref(false)
if (auth.isLoggedIn) {
  wishlistHas(props.p.id).then((hit) => { wlDone.value = hit }).catch(() => { /* 静默 */ })
}
function bumpWl(d) {
  try {
    const n = Math.max(0, (parseInt(localStorage.getItem('gm_wl_count'), 10) || 0) + d)
    localStorage.setItem('gm_wl_count', String(n))
  } catch (_) { /* 隐私模式 */ }
  window.dispatchEvent(new CustomEvent('gm:wl-changed'))
}
async function toggleWishlist() {
  if (wlBusy.value) return
  if (!auth.isLoggedIn) {
    router.push('/login?next=' + encodeURIComponent(route.fullPath))
    return
  }
  wlBusy.value = true
  try {
    if (wlDone.value) {
      await wishlistRemove(props.p.id)
      wlDone.value = false
      bumpWl(-1)
      ui.toast(zh.value ? '已从心愿单移除' : 'Removed from wishlist', 'success')
    } else {
      await wishlistAdd(props.p.id)
      wlDone.value = true
      bumpWl(1)
      ui.toast(zh.value ? '已加入心愿单 ♥' : 'Added to wishlist ♥', 'success')
    }
  } catch (e) {
    if (!wlDone.value && e && e.status === 409) { wlDone.value = true }
    else ui.toast(zh.value ? '操作失败，请重试' : 'Could not update wishlist — try again', 'error')
  } finally { wlBusy.value = false }
}
</script>

<template>
  <div class="pcard" :class="{ 'pcard-sold': soldOut }">
    <div class="pcard-img">
      <span v-if="p.is_new" class="badge badge-new">NEW</span>
      <span v-else-if="p.is_best_seller" class="badge badge-best">BEST</span>
      <span v-if="off" class="badge badge-sale" style="left:auto;right:48px">-{{ off }}%</span>
      <button
        type="button" class="pcard-wl" :class="{ active: wlDone }" :disabled="wlBusy"
        :aria-label="wlDone ? (zh ? '移出心愿单' : 'Remove from wishlist') : (zh ? '加入心愿单' : 'Add to wishlist')"
        :title="wlDone ? (zh ? '移出心愿单' : 'Remove from wishlist') : (zh ? '加入心愿单' : 'Add to wishlist')"
        @click.stop.prevent="toggleWishlist"
      ><span aria-hidden="true">{{ wlDone ? '♥' : '♡' }}</span></button>
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
        <span v-if="saveAmt" class="save-pill">{{ zh ? '省' : 'SAVE' }} ${{ saveAmt }}</span></div>
      <div v-if="lowStock && !soldOut" class="pcard-stock">⚡ {{ zh ? `仅剩 ${lowStock} 件` : `Only ${lowStock} left` }}</div>
      <div v-if="ratingCount" class="stars" role="img" :aria-label="ratingLabel">
        <span aria-hidden="true">{{ '★'.repeat(filledStars) }}<span class="off">{{ '★'.repeat(5 - filledStars) }}</span></span>
        <span class="cnt" aria-hidden="true">({{ ratingCount.toLocaleString() }})</span>
      </div>
      <div v-else-if="filledStars" class="stars" role="img" :aria-label="ratingSoloLabel">
        <span aria-hidden="true">{{ '★'.repeat(filledStars) }}<span class="off">{{ '★'.repeat(5 - filledStars) }}</span></span>
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
/* 价格行 SAVE 金额胶囊（折扣百分比已在图片徽标展示，此处去重） */
.pcard-price .save-pill { background: var(--plum); color: #fff; border-radius: 999px; padding: 2px 9px; font-size: 10.5px; font-weight: 800; letter-spacing: .3px; margin-left: 4px; }
.pcard-newline { font-size: 12px; color: var(--gray); margin-top: 2px; }
.pcard-soldcount { font-size: 12px; color: var(--gray); margin-top: 2px; }
/* 心愿单快捷钮：右上角悬浮（z 高于卡片链接，click.stop 不触发跳转） */
.pcard-wl {
  position: absolute; top: 10px; right: 10px; z-index: 3;
  width: 34px; height: 34px; border-radius: 50%; border: none;
  background: rgba(255,255,255,.92); color: var(--plum);
  font-size: 17px; line-height: 1; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 2px 8px rgba(31,27,30,.18);
  transition: transform .15s ease-out, color .15s, background .15s;
}
.pcard-wl:hover:not(:disabled) { background: #fff; transform: scale(1.1); }
.pcard-wl.active { color: var(--rose); }
.pcard-wl:disabled { opacity: .6; cursor: wait; }
/* 整卡链接/快速加购的键盘焦点环：实色描边，图片上依然清晰（全局 rgba 半透明环的加强） */
.pcard a:focus-visible { outline: 2px solid var(--plum); outline-offset: 2px; border-radius: 4px; }
/* 快速加购为 hover 悬浮显现——键盘聚焦时也须可见（触屏 hover:none 下全局已是常显，此处兼容） */
.pcard-quick:focus-visible { opacity: 1; transform: none; background: var(--plum); color: #fff; }
.pcard-quick:disabled { opacity: .6; cursor: wait; }
@media (hover: none) {
  .pcard-quick { opacity: 1; transform: none; }
}
</style>
