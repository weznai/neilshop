<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'

const d = ref(null)
const range = ref('近 7 天')

onMounted(async () => {
  try { d.value = await req('GET', '/api/admin/ops/dashboard') } catch (_) { /* */ }
})

function money(c) { return '$' + ((c || 0) / 100).toFixed(2) }
const STATS = [
  { k: 'sales_7d', lb: '销售额（7天）', fmt: 'money', delta: true },
  { k: 'orders_7d', lb: '订单量（7天）', fmt: 'int' },
  { k: 'aov', lb: '客单价 AOV', fmt: 'money' },
  { k: 'conv', lb: '转化率', fmt: 'pct' },
]
function fmt(v, f) {
  if (v == null) return '—'
  if (f === 'money') return money(v)
  if (f === 'pct') return v + '%'
  return String(v)
}
const feed = () => (d.value && d.value.recent_orders) || []
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">数据看板</h1>
      <span style="font-size:12.5px;color:var(--gray)">{{ range }} · 实时数据（API）</span>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <select v-model="range" class="input" style="width:auto;height:38px;font-size:13px">
        <option>近 7 天</option><option>近 30 天</option><option>今日</option>
      </select>
      <span style="width:34px;height:34px;border-radius:50%;background:var(--plum);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:13px">运</span>
    </div>
  </div>

  <div class="stat-grid">
    <div v-for="s in STATS" :key="s.k" class="stat">
      <div class="lb">{{ s.lb }}</div>
      <div class="vl">{{ d ? fmt(d[s.k], s.fmt) : '…' }}</div>
    </div>
  </div>

  <div class="grid-2" style="margin-top:18px">
    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:12px">最近订单</h3>
      <div v-if="feed().length" style="display:grid;gap:10px">
        <div v-for="o in feed().slice(0, 8)" :key="o.order_no"
             style="display:flex;align-items:center;gap:12px;font-size:13px;padding:8px 0;border-bottom:1px solid var(--gray-light)">
          <b>{{ o.order_no }}</b>
          <span style="color:var(--gray)">{{ (o.email || '').split('@')[0] }}</span>
          <span class="feed-time" style="margin-left:auto;color:var(--gray);font-size:12px">{{ (o.created_at || '').slice(5, 16).replace('T', ' ') }}</span>
          <b style="color:var(--plum)">{{ money(o.grand_total) }}</b>
        </div>
      </div>
      <div v-else style="color:var(--gray);font-size:13px;padding:16px 0">暂无订单数据</div>
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:12px">待处理事项</h3>
      <div style="display:grid;gap:8px;font-size:13.5px">
        <router-link to="/orders" class="setrow" style="justify-content:space-between;display:flex;padding:10px 0;border-bottom:1px solid var(--gray-light)">
          <span>📦 待发货订单</span><b>{{ d?.pending_ship ?? '—' }}</b>
        </router-link>
        <router-link to="/returns" class="setrow" style="justify-content:space-between;display:flex;padding:10px 0;border-bottom:1px solid var(--gray-light)">
          <span>↩️ 待审核退货</span><b>{{ d?.pending_rma ?? '—' }}</b>
        </router-link>
        <router-link to="/tickets" class="setrow" style="justify-content:space-between;display:flex;padding:10px 0;border-bottom:1px solid var(--gray-light)">
          <span>💬 未关工单</span><b>{{ d?.open_tickets ?? '—' }}</b>
        </router-link>
        <router-link to="/inventory" class="setrow" style="justify-content:space-between;display:flex;padding:10px 0">
          <span>⚠️ 低库存 SKU</span><b>{{ d?.low_stock ?? '—' }}</b>
        </router-link>
      </div>
    </div>
  </div>
</template>
