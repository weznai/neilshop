<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import { statusLabel, statusTag } from '../../composables/orderStatus'

const auth = useAuthStore()
const orders = ref([])
const orderTotal = ref(0)
const wlCount = ref(null)
const pts = ref(null)
const loaded = ref(false)
const failed = ref(false)

/* OrderStatus 共享映射（composables/orderStatus.js） */
/* User.tier：0普通 1银 2金 */
const TIER = { 0: 'Glow', 1: 'Shimmer', 2: 'Diva' }

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
function fmt(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

onMounted(async () => {
  const jobs = [
    req('GET', '/api/orders').then((d) => {
      orders.value = d.items || []
      orderTotal.value = d.total || 0
    }).catch(() => { failed.value = true }),
    req('GET', '/api/account/wishlist').then((l) => { wlCount.value = (l || []).length }).catch(() => {}),
    req('GET', '/api/points').then((d) => { pts.value = d }).catch(() => {}),
  ]
  await Promise.allSettled(jobs)
  loaded.value = true
})

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

const u = computed(() => auth.user || {})
const recent = computed(() => orders.value.slice(0, 3))
const pointsShow = computed(() => (pts.value ? pts.value.usable : u.value.points) || 0)
</script>

<template>
  <div style="display:grid;gap:18px">
    <div class="card" style="padding:22px;background:linear-gradient(135deg,var(--rose-pale),#fff 70%)">
      <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
        <span style="width:56px;height:56px;border-radius:50%;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:22px;font-weight:700">
          {{ (u.name || u.email || 'G').charAt(0).toUpperCase() }}
        </span>
        <div>
          <h2 style="font-family:var(--font-title);font-size:22px">Hi, {{ u.name || 'glam queen' }} 👑</h2>
          <div style="font-size:13px;color:var(--gray);display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <span class="tag tag-paid">{{ TIER[u.tier] || 'Glow' }} 会员</span>
            <span>{{ pointsShow.toLocaleString() }} 积分 · 累计消费 {{ money(u.total_spent) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-3">
      <div class="card" style="padding:18px">
        <div style="font-size:12.5px;color:var(--gray)">📦 订单</div>
        <b style="font-size:26px">{{ failed ? '—' : orderTotal }}</b>
        <div style="font-size:12.5px"><router-link to="/account/orders" style="color:var(--plum)">全部订单 →</router-link></div>
      </div>
      <div class="card" style="padding:18px">
        <div style="font-size:12.5px;color:var(--gray)">⭐ 可用积分</div>
        <b style="font-size:26px;color:var(--plum)">{{ pointsShow.toLocaleString() }}</b>
        <div style="font-size:12.5px">
          <template v-if="pts && pts.frozen > 0">冻结 {{ pts.frozen.toLocaleString() }} 分 · </template>
          <router-link to="/account/points" style="color:var(--plum)">明细 →</router-link>
        </div>
      </div>
      <div class="card" style="padding:18px">
        <div style="font-size:12.5px;color:var(--gray)">💜 心愿单</div>
        <b style="font-size:26px">{{ wlCount === null ? '…' : wlCount }}</b>
        <div style="font-size:12.5px"><router-link to="/account/wishlist" style="color:var(--plum)">去管理 →</router-link></div>
      </div>
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:16px;margin-bottom:12px">最近订单</h3>
      <div v-if="!loaded" style="display:grid;gap:10px">
        <div v-for="i in 3" :key="i" class="skeleton" style="height:52px;border-radius:10px" />
      </div>
      <div v-else-if="recent.length" style="display:grid;gap:10px">
        <div v-for="o in recent" :key="o.order_no" style="display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:14px;padding:10px 0;border-bottom:1px solid var(--gray-light);flex-wrap:wrap">
          <div><b>{{ o.order_no }}</b><div style="font-size:12px;color:var(--gray)">{{ fmt(o.placed_at) }}</div></div>
          <span class="tag" :class="statusTag(o.status)">{{ statusLabel(o.status) }}</span>
          <div style="display:flex;gap:10px;align-items:center">
            <b style="color:var(--plum)">{{ money(o.grand_total) }}</b>
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/account/orders/detail', query: { no: o.order_no } }">详情</router-link>
          </div>
        </div>
      </div>
      <div v-else-if="failed" style="color:var(--gray);font-size:14px;padding:14px 0">
        订单加载失败 —— <a href="javascript:void(0)" style="color:var(--plum)" @click="reload">刷新重试</a>
      </div>
      <div v-else style="color:var(--gray);font-size:14px;padding:14px 0">
        还没有订单 —— <router-link to="/store" style="color:var(--plum)">去逛逛</router-link> 💅
      </div>
    </div>
  </div>
</template>
