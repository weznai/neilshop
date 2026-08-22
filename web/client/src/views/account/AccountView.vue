<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { req } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { useUiStore } from '../../stores/ui'
import { statusLabel, statusTag } from '../../composables/orderStatus'
import { i18n } from '../../i18n'

const auth = useAuthStore()
const ui = useUiStore()
const tt = (en, zh) => (i18n.lang === 'zh' ? zh : en)
const orders = ref([])
const orderTotal = ref(0)
const wlCount = ref(null)
const pts = ref(null)
const expiringSum = ref(0)
const loaded = ref(false)
const failed = ref(false)
const payingNo = ref('')

/* 心愿单计数：读 localStorage gm_wl_count（WishlistView/ProductView 维护）+ 监听 gm:wl-changed，不再拉全量 */
function syncWl() {
  const v = parseInt((localStorage.getItem('gm_wl_count') || '').trim(), 10)
  wlCount.value = isNaN(v) ? null : v
}
function onWlChanged() { syncWl() }

/* OrderStatus 共享映射（composables/orderStatus.js） */
/* User.tier：0普通 1银 2金；门槛：$100 / $300（美分） */
const TIER = { 0: 'Glow', 1: 'Shimmer', 2: 'Diva' }
const TIER_NEXT = { 0: 10000, 1: 30000 }

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
function fmt(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  const p = (n) => String(n).padStart(2, '0')
  const hm = `${p(d.getHours())}:${p(d.getMinutes())}`
  return d.getFullYear() === new Date().getFullYear()
    ? `${p(d.getMonth() + 1)}-${p(d.getDate())} ${hm}`
    : `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${hm}`
}

onMounted(async () => {
  syncWl()
  window.addEventListener('gm:wl-changed', onWlChanged)
  const jobs = [
    req('GET', '/api/orders').then((d) => {
      orders.value = d.items || []
      orderTotal.value = d.total || 0
    }).catch(() => { failed.value = true }),
    req('GET', '/api/points').then((d) => { pts.value = d }).catch(() => {}),
    /* 即将过期积分（>0 时黄色警示）：汇总正向流水 change 之和 */
    req('GET', '/api/points/expiring').then((d) => {
      expiringSum.value = (d.items || []).reduce((n, r) => n + Math.max(0, r.change || 0), 0)
    }).catch(() => {}),
  ]
  await Promise.allSettled(jobs)
  loaded.value = true
})
onUnmounted(() => window.removeEventListener('gm:wl-changed', onWlChanged))

async function reload() {
  failed.value = false
  loaded.value = false
  try {
    const d = await req('GET', '/api/orders')
    orders.value = d.items || []
    orderTotal.value = d.total || 0
  } catch (_) { failed.value = true }
  loaded.value = true
}

/* 待付订单支付：先建支付意图再 mock 支付（与 OrdersView 一致） */
async function pay(o) {
  payingNo.value = o.order_no
  try {
    await req('POST', '/api/payments/create-intent', { order_no: o.order_no })
    const d = await req('POST', '/api/payments/mock-pay', { order_no: o.order_no, succeed: true })
    ui.toast(d.order_status === 1 ? tt('Payment successful — points will be credited after confirmation', '支付成功，积分将在确认后发放') : tt('Payment processing', '支付处理中'), 'success')
    await reload()
  } catch (e) {
    const d = e && e.data && e.data.detail || ''
    if (String(d).startsWith('order_not_pending')) { ui.toast(tt('Order status changed — refreshed', '订单状态已变化，已刷新'), 'error'); reload() }
    else if (d === 'already_paid') { ui.toast(tt('This order is already paid', '该订单已支付'), 'error'); reload() }
    else ui.toast(tt('Payment failed — please retry later', '支付失败，请稍后再试'), 'error')
  } finally { payingNo.value = '' }
}

const u = computed(() => auth.user || {})
const recent = computed(() => orders.value.slice(0, 3))
const pointsShow = computed(() => (pts.value ? pts.value.usable : u.value.points) || 0)
/* 等级晋升进度：下一档门槛 $100/$300（美分），已到顶显示满格 */
const tierNext = computed(() => {
  const t = u.value.tier || 0
  const goal = TIER_NEXT[t]
  if (goal === undefined) return null
  const spent = u.value.total_spent || 0
  return {
    goal,
    pct: Math.min(100, Math.round((spent / goal) * 100)),
    left: Math.max(0, goal - spent),
    next: TIER[t + 1],
  }
})
</script>

<template>
  <div style="display:grid;gap:18px">
    <div class="card" style="padding:22px;background:linear-gradient(135deg,var(--rose-pale),#fff 70%)">
      <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
        <span style="width:56px;height:56px;border-radius:50%;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:22px;font-weight:700">
          {{ (u.name || u.email || 'G').charAt(0).toUpperCase() }}
        </span>
        <div style="flex:1;min-width:220px">
          <h2 style="font-family:var(--font-title);font-size:22px">{{ tt('Hi', '嗨') }}, {{ u.name || tt('glam queen', '宝贝') }} 👑</h2>
          <div style="font-size:13px;color:var(--gray);display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <span class="tag tag-paid">{{ TIER[u.tier] || 'Glow' }} {{ tt('member', '会员') }}</span>
            <span>{{ tt(`${pointsShow.toLocaleString()} pts · lifetime spend ${money(u.total_spent)}`, `${pointsShow.toLocaleString()} 积分 · 累计消费 ${money(u.total_spent)}`) }}</span>
          </div>
          <!-- 等级晋升进度条：下一档 $100/$300 差额 -->
          <div v-if="tierNext" class="tier-prog">
            <div class="ship-track"><div class="ship-fill" :style="{ width: tierNext.pct + '%' }" /></div>
            <div class="tier-prog-text">
              {{ money(u.total_spent) }} / {{ money(tierNext.goal) }} ·
              {{ tierNext.left > 0
                ? tt(`spend ${money(tierNext.left)} more to reach ${tierNext.next}`, `再消费 ${money(tierNext.left)} 升级 ${tierNext.next}`)
                : tt(`${tierNext.next} unlock imminent ✓`, `即将升级 ${tierNext.next} ✓`) }}
            </div>
          </div>
        </div>
      </div>
      <!-- 即将过期积分警示条（>0 显示） -->
      <div v-if="expiringSum > 0" class="expiring-bar">
        ⏳ <b>{{ tt(`${expiringSum.toLocaleString()} pts expiring soon`, `${expiringSum.toLocaleString()} 积分即将过期`) }}</b> · {{ tt('use them at checkout', '结账时记得先用掉哦') }}
        <router-link to="/account/points" style="color:var(--warn);font-weight:700;text-decoration:underline">{{ tt('View details →', '查看明细 →') }}</router-link>
      </div>
    </div>

    <div class="grid grid-3">
      <div class="card stat-card" style="padding:18px">
        <div style="font-size:12.5px;color:var(--gray)">📦 {{ tt('Orders', '订单') }}</div>
        <b style="font-size:26px">{{ failed ? '—' : orderTotal }}</b>
        <div style="font-size:12.5px"><router-link to="/account/orders" style="color:var(--plum)">{{ tt('All orders →', '全部订单 →') }}</router-link></div>
      </div>
      <div class="card stat-card" style="padding:18px">
        <div style="font-size:12.5px;color:var(--gray)">⭐ {{ tt('Usable points', '可用积分') }}</div>
        <b style="font-size:26px;color:var(--plum)">{{ pointsShow.toLocaleString() }}</b>
        <div style="font-size:12.5px">
          <template v-if="pts && pts.frozen > 0">{{ tt(`${pts.frozen.toLocaleString()} frozen ·`, `冻结 ${pts.frozen.toLocaleString()} 分 ·`) }} </template>
          <router-link to="/account/points" style="color:var(--plum)">{{ tt('Details →', '明细 →') }}</router-link>
        </div>
      </div>
      <div class="card stat-card" style="padding:18px">
        <div style="font-size:12.5px;color:var(--gray)">💜 {{ tt('Wishlist', '心愿单') }}</div>
        <b style="font-size:26px">{{ wlCount === null ? '…' : wlCount }}</b>
        <div style="font-size:12.5px"><router-link to="/account/wishlist" style="color:var(--plum)">{{ tt('Manage →', '去管理 →') }}</router-link></div>
      </div>
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:16px;margin-bottom:12px">{{ tt('Recent orders', '最近订单') }}</h3>
      <div v-if="!loaded" style="display:grid;gap:10px">
        <div v-for="i in 3" :key="i" class="skeleton" style="height:52px;border-radius:10px" />
      </div>
      <div v-else-if="recent.length" style="display:grid;gap:10px">
        <div v-for="o in recent" :key="o.order_no" style="display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:14px;padding:10px 0;border-bottom:1px solid var(--gray-light);flex-wrap:wrap">
          <div><b>{{ o.order_no }}</b><div style="font-size:12px;color:var(--gray)">{{ fmt(o.placed_at) }}</div></div>
          <span class="tag" :class="statusTag(o.status)">{{ statusLabel(o.status) }}</span>
          <div style="display:flex;gap:10px;align-items:center">
            <b style="color:var(--plum)">{{ money(o.grand_total) }}</b>
            <button v-if="o.status === 0" class="btn btn-primary btn-sm" :class="{ loading: payingNo === o.order_no }" :disabled="payingNo === o.order_no" @click="pay(o)">{{ tt('Pay now', '去支付') }}</button>
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/account/orders/detail', query: { no: o.order_no } }">{{ tt('Details', '详情') }}</router-link>
          </div>
        </div>
      </div>
      <div v-else-if="failed" style="color:var(--gray);font-size:14px;padding:14px 0">
        {{ tt('Could not load orders —', '订单加载失败 ——') }} <a href="javascript:void(0)" style="color:var(--plum)" @click="reload">{{ tt('refresh', '刷新重试') }}</a>
      </div>
      <div v-else style="color:var(--gray);font-size:14px;padding:14px 0">
        {{ tt('No orders yet —', '还没有订单 ——') }} <router-link to="/store" style="color:var(--plum)">{{ tt('start shopping', '去逛逛') }}</router-link> 💅
      </div>
    </div>
  </div>
</template>

<style scoped>
.tier-prog { margin-top: 8px; max-width: 420px; }
.tier-prog-text { font-size: 11.5px; color: var(--gray); margin-top: 5px; }
.expiring-bar { margin-top: 14px; padding: 10px 14px; border-radius: 10px; background: var(--pale-warn); color: var(--warn); font-size: 13px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
/* 统计卡 hover 上浮 */
.stat-card { transition: transform .18s ease-out, box-shadow .18s ease-out; }
.stat-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-pop); }
</style>
