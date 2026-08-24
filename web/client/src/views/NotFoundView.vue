<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'
import { useUiStore } from '../stores/ui'
import { i18n, tt } from '../i18n'
import ProductCard from '../components/ProductCard.vue'

const ui = useUiStore()
const hot = ref([])
const SUGGEST = [
  ['Best sellers', '热卖爆款', '/store?sort=best'],
  ['New arrivals', '新品上架', '/store?sort=new'],
  ['Sale', '限时特惠', '/sale'],
  ['FAQ', '常见问题', '/faq'],
  ['Size guide', '尺码指南', '/size-guide'],
  ['Contact us', '联系我们', '/contact'],
  ['Track order', '订单查询', '/track'],
]
/* /api/ai/hot 模块级 30s 缓存（对齐 api/client.js productDetail 缓存模式；rejected promise 不滞留） */
let _hotCache = { at: 0, promise: null }
function fetchHot() {
  if (_hotCache.promise && Date.now() - _hotCache.at < 30000) return _hotCache.promise
  const rec = { at: Infinity, promise: null }
  rec.promise = req('GET', '/api/ai/hot?size=4')
    .then((d) => { rec.at = Date.now(); return d })
    .catch((e) => { if (_hotCache === rec) _hotCache = { at: 0, promise: null }; throw e })
  _hotCache = rec
  return rec.promise
}
onMounted(async () => {
  try {
    const d = await fetchHot()
    hot.value = (d.items || []).slice(0, 4)
  } catch (_) { hot.value = [] }
})
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:1000px">
      <div style="max-width:760px;margin:0 auto;text-align:center">
        <div class="b44" style="font-family:var(--font-title);font-size:76px;font-weight:700;letter-spacing:2px">
          <span>4</span><span>0</span><span>4</span>
        </div>
        <h1 style="font-family:var(--font-title);font-size:28px;margin:8px 0 4px">
          {{ tt('Page not found — but your perfect set is 💅', '页面走丢了 — 但你的本命美甲就在附近 💅') }}
        </h1>
        <p style="color:var(--gray);font-size:14px;margin-bottom:22px">
          {{ tt("This page had a chip moment. Let's get you back to the glam.", '这个页面崩了个甲片，马上带你回到主场。') }}
        </p>
        <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-bottom:26px">
          <router-link to="/" class="btn btn-primary">{{ tt('Back to home', '回到首页') }}</router-link>
          <button class="btn btn-secondary" @click="ui.openSearch()">🔍 {{ tt('Search the store', '搜索商店') }}</button>
        </div>
        <div style="display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-bottom:34px">
          <router-link v-for="[en, zh, href] in SUGGEST" :key="href" :to="href" class="trend-chip">{{ tt(en, zh) }}</router-link>
        </div>
      </div>

      <template v-if="hot.length">
        <h3 style="font-family:var(--font-title);font-size:19px;margin-bottom:16px;text-align:center">{{ tt('Hot right now', '正在热卖') }}</h3>
        <div class="grid grid-4" style="gap:14px">
          <ProductCard v-for="p in hot" :key="p.id" :p="p" />
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.b44 span{display:inline-block;animation:bounceIn .7s cubic-bezier(.34,1.56,.64,1) both}
.b44 span:nth-child(1){color:var(--rose);animation-delay:0s}
.b44 span:nth-child(2){color:var(--plum);animation-delay:.1s}
.b44 span:nth-child(3){color:var(--coral);animation-delay:.2s}
@keyframes bounceIn{
  0%{transform:translateY(-56px) scale(.55);opacity:0}
  60%{transform:translateY(10px) scale(1.06);opacity:1}
  80%{transform:translateY(-5px) scale(1)}
  100%{transform:translateY(0) scale(1)}
}
@media (prefers-reduced-motion: reduce){.b44 span{animation:none}}
</style>
