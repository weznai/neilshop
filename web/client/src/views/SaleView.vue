<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../api/client'
import { i18n } from '../i18n'
import ProductCard from '../components/ProductCard.vue'

const items = ref([])
const loaded = ref(false)
const loadErr = ref(false)
const zh = () => i18n.lang === 'zh'

/* 后端已支持 on_sale 筛选（compare_at_price > price_min）；
 * 促销来源 = on_sale=1 ∪ tag=sale（运营打标但未设划线价的商品），按折扣力度排序 */
async function load() {
  loaded.value = false
  loadErr.value = false
  const isDeal = (p) => p.compare_at_price && p.compare_at_price > (p.price_min ?? p.price ?? 0)
  const offPct = (p) => (isDeal(p) ? 1 - (p.price_min ?? p.price) / p.compare_at_price : 0)
  const locale = i18n.lang === 'zh' ? '&locale=zh-CN' : ''
  try {
    const [onSale, tagged] = await Promise.all([
      req('GET', '/api/catalog/products?on_sale=1&size=100' + locale).catch(() => null),
      req('GET', '/api/catalog/products?tag=sale&size=100' + locale).catch(() => null),
    ])
    if (!onSale && !tagged) throw new Error('load failed') /* 两路全失败 → 错误态（区别于无促销品） */
    const map = new Map()
    for (const p of ((onSale && onSale.items) || [])) map.set(p.id, p)
    for (const p of ((tagged && tagged.items) || [])) if (!map.has(p.id)) map.set(p.id, p)
    items.value = [...map.values()].sort((a, b) => offPct(b) - offPct(a))
  } catch (_) {
    items.value = []
    loadErr.value = true
  }
  loaded.value = true
}
onMounted(load)

/* 头图折扣宣称按真实数据计算：划线价 > 现价的最大折扣百分比（向下取整） */
const maxOff = computed(() => {
  let m = 0
  for (const p of items.value) {
    const price = p.price_min ?? p.price ?? 0
    if (p.compare_at_price && p.compare_at_price > price) m = Math.max(m, 1 - price / p.compare_at_price)
  }
  return Math.floor(m * 100)
})
</script>

<template>
  <section class="section">
    <div class="container">
      <div class="sale-hero">
        <div style="font-size:46px">🔥</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:6px">
          {{ zh() ? '季末大促' : 'End of Season Sale' }}
        </h1>
        <p style="color:var(--gray)">
          {{
            maxOff
              ? (zh() ? `低至 ${100 - maxOff} 折 — 无需折扣码，售完即止。` : `Up to ${maxOff}% off — no code needed. While stocks last.`)
              : (zh() ? '限时精选好物 — 无需折扣码，售完即止。' : 'Limited-time picks — no code needed. While stocks last.')
          }}
        </p>
      </div>
      <div class="grid grid-4">
        <template v-if="!loaded">
          <div v-for="i in 4" :key="'sk' + i" class="sale-sk">
            <div class="sale-sk-img"></div>
            <div class="sale-sk-line" style="width:70%"></div>
            <div class="sale-sk-line" style="width:40%"></div>
          </div>
        </template>
        <ProductCard v-for="p in items" :key="p.id" :p="p" />
      </div>
      <div v-if="loaded && loadErr" style="text-align:center;color:var(--gray);padding:40px 0">
        <div style="font-size:44px;margin-bottom:10px">⚠️</div>
        {{ zh() ? '促销商品加载失败，请稍后重试' : 'Failed to load sale items — please retry' }}
        <div style="margin-top:14px"><button class="btn btn-secondary" @click="load">⟳ {{ zh() ? '重试' : 'Retry' }}</button></div>
      </div>
      <div v-else-if="loaded && !items.length" style="text-align:center;color:var(--gray);padding:40px 0">
        <div style="font-size:44px;margin-bottom:10px">💅</div>
        {{ zh() ? '促销补货中，先去逛逛新品' : 'Sale restocking — check back soon' }} ·
        <router-link to="/store?sort=new" style="color:var(--plum)">{{ zh() ? '新品专区' : 'New arrivals' }}</router-link>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sale-hero{ text-align:center; margin: 6px 0 30px; padding: 26px 16px; border-radius: 18px; background: linear-gradient(135deg, var(--rose-pale), #fff 70%); border: 1px solid var(--rose-light); }
.sale-sk{ border-radius: 12px; }
.sale-sk-img{ aspect-ratio: 1; border-radius: 12px; }
.sale-sk-img, .sale-sk-line{ background: linear-gradient(100deg, var(--gray-light) 40%, #f7f3f5 50%, var(--gray-light) 60%); background-size: 200% 100%; animation: saleSk 1.2s infinite; }
.sale-sk-line{ height: 14px; border-radius: 7px; margin-top: 10px; }
@keyframes saleSk{ to{ background-position: -200% 0; } }
</style>
