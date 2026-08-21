<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../api/client'
import EmptyState from '../components/EmptyState.vue'

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

/* 14 天日序列（daily[].date 后端已是 "MM-DD"） */
const daily = computed(() => (d.value?.daily || []).slice(-14))
const dailyMax = computed(() => Math.max(1, ...daily.value.map((x) => x.gmv_cents || 0)))
/* 参数改名 dayStr：避免遮蔽外层响应式 d（数据看板主对象） */
const dayLabel = (dayStr) => dayStr || ''

/* KPI 环比：近 7 天 vs 前 7 天（daily 求和；AOV 用两段求和相除） */
const weekDelta = computed(() => {
  const arr = daily.value
  if (arr.length < 8) return { gmv: null, orders: null, aov: null }
  const sum = (rows, k) => rows.reduce((s, x) => s + (x[k] || 0), 0)
  const cur7 = arr.slice(-7), prev7 = arr.slice(-14, -7)
  const g1 = sum(cur7, 'gmv_cents'), g0 = sum(prev7, 'gmv_cents')
  const o1 = sum(cur7, 'orders'), o0 = sum(prev7, 'orders')
  const pct = (a, b) => (b > 0 ? Math.round(((a - b) / b) * 1000) / 10 : null)
  return { gmv: pct(g1, g0), orders: pct(o1, o0), aov: pct(o1 ? g1 / o1 : 0, o0 ? g0 / o0 : 0) }
})

/* KPI 卡迷你柱状图序列：gmv / orders / aov（待处理卡为运营即时值，无日序列） */
const spark = computed(() => {
  const arr = daily.value
  return {
    gmv: arr.map((x) => x.gmv_cents || 0),
    orders: arr.map((x) => x.orders || 0),
    aov: arr.map((x) => (x.orders ? (x.gmv_cents || 0) / x.orders : 0)),
  }
})
function sparkH(vals, i) {
  const max = Math.max(1, ...vals)
  return Math.max(8, Math.round((vals[i] / max) * 100)) + '%'
}

const STATS = computed(() => [
  { lb: '销售额', vl: money(cur.value?.gmv_cents), pct: weekDelta.value.gmv, series: 'gmv' },
  { lb: '订单量', vl: String(cur.value?.orders ?? 0), pct: weekDelta.value.orders, series: 'orders' },
  { lb: '客单价 AOV', vl: money(aov.value), pct: weekDelta.value.aov, series: 'aov' },
  { lb: '待处理', vl: String(d.value?.pending_orders ?? 0), note: '待发货', series: null },
])

/* 转化漏斗：全局占比（本步/浏览）+ 相邻转化率（本步/上步）并列 */
const FUNNEL_COLORS = ['var(--rose-light)', 'var(--rose)', 'var(--plum)', 'var(--plum-dark)']
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

/* 柱状图交互：hover 高亮本柱、相邻柱降透明；x 轴标签隔 1 显示 */
const hoverBar = ref(null)

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
        <div v-if="s.pct != null" class="delta" :class="s.pct >= 0 ? 'up' : 'down'">
          {{ s.pct >= 0 ? '▲' : '▼' }} {{ Math.abs(s.pct) }}% <small style="font-weight:400;opacity:.75">vs 上周</small>
        </div>
        <div v-else-if="s.note" class="delta">{{ s.note }}</div>
        <!-- 14 天迷你柱状图（rose-light 柱 + 末柱 plum） -->
        <div v-if="s.series && spark[s.series].length" class="spark" aria-hidden="true">
          <div
            v-for="(v, i) in spark[s.series]" :key="i"
            class="spark-bar"
            :style="{ height: sparkH(spark[s.series], i), background: i === spark[s.series].length - 1 ? 'var(--plum)' : 'var(--rose-light)' }"
          ></div>
        </div>
      </div>
    </div>

    <!-- 14 天 GMV 柱状图 -->
    <div class="card card-lift" style="padding:20px;margin-top:18px">
      <h3 style="font-size:15px;margin-bottom:4px">GMV · 近 14 天</h3>
      <EmptyState v-if="!daily.length" icon="📉" title="近 14 天暂无成交数据" sub="有订单成交后这里会亮起来" />
      <div v-else style="display:flex;align-items:flex-end;gap:6px;height:180px;margin-top:14px" @mouseleave="hoverBar = null">
        <div v-for="(x, i) in daily" :key="i" style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;min-width:0;position:relative">
          <div
            :style="{
              height: Math.max(2, ((x.gmv_cents || 0) / dailyMax) * 100) + '%',
              background: i === daily.length - 1 ? 'var(--plum)' : 'var(--rose-light)',
              opacity: hoverBar != null && hoverBar !== i ? 0.55 : 1,
            }"
            style="border-radius:5px 5px 0 0;transition:height .5s,opacity .15s;cursor:pointer"
            :title="`${dayLabel(x.date)} · ${money(x.gmv_cents)} · ${x.orders || 0} 单`"
            @mouseenter="hoverBar = i"
          ></div>
          <!-- x 轴标签隔 1 显示，避免 14 根柱标签挤压 -->
          <div style="font-size:10px;color:var(--gray);text-align:center;margin-top:6px;white-space:nowrap">{{ i % 2 === 0 ? dayLabel(x.date) : '' }}</div>
        </div>
      </div>
    </div>

    <div class="grid-2" style="margin-top:18px;align-items:start">
      <!-- 待办（链接带预填筛选：待发货→orders?status=1 等） -->
      <div class="card card-lift" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">待处理事项</h3>
        <div style="display:grid;gap:2px;font-size:13.5px">
          <router-link class="todo-row" to="/orders?status=1">
            <span>📦 待发货订单<span class="todo-arrow">→</span></span><b>{{ d.pending_orders ?? 0 }}</b>
          </router-link>
          <router-link class="todo-row" to="/content">
            <span>⭐ 待审评价<span class="todo-arrow">→</span></span><b>{{ d.pending_reviews ?? 0 }}</b>
          </router-link>
          <router-link class="todo-row" to="/tickets">
            <span>💬 未关工单<span class="todo-arrow">→</span></span><b>{{ d.open_tickets ?? 0 }}</b>
          </router-link>
          <router-link class="todo-row" to="/inventory">
            <span>⚠️ 低库存 SKU<span class="todo-arrow">→</span></span><b style="color:var(--error)">{{ d.low_stock ?? 0 }}</b>
          </router-link>
          <div style="display:flex;justify-content:space-between;padding:10px 0">
            <span>🛒 24h 弃购车</span><b>{{ d.abandoned_carts ?? 0 }}</b>
          </div>
        </div>
        <!-- 快捷入口（看板未返回计数的两类待办，直达预填筛选） -->
        <div style="display:flex;gap:16px;margin-top:10px;font-size:12.5px">
          <router-link to="/orders?status=0" style="color:var(--plum)">待支付订单 →</router-link>
          <router-link to="/returns?tab=rma" style="color:var(--plum)">待审退货 →</router-link>
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

      <!-- 漏斗（四级分层配色 rose-light→rose→plum→plum-dark + 步间转化率徽标） -->
      <div class="card card-lift" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:4px">转化漏斗 <span v-if="funnel.approximate" style="font-size:11px;color:var(--gray);font-weight:400">（近似）</span></h3>
        <template v-for="(s, i) in funnel.steps" :key="s.label">
          <div v-if="i > 0" class="funnel-step">
            <span class="step-badge" :title="`本步 ${s.n} / 上步 ${funnel.steps[i - 1].n}`">↓ {{ s.step }}%</span>
          </div>
          <div style="display:flex;align-items:center;gap:12px;margin:6px 0">
            <span style="width:52px;font-size:13px;color:var(--gray);text-align:right;flex:none">{{ s.label }}</span>
            <div style="flex:1;display:flex;align-items:center;gap:9px;min-width:0">
              <div :style="{ width: Math.max(2, (s.n / funnel.max) * 78) + '%', background: FUNNEL_COLORS[i] }" style="height:24px;border-radius:6px;flex:none;transition:width .4s"></div>
              <b style="font-size:13px;color:var(--plum)">{{ s.n }}</b>
              <small style="color:var(--gray);font-size:11.5px;white-space:nowrap">全局 {{ s.global }}%</small>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 热销榜 -->
    <div class="card card-lift" style="padding:20px;margin-top:18px">
      <h3 style="font-size:15px;margin-bottom:12px">热销 Top 5</h3>
      <div v-if="topProducts.length" style="display:grid;gap:10px">
        <div v-for="(p, i) in topProducts" :key="p.id || i" style="display:flex;align-items:center;gap:12px;font-size:13.5px;padding:8px 0;border-bottom:1px solid var(--gray-light)">
          <b style="width:22px;color:var(--plum);font-family:var(--font-title);font-size:16px">{{ i + 1 }}</b>
          <span style="flex:1">{{ p.title }}</span>
          <span style="color:var(--gray)">售出 {{ p.sold_count ?? p.sold ?? '—' }}</span>
        </div>
      </div>
      <EmptyState v-else icon="🏆" title="暂无热销数据" sub="有成交后这里会展示 Top 5" />
    </div>
  </template>
  <div v-else class="card skeleton" style="min-height:300px" />
</template>

<style scoped>
/* KPI 卡迷你柱状图：12px 高，rose-light 柱 + 末柱 plum（末柱在模板内联指定） */
.spark{display:flex;align-items:flex-end;gap:2px;height:12px;margin-top:10px}
.spark-bar{flex:1;min-width:2px;border-radius:1px 1px 0 0;background:var(--rose-light);transition:height .4s}
/* 待办行：hover 箭头右移 */
.todo-row{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--gray-light)}
.todo-arrow{display:inline-block;margin-left:6px;color:var(--plum);opacity:0;transform:translateX(-4px);transition:opacity .18s,transform .18s}
.todo-row:hover .todo-arrow{opacity:1;transform:none}
/* 漏斗步间转化率徽标 */
.funnel-step{display:flex;justify-content:flex-start;padding:0 0 0 64px;margin:-2px 0}
.step-badge{font-size:10.5px;font-weight:700;color:var(--plum);background:var(--rose-pale);border:1px solid var(--rose-light);border-radius:999px;padding:1px 8px}
</style>
