<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { req, productDetail } from '../../api/client'
import { useCartStore } from '../../stores/cart'
import { useUiStore } from '../../stores/ui'
import { useAuthStore } from '../../stores/auth'
import { useArmConfirm } from '../../composables/useArmConfirm'
import { i18n } from '../../i18n'

const ui = useUiStore()
const cart = useCartStore()
const auth = useAuthStore()
const router = useRouter()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
const items = ref([])
const loaded = ref(false)
const failed = ref(false)
const addingId = ref(0)
const notifyBusy = ref(0)

/* 两段式确认（useArmConfirm：5s 复位；arm 态红字 + 二段文案） */
const arm = useArmConfirm()

onMounted(async () => {
  try {
    items.value = await req('GET', '/api/account/wishlist')
    localStorage.setItem('gm_wl_count', String(items.value.length))
  } catch (_) { items.value = []; failed.value = true }
  loaded.value = true
})

async function add(pid) {
  addingId.value = pid
  /* 屏蔽 cart.add 内的通用"已加入购物车"toast（覆写法与 ProductCard quickAdd 一致），只弹规格选择说明一条 */
  const quietUi = Object.assign({}, ui, {
    toast: (msg, type) => { if (type !== 'success' || !/added to cart|已加入购物车/i.test(String(msg))) ui.toast(msg, type) },
  })
  const ok = await cart.addByProductId(pid, 1, quietUi)
  if (ok) ui.toast(tt('First in-stock variant auto-selected — adjust in cart if needed', '已自动选择首个有货规格，可在购物车调整'), 'success')
  addingId.value = 0
}

/* 售罄卡到货通知：未登录跳登录带回跳；登录取首个无货变体订阅（每卡只订一个，不循环） */
async function stockNotify(w) {
  if (notifyBusy.value) return
  if (!auth.isLoggedIn) {
    router.push({ path: '/login', query: { next: '/account/wishlist' } })
    return
  }
  notifyBusy.value = w.id
  try {
    const d = await productDetail(w.id)
    const v = (d.variants || []).find((x) => (x.stock || 0) <= 0)
    if (!v) { ui.toast(tt('All variants in stock — grab it now!', '全部规格都有货，快下单！'), 'success'); return }
    await req('POST', '/api/catalog/stock-notify', { variant_id: v.id, email: auth.user.email })
    ui.toast(tt("We'll email you when it's back in stock", '到货后第一时间邮件通知你'), 'success')
  } catch (e) {
    if (e && e.status === 409) ui.toast(tt('Just restocked — grab it now!', '该款刚回货啦，快下单！'), 'success')
    else ui.toast(tt('Subscribe failed — please retry later', '订阅失败，请稍后再试'), 'error')
  } finally { notifyBusy.value = 0 }
}
async function remove(pid) {
  try {
    await req('DELETE', '/api/account/wishlist/' + pid)
    items.value = items.value.filter((w) => w.id !== pid)
    localStorage.setItem('gm_wl_count', String(items.value.length))
    /* 广播角标即时刷新（Header 监听 gm:wl-changed） */
    window.dispatchEvent(new Event('gm:wl-changed'))
    ui.toast(tt('Removed from wishlist', '已从心愿单移除'), 'success')
  } catch (e) {
    ui.toast(e && e.status === 404 ? tt('This item is no longer in your wishlist', '该商品已不在心愿单') : tt('Remove failed — please retry later', '移除失败，请稍后再试'), 'error')
  }
}
function money(c) { return '$' + ((c || 0) / 100).toFixed(2) }
function priceRange(w) {
  if (w.price_max && w.price_min !== w.price_max) return `${money(w.price_min)} ~ ${money(w.price_max)}`
  return money(w.price_min)
}
</script>

<template>
  <div>
    <div v-if="items.length" class="grid grid-3" style="margin-bottom:12px">
      <div v-for="w in items" :key="w.id" class="pcard">
        <div class="pcard-img">
          <router-link :to="`/product?id=${w.id}`">
            <img class="img-main" :src="w.hero_image" :alt="w.title">
          </router-link>
          <span v-if="w.stock_summary?.out" class="badge badge-out">SOLD OUT</span>
          <span v-if="!w.stock_summary?.out" class="pcard-quick" role="button" tabindex="0"
            :style="{ opacity: addingId === w.id ? 1 : '', transform: addingId === w.id ? 'translateY(0)' : '' }"
            @click="add(w.id)"
          >{{ addingId === w.id ? tt('Adding…', '加入中…') : '+ ' + tt('Add to Cart', '加入购物车') }}</span>
        </div>
        <div class="pcard-info">
          <div class="pcard-title"><router-link :to="`/product?id=${w.id}`">{{ w.title }}</router-link></div>
          <div class="pcard-price">
            {{ priceRange(w) }}
            <span v-if="w.compare_at_price && w.compare_at_price > w.price_min" class="compare">{{ money(w.compare_at_price) }}</span>
          </div>
          <div v-if="w.stock_summary && !w.stock_summary.out && w.stock_summary.low" class="pcard-stock">⚠️ {{ tt('Only a few left', '少量库存') }}</div>
          <div v-else-if="w.stock_summary?.out" class="pcard-stock" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <span>{{ tt('Sold out', '已售罄') }}</span>
            <button
              class="btn btn-ghost btn-sm" style="color:var(--plum);padding:2px 8px"
              :disabled="notifyBusy === w.id"
              @click="stockNotify(w)"
            >{{ notifyBusy === w.id ? tt('Subscribing…', '订阅中…') : '🔔 ' + tt('Notify me', '到货通知') }}</button>
            <router-link class="btn btn-ghost btn-sm" style="color:var(--plum);padding:2px 8px" :to="`/product?id=${w.id}`">{{ tt('View product', '查看商品') }}</router-link>
          </div>
          <button
            class="btn btn-ghost btn-sm" style="margin-top:8px"
            :class="{ arm: arm.is(w.id) }" @click="arm.hit(w.id, () => remove(w.id))"
          >{{ arm.is(w.id) ? tt('Tap again to confirm', '再点一次确认') : tt('Remove', '移除') }}</button>
        </div>
      </div>
    </div>
    <div v-else-if="loaded && failed" class="card" style="padding:30px;text-align:center;color:var(--gray)">
      {{ tt('Could not load your wishlist — please refresh', '心愿单加载失败，请刷新重试') }}
    </div>
    <div v-else-if="loaded" class="card" style="padding:30px;text-align:center;color:var(--gray)">
      💜 {{ tt('Your wishlist is empty — tap the heart on any product page.', '心愿单还是空的 —— 去商品页点亮小心心吧。') }}
      <div style="margin-top:12px"><router-link class="btn btn-primary btn-sm" to="/store">{{ tt('Go shopping', '去逛逛') }}</router-link></div>
    </div>
    <div v-else class="grid grid-3">
      <div v-for="i in 3" :key="i" class="pcard skeleton" style="min-height:260px" />
    </div>
  </div>
</template>
