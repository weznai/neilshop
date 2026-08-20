<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../api/client'
import { i18n } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'

const cart = useCartStore()
const ui = useUiStore()
const zh = () => i18n.lang === 'zh'

/* 捆绑折扣比例由服务端结算时按 settings bundle_2_off/15%、bundle_3_off/20% 计算（无公开配置端点），
 * 页面按同一口径展示，实际以购物车/结算为准 */
const items = ref([])
const loaded = ref(false)
const busy = ref(0)

onMounted(async () => {
  try { items.value = (await req('GET', '/api/catalog/products?size=9&sort=best')).items || [] }
  catch (_) { items.value = [] }
  loaded.value = true
})

const bundles = computed(() => {
  const p = items.value
  if (!p.length) return []
  const take = (start, n) => p.slice(start, start + n)
  const defs = [
    { name: 'Date Night Duo', nameZh: '约会双人组', sets: take(0, 2), off: 15 },
    { name: 'Everyday Trio', nameZh: '日常三件套', sets: take(2, 3), off: 20 },
    { name: 'Full Glam Set', nameZh: '全妆礼盒', sets: take(5, 3), off: 20 },
  ]
  return defs.filter((b) => b.sets.length === (b.off === 15 ? 2 : 3))
    .map((b) => {
      const total = b.sets.reduce((n, s) => n + (s.price_min ?? 0), 0) / 100
      return {
        ...b,
        total,
        pay: total * (1 - b.off / 100),
        save: total * b.off / 100,
        soldOut: b.sets.some((s) => s.stock_summary && s.stock_summary.out),
        img: (b.sets[0] && b.sets[0].hero_image) || '',
        img2: (b.sets[1] && b.sets[1].hero_image) || '',
      }
    })
})

async function addBundle(b) {
  if (b.soldOut || busy.value) return
  busy.value = 1
  /* 三个商品详情并行请求（allSettled：单品失败不影响其余） */
  const results = await Promise.allSettled(b.sets.map((s) => req('GET', '/api/catalog/products-by-id/' + s.id)))
  let ok = 0
  for (const r of results) {
    if (r.status !== 'fulfilled') continue
    const v = (r.value.variants || []).find((x) => x.stock > 0)
    if (!v) continue
    try { await req('POST', '/api/cart/items', { variant_id: v.id, qty: 1 }); ok++ } catch (_) { /* 单品失败继续 */ }
  }
  await cart.refresh().catch(() => {})
  busy.value = 0
  if (ok) {
    ui.toast(
      zh()
        ? `已加 ${ok} 件 — 已自动选择首个有货规格，可在购物车调整；折扣自动生效 🎁`
        : `Added ${ok} sets — first in-stock size auto-selected (adjust in cart), discount auto-applied 🎁`,
      'success',
    )
    ui.openCart()
  } else {
    ui.toast(zh() ? '加购失败，请稍后再试' : 'Could not add bundle, try again', 'error')
  }
}
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:40px;margin-bottom:4px">🎁</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">{{ zh() ? '组合优惠' : 'Bundles & Save' }}</h1>
        <p style="color:var(--gray)">
          {{ zh() ? '任意 2 件穿戴甲自动 85 折 / 任意 3 件自动 8 折 —— 购物车自动计算，无需折扣码。' : 'Any 2 press-on sets auto-get 15% off · any 3+ auto-get 20% off — calculated automatically in your cart, no code needed.' }}
        </p>
      </div>
      <div class="grid grid-3">
        <div v-for="b in bundles" :key="b.name" class="card bundle-card" :class="{ sold: b.soldOut }" style="padding:0;overflow:hidden">
          <div class="bundle-imgs">
            <img v-if="b.img" :src="b.img" :alt="b.name + ' 1'" loading="lazy">
            <img v-if="b.img2" :src="b.img2" :alt="b.name + ' 2'" loading="lazy">
            <span class="bundle-off">-{{ b.off }}%</span>
          </div>
          <div style="padding:18px">
            <b style="font-family:var(--font-title);font-size:18px">{{ zh() ? b.nameZh : b.name }}</b>
            <div style="font-size:13px;color:var(--gray);margin:6px 0 4px">
              <span v-for="(s, i) in b.sets" :key="s.id"><template v-if="i"> · </template>{{ s.title }}</span>
            </div>
            <div style="display:flex;align-items:baseline;gap:10px;margin:8px 0 14px">
              <b style="font-size:20px;color:var(--plum);font-variant-numeric:tabular-nums">${{ b.pay.toFixed(2) }}</b>
              <span style="color:var(--gray);text-decoration:line-through;font-size:13px">${{ b.total.toFixed(2) }}</span>
              <span style="color:var(--coral);font-weight:700;font-size:13px">{{ zh() ? '省' : 'save' }} ${{ b.save.toFixed(2) }}</span>
            </div>
            <button class="btn btn-primary btn-block" :disabled="b.soldOut || busy" @click="addBundle(b)">
              {{ b.soldOut ? (zh() ? '含售罄商品' : 'Contains sold-out set') : (zh() ? '整组加购' : 'Add bundle to cart') }}
            </button>
          </div>
        </div>
      </div>
      <div v-if="loaded && !bundles.length" style="text-align:center;color:var(--gray);padding:40px 0">
        <div style="font-size:44px;margin-bottom:10px">🎁</div>
        {{ zh() ? '组套整理中 — 单买 2 件同样享 85 折' : 'Bundles restocking — any 2 sets still get 15% off in cart' }} ·
        <router-link to="/store" style="color:var(--plum)">{{ zh() ? '去逛全场' : 'Shop all' }}</router-link>
      </div>
    </div>
  </section>
</template>

<style scoped>
.bundle-card.sold { opacity: .68; }
.bundle-imgs { position: relative; display: grid; grid-template-columns: 1fr 1fr; height: 200px; background: var(--rose-pale); }
.bundle-imgs img { width: 100%; height: 100%; object-fit: cover; }
.bundle-off { position: absolute; top: 10px; right: 10px; background: var(--coral); color: #fff; font-size: 12px; font-weight: 800; padding: 4px 10px; border-radius: 999px; box-shadow: 0 2px 8px rgba(31,27,30,.25); }
</style>
