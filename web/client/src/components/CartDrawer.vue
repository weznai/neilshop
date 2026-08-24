<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { i18n, tt } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { req } from '../api/client'
import { catalogById } from '../data/catalog'

const cart = useCartStore()
const ui = useUiStore()


const zh = computed(() => i18n.lang === 'zh')
const recs = ref([])
let recSeq = 0

/* 行项图/推荐图兜底：回落 placehold + dataset 守卫防循环 */
const IMG_FALLBACK = 'https://placehold.co/200x200/E8B4B8/552338?text=GLOWMAG'
function imgFallback(e) {
  const img = e.target
  if (img.dataset.fb) return
  img.dataset.fb = '1'
  img.src = IMG_FALLBACK
}

watch(
  () => cart.items.map((i) => i.pid || i.id).join(','),
  async (ids) => {
    const seq = ++recSeq
    try {
      const path = ids
        ? '/api/ai/recommend?cart_ids=' + encodeURIComponent(ids) + '&size=4'
        : '/api/ai/hot?size=4'
      const d = await req('GET', path)
      if (seq !== recSeq) return
      const inCart = new Set(cart.items.map((i) => i.pid || i.id))
      const seen = new Set()
      recs.value = (d.items || [])
        .filter((p) => p && p.id != null && !inCart.has(p.id) && !seen.has(p.id) && seen.add(p.id))
        .slice(0, 4)
    } catch (_) { recs.value = [] }
  },
  { immediate: true },
)

/* 删除撤销条（6s 自动消失） */
const undoTimer = ref(null)
watch(
  () => cart.removed && cart.removed.at,
  () => {
    clearTimeout(undoTimer.value)
    if (cart.removed) undoTimer.value = setTimeout(() => cart.dismissRemoved(), 6000)
  },
)
function undoRemove() {
  clearTimeout(undoTimer.value)
  cart.undoRemove(ui)
}

const subtotalD = computed(() => (cart.subtotalC / 100).toFixed(2))
/* 与 CartView/Checkout 同口径：有下架或缺货商品时禁止去结算 */
const blocked = computed(() => cart.items.some((i) => i.inactive || (i.stock || 0) <= 0 || (i.stock > 0 && i.qty > i.stock)))
/* 免邮门槛（settings 下发，与 CartView/Checkout 同源；失败回落 $35 文案） */
const freeShipC = ref(3500)
req('GET', '/api/checkout/shipping-methods?country=US').then((d) => {
  if (d && d.free_shipping_threshold) freeShipC.value = Number(d.free_shipping_threshold) || 3500
}).catch(() => {})
/* 抽屉不跑 preview，无法按折后口径精确计算免邮进度 → 弱化为静态提示，进度条隐藏（以结算页试算为准） */
const shipHint = computed(() => tt(
  `Free shipping on orders over $${(freeShipC.value / 100).toFixed(0)} (calculated on discounted subtotal, final at checkout)`,
  `满 $${(freeShipC.value / 100).toFixed(0)} 可享免邮（按折后金额计算，以结算页为准）`,
))

/* 去结算携带已验证折扣码（CartView applyCode 成功时写入 gm_applied_code；CheckoutView 支持 ?code=） */
function checkoutLink() {
  let c = ''
  try { c = (localStorage.getItem('gm_applied_code') || '').trim().toUpperCase() } catch (_) { /* 隐私模式 */ }
  return '/checkout' + (c ? `?code=${encodeURIComponent(c)}` : '')
}

function recTitle(p) {
  if (zh.value) {
    const hit = catalogById(p.id)
    if (hit && hit.titleZh) return hit.titleZh
  }
  return p.title
}

/* ===== a11y：dialog 角色 / 焦点管理（开→关闭钮，关→归还触发元素）/ Esc + 简易 focus trap ===== */
const boxEl = ref(null)
const closeEl = ref(null)
let lastActive = null

watch(() => ui.cartDrawer, async (open) => {
  if (open) {
    lastActive = document.activeElement
    await nextTick()
    if (closeEl.value) closeEl.value.focus({ preventScroll: true })
  } else {
    if (lastActive && lastActive !== document.body && document.contains(lastActive)) {
      try { lastActive.focus({ preventScroll: true }) } catch (_) { /* 触发元素已卸载 */ }
    }
    lastActive = null
  }
})

function drawerKeydown(e) {
  if (!ui.cartDrawer) return
  if (e.key === 'Escape') { e.stopPropagation(); ui.closeCart(); return }
  if (e.key === 'Tab') {
    const f = boxEl.value
      ? [...boxEl.value.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
      : []
    if (!f.length) return
    const first = f[0]
    const last = f[f.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }
}
</script>

<template>
  <div class="overlay" :class="{ open: ui.cartDrawer }" @click="ui.closeCart()"></div>
  <aside
    ref="boxEl" class="drawer" :class="{ open: ui.cartDrawer }"
    role="dialog" aria-modal="true" :aria-label="i18n.t('aria.cartDrawer')"
    @keydown="drawerKeydown"
  >
    <div class="drawer-head">
      {{ i18n.t('cart.title') }}
      <button
        ref="closeEl" style="font-size:22px"
        :aria-label="zh ? '关闭购物车' : 'Close cart'"
        @click="ui.closeCart()"
      >×</button>
    </div>
    <div class="drawer-body">
      <div v-if="!cart.items.length" style="text-align:center;padding:48px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:12px">🛒</div>
        <p style="margin-bottom:16px">{{ i18n.t('cart.empty') }}</p>
        <router-link class="btn btn-primary btn-sm" to="/store" @click="ui.closeCart()">{{ i18n.t('cart.shop') }}</router-link>
      </div>
      <template v-else>
        <div v-if="cart.removed" class="undo-bar">
          <span>“{{ cart.removed.title }}” {{ zh ? '已移除' : 'removed' }}</span>
          <button class="undo-btn" @click="undoRemove">{{ zh ? '撤销' : 'Undo' }}</button>
        </div>
        <div
          v-for="i in cart.items" :key="i.id"
          style="display:flex;gap:12px;padding:12px 0;border-bottom:1px solid var(--gray-light)"
        >
          <img :src="i.img || IMG_FALLBACK" style="width:72px;height:72px;border-radius:8px;object-fit:cover" :style="{ opacity: i.inactive ? 0.6 : 1 }" :alt="i.title || ''" loading="lazy" @error="imgFallback">
          <div style="flex:1;min-width:0">
            <div style="font-weight:600;font-size:14px">{{ i.title || tt('Unavailable item', '已失效商品') }}</div>
            <div style="font-size:12px;color:var(--gray)">{{ i.variant }}</div>
            <div v-if="i.inactive" style="font-size:11.5px;color:var(--error);font-weight:600;margin-top:2px">
              {{ zh ? '已下架，请移除' : 'Delisted — please remove' }}
            </div>
            <div v-else-if="i.stock > 0 && i.stock <= 5" style="font-size:11.5px;color:var(--warn);font-weight:600;margin-top:2px">
              {{ zh ? `仅剩 ${i.stock} 件` : `Only ${i.stock} left` }}
            </div>
            <div v-else-if="i.stock <= 0" style="font-size:11.5px;color:var(--error);font-weight:600;margin-top:2px">
              {{ zh ? '库存不足' : 'Out of stock' }}
            </div>
            <div v-if="!i.inactive" style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
              <div style="display:flex;align-items:center;gap:0;border:1px solid var(--gray-light);border-radius:8px">
                <button
                  class="qbtn"
                  :disabled="i.qty <= 1"
                  :aria-label="zh ? `减少数量：${i.title}` : `Decrease quantity of ${i.title}`"
                  @click="cart.setQty(i.vid, i.qty - 1, ui)"
                >−</button>
                <span style="width:32px;text-align:center;font-size:13px;font-weight:600">{{ i.qty }}</span>
                <button
                  class="qbtn" :disabled="(i.stock || 0) <= 0 || (i.stock > 0 && i.qty >= i.stock)"
                  :title="(i.stock || 0) <= 0 ? (zh ? '库存不足' : 'Out of stock') : (i.stock > 0 && i.qty >= i.stock ? (zh ? '库存上限' : 'Max stock') : '')"
                  :aria-label="zh ? `增加数量：${i.title}` : `Increase quantity of ${i.title}`"
                  @click="cart.setQty(i.vid, i.qty + 1, ui)"
                >＋</button>
              </div>
              <div style="font-weight:700;color:var(--plum)">${{ ((i.priceC || i.price * 100) * i.qty / 100).toFixed(2) }}</div>
            </div>
          </div>
          <button
            style="color:var(--gray);font-size:18px;align-self:flex-start"
            :aria-label="zh ? `移除 ${i.title}` : `Remove ${i.title}`"
            @click="cart.remove(i.vid, ui)"
          >×</button>
        </div>
      </template>
    </div>
    <div v-if="cart.items.length" class="drawer-foot">
      <div v-if="recs.length" class="rec-wrap">
        <div class="rec-head">{{ i18n.t('cart.pairs') }}</div>
        <div class="rec-row">
          <div v-for="p in recs" :key="p.id" class="rec-card">
            <img :src="p.hero_image" :alt="p.title" loading="lazy" @error="imgFallback">
            <div class="rec-info">
              <div class="rec-title">{{ recTitle(p) }}</div>
              <div class="rec-price">{{ tt('from', '起') }} ${{ (p.price_min / 100).toFixed(2) }}</div>
            </div>
            <button
              class="rec-add"
              :aria-label="zh ? `加入购物车：${recTitle(p)}` : `Add ${recTitle(p)} to cart`"
              @click="cart.addByProductId(p.id, 1, ui)"
            >⊕</button>
          </div>
        </div>
      </div>
      <div class="ship-bar" style="font-size:12px">{{ shipHint }}</div>
      <div style="display:flex;justify-content:space-between;margin-bottom:12px;font-size:15px">
        <span>{{ i18n.t('cart.subtotal') }}</span>
        <b style="font-variant-numeric:tabular-nums">${{ subtotalD }}</b>
      </div>
      <router-link v-if="!blocked" :to="checkoutLink()" class="btn btn-primary btn-block" @click="ui.closeCart()">
        {{ i18n.t('cart.checkout') }} · {{ tt('Subtotal', '小计') }} ${{ subtotalD }}
      </router-link>
      <button v-else class="btn btn-primary btn-block" disabled>{{ i18n.t('cart.checkout') }}</button>
      <div v-if="blocked" style="font-size:11.5px;color:var(--error);font-weight:600;margin-top:8px;text-align:center">
        {{ tt('Please remove out-of-stock / unavailable items first', '请先移除缺货/下架商品') }}
      </div>
      <div style="text-align:center;margin-top:10px">
        <router-link to="/cart" style="font-size:13px;color:var(--gray);text-decoration:underline" @click="ui.closeCart()">
          {{ i18n.t('cart.view') }}
        </router-link>
      </div>
    </div>
  </aside>
</template>

<style scoped>
/* 关闭态不可聚焦/退出可访问性树：visibility 延迟到滑出动画结束后生效（打开时立即可见） */
.drawer { transition: right .25s ease-out, visibility 0s linear .25s; }
.drawer:not(.open) { visibility: hidden; }
.drawer.open { visibility: visible; transition: right .25s ease-out; }
.qbtn { width: 30px; height: 30px; border: none; background: none; color: var(--plum); font-size: 16px; font-weight: 700; line-height: 1; cursor: pointer; border-radius: 6px; transition: background .15s; }
.qbtn:hover:not(:disabled) { background: var(--rose-pale); }
.qbtn:disabled { opacity: .35; cursor: not-allowed; }
.undo-bar { display: flex; align-items: center; justify-content: space-between; gap: 10px; background: var(--rose-pale); border-radius: 10px; padding: 10px 12px; font-size: 13px; margin-bottom: 10px; }
.undo-bar span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.undo-btn { border: none; background: var(--plum); color: #fff; font-size: 12px; font-weight: 700; padding: 6px 14px; border-radius: 999px; cursor: pointer; flex: none; }
.undo-btn:hover { opacity: .88; }
</style>
