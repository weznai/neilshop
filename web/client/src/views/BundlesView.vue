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
const busy = ref({})

onMounted(async () => {
  try { items.value = (await req('GET', '/api/catalog/products?size=9&sort=best&category=press-on-nails')).items || [] }
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

/* 加购失败单项提示（详情拉取失败 / 无有货规格 / POST 失败统一走此文案风格） */
function failToast(title) {
  ui.toast(zh() ? `「${title}」加购失败，请稍后再试` : `Could not add ${title} — try again later`, 'error')
}

async function addBundle(b) {
  if (b.soldOut || busy.value[b.name]) return
  busy.value = { ...busy.value, [b.name]: true }
  /* 三个商品详情并行请求（allSettled：单品失败不影响其余） */
  const details = await Promise.allSettled(b.sets.map((s) => req('GET', '/api/catalog/products-by-id/' + s.id)))
  const picks = []
  details.forEach((r, i) => {
    if (r.status !== 'fulfilled') { failToast(b.sets[i].title); return }
    const v = (r.value.variants || []).find((x) => x.stock > 0)
    if (v) picks.push({ title: b.sets[i].title, v })
    else failToast(b.sets[i].title)
  })
  /* 加购并行（allSettled），单项失败单独提示 */
  const adds = await Promise.allSettled(picks.map((x) => req('POST', '/api/cart/items', { variant_id: x.v.id, qty: 1 })))
  let ok = 0
  adds.forEach((r, i) => {
    if (r.status === 'fulfilled') ok++
    else failToast(picks[i].title)
  })
  await cart.refresh().catch(() => {})
  busy.value = { ...busy.value, [b.name]: false }
  if (ok) {
    ui.toast(
      zh()
        ? `已加 ${ok} 件 — 已自动选择首个有货规格，可在购物车调整；折扣自动生效 🎁`
        : `Added ${ok} sets — first in-stock size auto-selected (adjust in cart), discount auto-applied 🎁`,
      'success',
    )
    ui.openCart()
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
            <div style="display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin:8px 0 14px">
              <b style="font-size:20px;color:var(--plum);font-variant-numeric:tabular-nums">${{ b.pay.toFixed(2) }}</b>
              <span style="color:var(--gray);text-decoration:line-through;font-size:13px">${{ b.total.toFixed(2) }}</span>
              <span class="save-pill">{{ zh() ? '省' : 'SAVE' }} ${{ b.save.toFixed(2) }}</span>
            </div>
            <button class="btn btn-primary btn-block" :disabled="b.soldOut || busy[b.name]" :class="{ loading: busy[b.name] }" @click="addBundle(b)">
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
/* 商品图层叠扇形：双图旋转错位 + 白边投影，仿拍立得叠放 */
.bundle-imgs { position: relative; height: 230px; background: linear-gradient(180deg, var(--rose-pale), #fff); overflow: hidden; }
.bundle-imgs img { position: absolute; top: 34px; width: 56%; aspect-ratio: 1; object-fit: cover; border-radius: 14px; border: 5px solid #fff; box-shadow: 0 10px 24px rgba(31,27,30,.2); background: #fff; }
.bundle-imgs img:nth-of-type(1) { left: 6%; transform: rotate(-4deg); z-index: 1; }
.bundle-imgs img:nth-of-type(2) { right: 6%; top: 44px; transform: rotate(4deg); z-index: 2; }
.bundle-off { position: absolute; top: 10px; right: 10px; background: var(--coral); color: #fff; font-size: 12px; font-weight: 800; padding: 4px 10px; border-radius: 999px; box-shadow: 0 2px 8px rgba(31,27,30,.25); z-index: 3; }
/* save 金额徽章化 */
.save-pill { background: var(--plum); color: #fff; border-radius: 999px; padding: 3px 10px; font-size: 11.5px; font-weight: 800; letter-spacing: .3px; }
</style>
