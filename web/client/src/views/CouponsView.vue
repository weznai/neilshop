<script setup>
/* 领券中心（公开营销页）：GET /api/promo/coupons 拉列表 + POST /api/promo/coupons/{id}/claim 领取 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { req, errMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'
import { fmtDate, zulu } from '../composables/datetime'
import { setSeo } from '../composables/seo'
import { tt } from '../i18n'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()

/* 页面级 SEO：路由级兜底（meta.title/canonical）之上补本页 description（onMounted 在 afterEach 之后，不会被兜底覆盖） */
onMounted(() => {
  setSeo({
    description: 'Claim free GLOWMAG coupons — percent-off, money-off and free-shipping codes for handmade press-on nails and magnetic lashes. Limited drops, claim before they run out.',
  })
})

const items = ref([])
const loaded = ref(false)
const loadErr = ref(false)
const busy = ref({}) /* 领取中（按券 id 防连击） */

async function load() {
  loaded.value = false
  loadErr.value = false
  try { items.value = (await req('GET', '/api/promo/coupons')).items || [] }
  catch (_) { items.value = []; loadErr.value = true }
  loaded.value = true
}
onMounted(load)

/* 权益文案：type 1 百分比 / 2 固定金额（value 美分）/ 3 免邮 */
function benefit(c) {
  if (c.type === 1) return c.value + '% OFF'
  if (c.type === 2) return '$' + ((c.value || 0) / 100).toFixed(2) + ' OFF'
  return tt('FREE SHIPPING', '免邮')
}
/* 门槛：满 $xx 可用 / 无门槛 */
function minText(c) {
  return c.min_subtotal
    ? tt('Min. spend ', '满 ') + '$' + (c.min_subtotal / 100).toFixed(2) + tt(' usable', ' 可用')
    : tt('No min. spend', '无门槛')
}
/* 有效期：未开始显开始日，否则显截止日，无截止日视为长期有效 */
function validText(c) {
  try {
    if (c.starts_at && new Date(zulu(c.starts_at)) > new Date()) return tt('Starts ', '') + fmtDate(c.starts_at)
  } catch (_) { /* 时间串异常回落截止日展示 */ }
  if (c.ends_at) return tt('Valid until ', '有效至 ') + fmtDate(c.ends_at)
  return tt('No expiry', '长期有效')
}
/* 剩余量：null=无限量（标“限量”营销语），有数显剩 N 张，0 显已领完 */
function remainText(c) {
  if (c.remaining == null) return tt('Limited', '限量')
  return c.remaining > 0 ? tt('Only ' + c.remaining + ' left', '剩 ' + c.remaining + ' 张') : tt('All claimed', '已领完')
}

/* 领取：未登录跳登录带 next 回跳；409 裸 reason 码本地双语映射 */
const CLAIM_ERR = {
  already_claimed: ['Already claimed — find it in My Coupons', '已领取过该券，可在「我的优惠券」中查看'],
  coupon_ended: ['This coupon has ended', '该券活动已结束'],
  coupon_exhausted: ['All gone — this coupon is fully claimed', '手慢了，该券已被领完'],
}
async function claim(c) {
  if (c.claimed || busy.value[c.id]) return
  if (!auth.isLoggedIn) { router.push({ path: '/login', query: { next: '/coupons' } }); return }
  busy.value = { ...busy.value, [c.id]: true }
  try {
    await req('POST', '/api/promo/coupons/' + c.id + '/claim')
    c.claimed = true
    ui.toast(tt('Claimed 🎉 — see it in My Coupons', '领取成功 🎉，可在「我的优惠券」中使用'), 'success')
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    const row = CLAIM_ERR[d]
    if (d === 'already_claimed') c.claimed = true /* 后端确认已领：本地态同步置灰 */
    ui.toast(row ? tt(row[0], row[1]) : errMessage(e), 'error')
  } finally {
    busy.value = { ...busy.value, [c.id]: false }
  }
}
</script>

<template>
  <section class="section">
    <div class="container">
      <div style="text-align:center;margin-bottom:30px">
        <div style="font-size:40px;margin-bottom:4px">🎟️</div>
        <h1 style="font-family:var(--font-title);font-size:34px;margin-bottom:8px">{{ tt('Coupon Center', '领券中心') }}</h1>
        <p style="color:var(--gray)">
          {{ tt('Claim free coupons — apply the code at checkout. One coupon per order.', '免费领取优惠券，结算时输入券码抵扣。每单限用一个券码。') }}
        </p>
        <p v-if="auth.isLoggedIn" style="margin-top:8px;font-size:13px">
          <router-link to="/account/coupons" style="color:var(--plum);font-weight:600">{{ tt('My coupons →', '我的优惠券 →') }}</router-link>
        </p>
      </div>

      <div v-if="!loaded" class="grid grid-3">
        <div v-for="i in 3" :key="i" class="skeleton" style="height:172px;border-radius:var(--radius-card)" />
      </div>

      <div v-else-if="loadErr" style="text-align:center;color:var(--gray);padding:40px 0">
        <div style="font-size:44px;margin-bottom:10px">⚠️</div>
        {{ tt('Coupons failed to load — please retry', '优惠券加载失败，请稍后重试') }}
        <div style="margin-top:14px"><button class="btn btn-secondary" @click="load">⟳ {{ tt('Retry', '重试') }}</button></div>
      </div>

      <div v-else-if="!items.length" style="text-align:center;color:var(--gray);padding:40px 0">
        <div style="font-size:44px;margin-bottom:10px">🎟️</div>
        {{ tt('No coupons available right now — check back soon', '暂无可领取的优惠券，稍后再来看看') }} ·
        <router-link to="/store" style="color:var(--plum)">{{ tt('Shop all', '去逛全场') }}</router-link>
      </div>

      <div v-else class="grid grid-3">
        <div v-for="c in items" :key="c.id" class="card cp-card" :class="{ got: c.claimed }">
          <div class="cp-left">
            <b>{{ benefit(c) }}</b>
            <small v-if="c.type === 1 && c.max_discount">{{ tt('up to ', '最高省 ') }}${{ (c.max_discount / 100).toFixed(2) }}</small>
          </div>
          <div class="cp-body">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
              <b class="cp-name">{{ c.name }}</b>
              <span v-if="c.first_order_only" class="tag tag-hot">{{ tt('First order', '首单') }}</span>
            </div>
            <div class="cp-meta">{{ minText(c) }} · {{ remainText(c) }}</div>
            <div class="cp-meta">{{ validText(c) }}</div>
            <button
              class="btn btn-primary btn-sm cp-claim" :class="{ loading: busy[c.id] }"
              :disabled="c.claimed || busy[c.id] || c.remaining === 0"
              @click="claim(c)"
            >
              {{ c.claimed
                ? tt('Claimed ✓', '已领取')
                : c.remaining === 0
                  ? tt('All claimed', '已领完')
                  : (busy[c.id] ? '' : tt('Claim', '立即领取')) }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 票券卡：左侧渐变权益栏 + 右侧信息体，虚线分隔仿实体券；已领置灰 */
.cp-card { display: flex; padding: 0; overflow: hidden; }
.cp-card.got { opacity: .66; }
.cp-left {
  flex: none; width: 126px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px;
  padding: 18px 10px; text-align: center; color: #fff;
  background: linear-gradient(150deg, var(--plum-dark), var(--plum));
}
.cp-left b { font-family: var(--font-title); font-size: 20px; line-height: 1.15; }
.cp-left small { font-size: 10.5px; opacity: .85; }
.cp-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 7px; padding: 15px 16px; border-left: 2px dashed rgba(138, 74, 99, .28); }
.cp-name { font-size: 14.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cp-meta { font-size: 12.5px; color: var(--gray); }
.cp-claim { margin-top: 4px; align-self: flex-start; min-width: 96px; }
/* 小屏：权益栏转顶部横条，信息体纵向铺满 */
@media (max-width: 420px) {
  .cp-card { flex-direction: column; }
  .cp-left { width: auto; flex-direction: row; gap: 8px; padding: 12px 14px; }
  .cp-left b { font-size: 18px; }
  .cp-body { border-left: none; border-top: 2px dashed rgba(138, 74, 99, .28); }
  .cp-claim { align-self: stretch; }
}
</style>
