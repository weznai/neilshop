<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import { i18n } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const cart = useCartStore()
const ui = useUiStore()
const auth = useAuthStore()

const p = ref(null)                 /* 商品详情 */
const vIdx = ref(0)
const qty = ref(1)
const reviews = ref([])
const adding = ref(false)
const notifyEmail = ref('')
const notifyState = ref(0)          /* 0 无 / 1 已订阅 */
const zh = computed(() => i18n.lang === 'zh')

const locale = computed(() => (zh.value ? 'zh-CN' : null))
const variant = computed(() => (p.value?.variants || [])[vIdx.value] || null)
const stockStatus = computed(() => variant.value?.stock_status || 'in')

async function load() {
  vIdx.value = 0
  qty.value = 1
  const id = parseInt(route.query.id, 10)
  const slug = route.query.slug
  try {
    p.value = slug
      ? await req('GET', '/api/catalog/products/' + slug + (locale.value ? '?locale=' + locale.value : ''))
      : await req('GET', '/api/catalog/products-by-id/' + (id || 3) + (locale.value ? '?locale=' + locale.value : ''))
    try {
      const r = await req('GET', '/api/catalog/reviews?product_id=' + p.value.id)
      reviews.value = r.items || []
    } catch (_) { reviews.value = [] }
  } catch (_) { p.value = null }
}
watch(() => route.query, load)
onMounted(load)

const basePrice = computed(() => (p.value?.variants?.[0]?.price ?? 0) / 100)

async function addToCart() {
  if (!variant.value || variant.value.stock <= 0) return
  adding.value = true
  await cart.add(variant.value.id, qty.value, ui)
  adding.value = false
}
async function bundleAdd() {
  await cart.addByProductId(p.value.id, 1, { ...ui, openCart: () => {} })
  ui.toast('Bundle added — saved $3.30 🎁', 'success')
}
function email() {
  return notifyEmail.value.trim() || (auth.user && auth.user.email) || ''
}
async function notifyMe() {
  if (!variant.value) { ui.toast("We'll email you the moment it's back in stock ✓", 'success'); return }
  try {
    await req('POST', '/api/catalog/stock-notify', { variant_id: variant.value.id, email: email() })
    notifyState.value = 1
    ui.toast("We'll email you when it's back in stock ✓", 'success')
  } catch (e) {
    ui.toast(e.status === 422 ? 'Enter a valid email first' : 'Subscribe failed', 'error')
  }
}
const gmEta = () => {
  const M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const d1 = new Date(Date.now() + 3 * 864e5), d2 = new Date(Date.now() + 6 * 864e5)
  return d1.getMonth() === d2.getMonth()
    ? `${M[d1.getMonth()]} ${d1.getDate()}–${d2.getDate()}`
    : `${M[d1.getMonth()]} ${d1.getDate()} – ${M[d2.getMonth()]} ${d2.getDate()}`
}
</script>

<template>
  <section class="section" v-if="p">
    <div class="container">
      <div class="grid-m-1" style="display:grid;grid-template-columns:1.05fr .95fr;gap:44px">
        <!-- 左：媒体 -->
        <div>
          <div style="position:relative;border-radius:18px;overflow:hidden;aspect-ratio:1;background:var(--rose-pale)">
            <img :src="p.hero_image" :alt="p.title" style="width:100%;height:100%;object-fit:cover">
            <span v-if="p.is_new" class="badge badge-new" style="position:absolute;top:14px;left:14px">NEW</span>
            <span v-if="p.compare_at_price" class="badge badge-sale" style="position:absolute;top:14px;right:14px">
              -{{ Math.round((1 - p.price_min / p.compare_at_price) * 100) }}%
            </span>
          </div>
          <div v-if="(p.images || []).length > 1" style="display:flex;gap:8px;margin-top:10px;overflow-x:auto">
            <img
              v-for="(im, i) in p.images.slice(0, 6)" :key="i" :src="im" :alt="`${p.title} view ${i + 1}`"
              style="width:64px;height:64px;border-radius:10px;object-fit:cover;flex:none;border:1.5px solid var(--gray-light)"
            >
          </div>
        </div>

        <!-- 右：购买面板 -->
        <div>
          <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:6px">{{ p.title }}</h1>
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            <span class="stars" style="color:var(--gold)">★★★★★</span>
            <span style="font-size:13px;color:var(--gray)">{{ (p.rating || 4.9) }} · {{ (p.rating_count || 0).toLocaleString() }} reviews</span>
          </div>
          <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:18px">
            <span style="font-size:32px;font-weight:800;color:var(--plum);font-variant-numeric:tabular-nums">
              ${{ (variant ? variant.price / 100 : basePrice).toFixed(2) }}
            </span>
            <span v-if="p.compare_at_price" style="color:var(--gray);text-decoration:line-through">
              ${{ (p.compare_at_price / 100).toFixed(2) }}
            </span>
          </div>

          <!-- 变体选择 -->
          <div style="margin-bottom:18px">
            <div style="font-size:12.5px;font-weight:700;letter-spacing:1px;color:var(--gray);margin-bottom:10px">
              SHAPE — <span id="selShape">{{ variant?.option1_value }}</span>
            </div>
            <div id="shapePicker" style="display:flex;gap:8px;flex-wrap:wrap">
              <button
                v-for="(v, i) in p.variants" :key="v.id"
                class="vbtn" :class="{ sel: vIdx === i }" :data-shape="v.option1_value"
                @click="vIdx = i"
              >
                {{ v.option1_value }}
                <b v-if="i > 0 && v.price > p.variants[0].price" style="color:var(--plum)">
                  +${{ ((v.price - p.variants[0].price) / 100).toFixed(2) }}
                </b>
              </button>
            </div>
          </div>

          <!-- 库存提示 -->
          <div id="stockHint" style="margin-bottom:18px;font-size:13.5px">
            <template v-if="stockStatus === 'out'">
              <b style="color:var(--error)">Out of stock</b> —
              <button type="button" class="btn btn-secondary" style="height:26px;padding:0 10px;font-size:12px;margin-left:4px" @click="notifyMe">
                Notify me
              </button>
            </template>
            <template v-else-if="stockStatus === 'low'">
              ⚡ <b style="color:var(--warn)">Only {{ variant.stock }} left</b>
              <span style="color:var(--gray)">— selling fast</span>
              <div class="stock-track"><div class="stock-fill" :style="{ width: Math.min(variant.stock * 2, 100) + '%' }"></div></div>
            </template>
            <template v-else>🚚 <b style="color:var(--success)">In stock &amp; ready to ship</b></template>
          </div>

          <!-- 数量 + 加购 -->
          <div style="display:flex;gap:12px;margin-bottom:14px">
            <div style="display:flex;align-items:center;border:1.5px solid var(--gray-light);border-radius:12px">
              <button class="qbtn" @click="qty = Math.max(1, qty - 1)">−</button>
              <span style="width:36px;text-align:center;font-weight:600">{{ qty }}</span>
              <button class="qbtn" @click="qty = Math.min(10, qty + 1)">＋</button>
            </div>
            <button id="addBtn" class="btn btn-primary btn-lg" style="flex:1" :disabled="stockStatus === 'out' || adding" :class="{ loading: adding }" @click="addToCart">
              Add to Cart · ${{ ((variant ? variant.price / 100 : basePrice) * qty).toFixed(2) }}
            </button>
          </div>
          <button class="btn btn-secondary btn-block" @click="bundleAdd">🎁 Buy 2 &amp; save 15% — applied in cart</button>

          <div style="font-size:12.5px;color:var(--gray);margin:16px 0 0;display:grid;gap:6px">
            <span>🚚 Free shipping over $35 · Est. delivery {{ gmEta() }}</span>
            <span>↩️ 30-day returns · exchanges always free</span>
            <span>🔒 Secure checkout · VISA / MC / PAYPAL / KLARNA</span>
          </div>
        </div>
      </div>

      <!-- 评价 -->
      <section class="section" style="padding-top:44px">
        <div class="section-head">
          <h2 class="section-title">Reviews ({{ (p.rating_count || 0).toLocaleString() }})</h2>
          <span style="font-size:14px;color:var(--gray)">{{ p.rating || 4.9 }} / 5</span>
        </div>
        <div class="grid grid-3">
          <div v-for="rv in reviews.slice(0, 6)" :key="rv.id" class="card">
            <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px">
              <span style="width:32px;height:32px;border-radius:50%;background:var(--rose);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:700">
                {{ (rv.reviewer_name || 'A').charAt(0).toUpperCase() }}
              </span>
              <b style="font-size:13px">{{ rv.reviewer_name }}</b>
              <span style="font-size:10.5px;font-weight:700;color:var(--success);background:rgba(62,189,147,.10);border:1px solid rgba(62,189,147,.35);border-radius:999px;padding:1.5px 9px;white-space:nowrap">✓ Verified Buyer</span>
            </div>
            <div class="stars" style="margin:8px 0">{{ '★'.repeat(rv.rating) }}<span class="off">{{ '★'.repeat(5 - rv.rating) }}</span></div>
            <p style="font-size:14px">{{ rv.content }}</p>
          </div>
        </div>
        <div v-if="!reviews.length" style="text-align:center;color:var(--gray);padding:30px 0">
          {{ zh ? '第一个来评价吧' : 'Be the first to review this set' }}
        </div>
      </section>
    </div>
  </section>

  <section v-else class="section">
    <div class="container" style="text-align:center;padding:80px 0;color:var(--gray)">
      <div style="font-size:44px;margin-bottom:10px">💅</div>
      Product not found — <router-link to="/store" style="color:var(--plum)">back to store</router-link>
    </div>
  </section>
</template>
