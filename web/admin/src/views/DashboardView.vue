<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../api/client'

const d = ref(null)
const err = ref('')
const range = ref('last7')
const refreshing = ref(false)

async function refresh() {
  refreshing.value = true
  err.value = ''
  try { d.value = await req('GET', '/api/admin/ops/dashboard') }
  catch (e) { err.value = (e.status || '') + ' ' + (e.message || '') }
  refreshing.value = false
}
onMounted(refresh)

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const cur = computed(() => (d.value ? d.value[range.value] : null))
const aov = computed(() => (cur.value && cur.value.orders ? Math.round(cur.value.gmv_cents / cur.value.orders) : 0))

const STATS = computed(() => [
  { lb: '销售额', vl: money(cur.value?.gmv_cents), delta: '' },
  { lb: '订单量', vl: String(cur.value?.orders ?? 0), delta: '' },
  { lb: '客单价 AOV', vl: money(aov.value), delta: '' },
  { lb: '待处理', vl: String(d.value?.pending_orders ?? 0), delta: '待发货' },
])

/* 14 天柱状图（daily[].date 后端已是 "MM-DD"） */
const daily = computed(() => (d.value?.daily || []).slice(-14))
const dailyMax = computed(() => Math.max(1, ...daily.value.map((x) => x.gmv_cents || 0)))
/* 参数改名 dayStr：避免遮蔽外层响应式 d（数据看板主对象） */
const dayLabel = (dayStr) => dayStr || ''

/* 转化漏斗：全局占比（本步/浏览）+ 相邻转化率（本步/上步）并列 */
const funnel = computed(() => {
  const f = d.value?.funnel || {}
  const rows = [
    ['浏览', f.views || 0],
    ['加购', f.add_to_cart || 0],
    ['下单', f.orders || 0],
    ['支付', f.paid || 0],
  ]
  const base = rows[0][1] || 1
  const steps = rows.map(([label, n], i) => ({
    label,
    n,
    global: Math.round((n / base) * 100),
    step: i === 0 ? null : Math.round((n / (rows[i - 1][1] || 1)) * 100),
  }))
  const max = Math.max(1, ...steps.map((s) => s.n))
  return { steps, max, approximate: f.approximate }
})

const topProducts = computed(() => (d.value?.top_products || []).slice(0, 5))
const lowStockTop = computed(() => (d.value?.low_stock_top || []).slice(0, 5))
const reconcile = computed(() => d.value?.reconcile)
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">数据看板</h1>
      <span style="font-size:12.5px;color:var(--gray)">实时数据（API）</span>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <button class="btn btn-secondary" :class="{ loading: refreshing }" :disabled="refreshing" @click="refresh">{{ refreshing ? '刷新中…' : '⟳ 刷新' }}</button>
      <select v-model="range" class="input" style="width:auto;height:38px;font-size:13px">
        <option value="today">今日</option>
        <option value="last7">近 7 天</option>
        <option value="last30">近 30 天</option>
      </select>
    </div>
  </div>

  <div v-if="err" class="card" style="padding:30px;text-align:center;color:var(--error)">加载失败：{{ err }}</div>

  <template v-else-if="d">
    <div class="stat-grid">
      <div v-for="s in STATS" :key="s.lb" class="stat">
        <div class="lb">{{ s.lb }}{{ range !== 'today' ? `（${range === 'last7' ? '7天' : '30天'}）` : '' }}</div>
        <div class="vl">{{ s.vl }}</div>
        <div v-if="s.delta" class="delta">{{ s.delta }}</div>
      </div>
    </div>

    <!-- 14 天 GMV 柱状图 -->
    <div class="card" style="padding:20px;margin-top:18px">
      <h3 style="font-size:15px;margin-bottom:4px">GMV · 近 14 天</h3>
      <div v-if="!daily.length" style="color:var(--gray);font-size:13px;text-align:center;padding:48px 0">近 14 天暂无成交数据</div>
      <div v-else style="display:flex;align-items:flex-end;gap:6px;height:180px;margin-top:14px">
        <div v-for="(x, i) in daily" :key="i" style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;min-width:0;position:relative">
          <div
            :style="{ height: Math.max(2, ((x.gmv_cents || 0) / dailyMax) * 100) + '%', background: i === daily.length - 1 ? 'var(--plum)' : 'var(--rose-light)' }"
            style="border-radius:5px 5px 0 0;transition:height .5s"
            :title="`${dayLabel(x.date)} · ${money(x.gmv_cents)} · ${x.orders || 0} 单`"
          ></div>
          <div style="font-size:10px;color:var(--gray);text-align:center;margin-top:6px;white-space:nowrap">{{ dayLabel(x.date) }}</div>
        </div>
      </div>
    </div>

    <div class="grid-2" style="margin-top:18px;align-items:start">
      <!-- 待办 -->
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">待处理事项</h3>
        <div style="display:grid;gap:2px;font-size:13.5px">
          <router-link to="/orders" style="display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--gray-light)">
            <span>📦 待发货订单</span><b>{{ d.pending_orders ?? 0 }}</b>
          </router-link>
          <router-link to="/content" style="display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--gray-light)">
            <span>⭐ 待审评价</span><b>{{ d.pending_reviews ?? 0 }}</b>
          </router-link>
          <router-link to="/tickets" style="display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--gray-light)">
            <span>💬 未关工单</span><b>{{ d.open_tickets ?? 0 }}</b>
          </router-link>
          <router-link to="/inventory" style="display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--gray-light)">
            <span>⚠️ 低库存 SKU</span><b style="color:var(--error)">{{ d.low_stock ?? 0 }}</b>
          </router-link>
          <div style="display:flex;justify-content:space-between;padding:10px 0">
            <span>🛒 24h 弃购车</span><b>{{ d.abandoned_carts ?? 0 }}</b>
          </div>
        </div>
        <div v-if="lowStockTop.length" style="margin-top:12px;padding-top:10px;border-top:1px dashed var(--gray-light)">
          <div style="font-size:12px;color:var(--gray);margin-bottom:4px">最缺货 Top {{ lowStockTop.length }}（库存 ≤ 8）</div>
          <div v-for="v in lowStockTop" :key="v.sku" style="display:flex;justify-content:space-between;gap:10px;font-size:12.5px;padding:4px 0">
            <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="v.sku + ' · ' + v.title">{{ v.sku }} · {{ v.title }}</span>
            <b :style="{ color: (v.stock || 0) <= 3 ? 'var(--error)' : 'var(--warn)' }" style="flex:none">余 {{ v.stock ?? 0 }}</b>
          </div>
        </div>
        <div v-if="reconcile" style="margin-top:12px;padding-top:10px;border-top:1px dashed var(--gray-light);font-size:12.5px;color:var(--gray)">
          对账 {{ reconcile.reconcile_date }}：
          <span :style="{ color: reconcile.diff_payment > 0 ? 'var(--error)' : 'var(--success)' }" title="支付差额，非 0 需人工核对">支付 diff {{ money(reconcile.diff_payment) }}{{ reconcile.diff_payment > 0 ? ' ⚠️' : '' }}</span> ·
          <span :style="{ color: reconcile.diff_points > 0 ? 'var(--error)' : 'var(--success)' }" title="积分差额，非 0 需人工核对">积分 diff {{ reconcile.diff_points }} 分{{ reconcile.diff_points > 0 ? ' ⚠️' : '' }}</span>
        </div>
      </div>

      <!-- 漏斗 -->
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:4px">转化漏斗 <span v-if="funnel.approximate" style="font-size:11px;color:var(--gray);font-weight:400">（近似）</span></h3>
        <div v-for="(s, i) in funnel.steps" :key="s.label" style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
          <span style="width:52px;font-size:13px;color:var(--gray);text-align:right;flex:none">{{ s.label }}</span>
          <div style="flex:1;display:flex;align-items:center;gap:9px;min-width:0">
            <div :style="{ width: Math.max(2, (s.n / funnel.max) * 78) + '%' }" style="height:24px;border-radius:6px;background:linear-gradient(90deg,var(--rose),var(--plum));flex:none"></div>
            <b style="font-size:13px;color:var(--plum)">{{ s.n }}</b>
            <small style="color:var(--gray);font-size:11.5px;white-space:nowrap">
              全局 {{ s.global }}%<template v-if="i > 0"> · 转化 {{ s.step }}%</template>
            </small>
          </div>
        </div>
      </div>
    </div>

    <!-- 热销榜 -->
    <div class="card" style="padding:20px;margin-top:18px">
      <h3 style="font-size:15px;margin-bottom:12px">热销 Top 5</h3>
      <div v-if="topProducts.length" style="display:grid;gap:10px">
        <div v-for="(p, i) in topProducts" :key="p.id || i" style="display:flex;align-items:center;gap:12px;font-size:13.5px;padding:8px 0;border-bottom:1px solid var(--gray-light)">
          <b style="width:22px;color:var(--plum);font-family:var(--font-title);font-size:16px">{{ i + 1 }}</b>
          <span style="flex:1">{{ p.title }}</span>
          <span style="color:var(--gray)">售出 {{ p.sold_count ?? p.sold ?? '—' }}</span>
        </div>
      </div>
      <div v-else style="color:var(--gray);font-size:13px;padding:12px 0">暂无数据</div>
    </div>
  </template>
  <div v-else class="card skeleton" style="min-height:300px" />
</template>
