<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'

const d = ref(null)
const err = ref('')
/* 时间范围入 URL（today/last7/last30）：刷新/分享保持所选范围；非法值回落 last7 */
const RANGES = ['today', 'last7', 'last30']
const st = reactive({ range: 'last7' })
useQuerySync(st, { defaults: { range: 'last7' } })
if (!RANGES.includes(st.range)) st.range = 'last7'
const refreshing = ref(false)
const loadedAt = ref(null)      /* 数据加载完成时间（卡头展示 HH:mm:ss） */

async function refresh() {
  refreshing.value = true
  err.value = ''
  try { d.value = await req('GET', '/api/admin/ops/dashboard'); loadedAt.value = new Date() }
  catch (e) { err.value = (e.status || '') + ' ' + (e.message || '') }
  refreshing.value = false
}
onMounted(refresh)

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
const fmtHMS = (dt) => (dt ? dt.toTimeString().slice(0, 8) : '')
const cur = computed(() => (d.value ? d.value[st.range] : null))
const aov = computed(() => (cur.value && cur.value.orders ? Math.round(cur.value.gmv_cents / cur.value.orders) : 0))

/* 14 天日序列（daily[].date 后端已是 "MM-DD"） */
const daily = computed(() => (d.value?.daily || []).slice(-14))
const dailyMax = computed(() => Math.max(1, ...daily.value.map((x) => x.gmv_cents || 0)))
const dailyTotal = computed(() => daily.value.reduce((s, x) => s + (x.gmv_cents || 0), 0))
const dailyAvg = computed(() => (daily.value.length ? Math.round(dailyTotal.value / daily.value.length) : 0))
/* 参数改名 dayStr：避免遮蔽外层响应式 d（数据看板主对象） */
const dayLabel = (dayStr) => dayStr || ''
/* 柱高百分比（≥2% 保底可见） */
const barH = (x) => Math.max(2, ((x.gmv_cents || 0) / dailyMax.value) * 100) + '%'

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
  { lb: '待处理', vl: String(d.value?.pending_orders ?? 0), note: '待发货', series: null, hot: true },
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
const funnelOverall = computed(() => funnel.value.steps[3]?.global ?? 0)

/* 柱状图交互：hover 高亮本柱、其余降透明；x 轴标签隔 1 显示 */
const hoverBar = ref(null)

const topProducts = computed(() => (d.value?.top_products || []).slice(0, 5))
const soldOf = (p) => p.sold_count ?? p.sold ?? 0
const maxSold = computed(() => Math.max(1, ...topProducts.value.map(soldOf)))
const lowStockTop = computed(() => (d.value?.low_stock_top || []).slice(0, 5))
const reconcile = computed(() => d.value?.reconcile)
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="dash-h1">数据看板</h1>
      <span class="dash-sub">实时数据（API）</span>
    </div>
    <div class="dash-actions">
      <span v-if="loadedAt && !err" class="dash-sub" title="数据加载完成时间">更新于 {{ fmtHMS(loadedAt) }}</span>
      <button class="btn btn-secondary" :class="{ loading: refreshing }" :disabled="refreshing" @click="refresh">{{ refreshing ? '刷新中…' : '⟳ 刷新' }}</button>
      <select v-model="st.range" class="input" style="width:auto;height:38px;font-size:13px">
        <option value="today">今日</option>
        <option value="last7">近 7 天</option>
        <option value="last30">近 30 天</option>
      </select>
    </div>
  </div>

  <EmptyState v-if="err" icon="⚠️" title="看板加载失败" :sub="err">
    <template #action><button class="btn btn-secondary btn-sm" :class="{ loading: refreshing }" :disabled="refreshing" @click="refresh">重试</button></template>
  </EmptyState>

  <template v-else-if="d">
    <div class="stat-grid">
      <div v-for="(s, i) in STATS" :key="s.lb" class="stat" :class="{ 'stat-dark': s.hot }" :style="{ animationDelay: i * 70 + 'ms' }">
        <div class="stat-top">
          <span class="lb">{{ s.lb }}{{ st.range !== 'today' ? `（${st.range === 'last7' ? '7天' : '30天'}）` : '' }}</span>
          <span v-if="s.pct != null" class="delta" :class="s.pct >= 0 ? 'up' : 'down'" title="近 7 天环比（近 7 天 vs 前 7 天），与所选时间窗无关">
            {{ s.pct >= 0 ? '▲' : '▼' }} {{ Math.abs(s.pct) }}%<i style="font-style:normal;font-weight:500;margin-left:3px">近7天</i>
          </span>
          <span v-else-if="s.note" class="delta">{{ s.note }}</span>
        </div>
        <div class="vl">{{ s.vl }}</div>
        <!-- 14 天迷你柱状图（rose-light 柱 + 末柱 plum） -->
        <div v-if="s.series && spark[s.series].length" class="spark" aria-hidden="true">
          <div
            v-for="(v, j) in spark[s.series]" :key="j"
            class="spark-bar"
            :class="{ last: j === spark[s.series].length - 1 }"
            :style="{ height: sparkH(spark[s.series], j) }"
          ></div>
        </div>
      </div>
    </div>

    <!-- 14 天 GMV 柱状图 -->
    <div class="card card-lift" style="padding:20px;margin-top:18px">
      <div class="dhead">
        <h3 class="dtitle">GMV · 近 14 天</h3>
        <div v-if="daily.length" class="dhead-meta">
          <span>总计 <b>{{ money(dailyTotal) }}</b></span>
          <span>日均 <b>{{ money(dailyAvg) }}</b></span>
        </div>
      </div>
      <EmptyState v-if="!daily.length" icon="📉" title="近 14 天暂无成交数据" sub="有订单成交后这里会亮起来" />
      <div v-else class="chart" @mouseleave="hoverBar = null">
        <div class="chart-grid" aria-hidden="true"></div>
        <div v-for="(x, i) in daily" :key="i" class="chart-col">
          <div v-if="hoverBar === i" class="chart-tip" :style="{ bottom: `calc(24px + ${barH(x)} + 10px)` }">
            {{ dayLabel(x.date) }} · <b>{{ money(x.gmv_cents) }}</b> · {{ x.orders || 0 }} 单
          </div>
          <div
            class="chart-bar"
            :class="{ last: i === daily.length - 1, dim: hoverBar != null && hoverBar !== i, hot: hoverBar === i }"
            :style="{ height: barH(x), animationDelay: i * 35 + 'ms' }"
            @mouseenter="hoverBar = i"
          ></div>
          <!-- x 轴标签隔 1 显示，避免 14 根柱标签挤压 -->
          <div class="chart-x">{{ i % 2 === 0 ? dayLabel(x.date) : '' }}</div>
        </div>
      </div>
    </div>

    <div class="grid-2" style="margin-top:18px;align-items:start">
      <!-- 待办（链接带预填筛选：待发货→orders?status=1 等） -->
      <div class="card card-lift" style="padding:20px">
        <div class="dhead"><h3 class="dtitle">待处理事项</h3></div>
        <div class="todo-list">
          <router-link class="todo-row" to="/orders?status=1,2">
            <span class="todo-ico">📦</span>
            <span class="todo-txt">待发货订单<i class="todo-arrow">→</i></span>
            <b class="todo-cnt" :class="(d.pending_orders ?? 0) > 0 ? 'c-on' : ''">{{ d.pending_orders ?? 0 }}</b>
          </router-link>
          <router-link class="todo-row" to="/content">
            <span class="todo-ico">⭐</span>
            <span class="todo-txt">待审评价<i class="todo-arrow">→</i></span>
            <b class="todo-cnt" :class="(d.pending_reviews ?? 0) > 0 ? 'c-on' : ''">{{ d.pending_reviews ?? 0 }}</b>
          </router-link>
          <router-link class="todo-row" to="/tickets">
            <span class="todo-ico">💬</span>
            <span class="todo-txt">未关工单<i class="todo-arrow">→</i></span>
            <b class="todo-cnt" :class="(d.open_tickets ?? 0) > 0 ? 'c-on' : ''">{{ d.open_tickets ?? 0 }}</b>
          </router-link>
          <router-link class="todo-row" to="/inventory">
            <span class="todo-ico">⚠️</span>
            <span class="todo-txt">低库存 SKU<i class="todo-arrow">→</i></span>
            <b class="todo-cnt c-err">{{ d.low_stock ?? 0 }}</b>
          </router-link>
          <div class="todo-row is-plain">
            <span class="todo-ico">🛒</span>
            <span class="todo-txt">24h 弃购车</span>
            <b class="todo-cnt">{{ d.abandoned_carts ?? 0 }}</b>
          </div>
        </div>
        <!-- 快捷入口（待支付用看板 unpaid_orders 计数；待审退货直达预填筛选） -->
        <div class="quick-row">
          <router-link class="quick-chip" to="/orders?status=0">待支付订单 {{ d.unpaid_orders ?? 0 }} →</router-link>
          <router-link class="quick-chip" to="/returns?tab=rma&rs=s0">待审退货 →</router-link>
        </div>
        <div v-if="lowStockTop.length" class="lstock">
          <div class="lstock-title" title="库存 ≤ max(安全库存, 8) 的在售变体">最缺货 Top {{ lowStockTop.length }}（低库存）</div>
          <div v-for="v in lowStockTop" :key="v.sku" class="lstock-row">
            <span class="lstock-name" :title="v.sku + ' · ' + v.title">{{ v.sku }} · {{ v.title }}</span>
            <b class="lstock-badge" :class="(v.stock || 0) <= 3 ? 'b-err' : 'b-warn'">余 {{ v.stock ?? 0 }}</b>
          </div>
        </div>
        <div v-if="reconcile" class="recon">
          对账 {{ reconcile.reconcile_date }}：
          <span :style="{ color: reconcile.diff_payment > 0 ? 'var(--error)' : 'var(--success)' }" title="支付差额，非 0 需人工核对">支付 diff {{ money(reconcile.diff_payment) }}{{ reconcile.diff_payment > 0 ? ' ⚠️' : '' }}</span> ·
          <span :style="{ color: reconcile.diff_points > 0 ? 'var(--error)' : 'var(--success)' }" title="积分差额，非 0 需人工核对">积分 diff {{ reconcile.diff_points }} 分{{ reconcile.diff_points > 0 ? ' ⚠️' : '' }}</span>
        </div>
      </div>

      <!-- 漏斗（四级分层配色 rose-light→rose→plum→plum-dark + 步间转化率徽标） -->
      <div class="card card-lift" style="padding:20px">
        <div class="dhead">
          <h3 class="dtitle">转化漏斗</h3>
          <span v-if="funnel.approximate" class="approx-tag">近似</span>
        </div>
        <template v-for="(s, i) in funnel.steps" :key="s.label">
          <div v-if="i > 0" class="funnel-step">
            <span class="step-badge" :title="`本步 ${s.n} / 上步 ${funnel.steps[i - 1].n}`">↓ {{ s.step }}%</span>
          </div>
          <div class="fstep-row">
            <span class="fstep-label">{{ s.label }}</span>
            <div class="fstep-main">
              <div class="fbar" :style="{ width: Math.max(2, (s.n / funnel.max) * 78) + '%', background: FUNNEL_COLORS[i] }"></div>
              <b class="fnum">{{ s.n }}</b>
              <small class="fglobal">全局 {{ s.global }}%</small>
            </div>
          </div>
        </template>
        <div class="funnel-foot">
          <span>浏览 → 支付</span>
          <span>整体转化 <b>{{ funnelOverall }}%</b></span>
        </div>
      </div>
    </div>

    <!-- 热销榜 -->
    <div class="card card-lift" style="padding:20px;margin-top:18px">
      <div class="dhead"><h3 class="dtitle">热销 Top 5</h3></div>
      <div v-if="topProducts.length" class="plist">
        <div v-for="(p, i) in topProducts" :key="p.id || i" class="prow">
          <b class="rank" :class="'rank-' + (i + 1)">{{ i + 1 }}</b>
          <div class="pmain">
            <div class="ptitle">{{ p.title }}</div>
            <div class="ptrack"><div class="pfill" :style="{ width: Math.max(4, (soldOf(p) / maxSold) * 100) + '%' }"></div></div>
          </div>
          <span class="psold">售出 <b>{{ soldOf(p) }}</b></span>
        </div>
      </div>
      <EmptyState v-else icon="🏆" title="暂无热销数据" sub="有成交后这里会展示 Top 5" />
    </div>
  </template>
  <div v-else class="card skeleton" style="min-height:300px" />
</template>

<style scoped>
/* ===== 顶栏 ===== */
.dash-h1{font-family:var(--font-title);font-size:22px;font-weight:700;letter-spacing:-.3px}
.dash-sub{font-size:12.5px;color:var(--gray)}
.dash-actions{display:flex;gap:10px;align-items:center}

/* ===== KPI 卡 ===== */
.stat{position:relative;overflow:hidden;animation:dashRise .45s ease-out backwards}
.stat::before{content:"";position:absolute;top:-30px;right:-30px;width:130px;height:110px;border-radius:50%;background:radial-gradient(closest-side,rgba(232,180,184,.16),transparent);pointer-events:none}
.stat-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.stat .vl{font-size:26px;margin-top:6px;letter-spacing:-.3px}
.stat .delta{margin-top:0;font-size:11.5px;font-weight:700;padding:2px 9px;border-radius:999px;background:var(--gray-light);color:var(--gray);font-variant-numeric:tabular-nums;white-space:nowrap}
.stat .delta.up{background:var(--pale-success);color:var(--success)}
.stat .delta.down{background:var(--pale-error);color:var(--error)}
/* 待处理卡：品牌深色渐变，反白强调 */
.stat-dark{background:linear-gradient(135deg,var(--plum) 0%,var(--plum-dark) 100%);border:none;box-shadow:0 8px 20px rgba(138,74,99,.28)}
.stat-dark::before{background:radial-gradient(closest-side,rgba(232,180,184,.28),transparent)}
.stat-dark .lb{color:rgba(255,255,255,.78)}
.stat-dark .vl{color:#fff}
.stat-dark .delta{background:rgba(255,255,255,.16);color:rgba(255,255,255,.92)}
/* KPI 卡迷你柱状图（rose-light 柱 + 末柱 plum） */
.spark{display:flex;align-items:flex-end;gap:2px;height:14px;margin-top:12px}
.spark-bar{flex:1;min-width:2px;border-radius:2px 2px 0 0;background:var(--rose-light);transition:height .4s}
.spark-bar.last{background:var(--plum)}

/* ===== 卡片标题（品牌渐变竖标） ===== */
.dhead{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}
.dtitle{font-size:15px;font-weight:700;display:flex;align-items:center;gap:8px}
.dtitle::before{content:"";width:4px;height:16px;border-radius:2px;background:linear-gradient(180deg,var(--rose),var(--plum));flex:none}
.dhead-meta{display:flex;gap:16px;font-size:12px;color:var(--gray);white-space:nowrap}
.dhead-meta b{color:var(--plum);font-variant-numeric:tabular-nums}

/* ===== GMV 柱状图 ===== */
.chart{position:relative;display:flex;align-items:flex-end;gap:6px;height:190px;margin-top:14px}
/* 四分位横向网格线（底部 24px 为 x 轴标签区） */
.chart-grid{position:absolute;left:0;right:0;top:0;bottom:24px;pointer-events:none;
  background:repeating-linear-gradient(to top,transparent 0,transparent calc(25% - 1px),var(--gray-light) calc(25% - 1px),var(--gray-light) 25%)}
.chart-col{flex:1;min-width:0;height:100%;position:relative;display:flex;flex-direction:column;justify-content:flex-end}
.chart-bar{width:100%;border-radius:6px 6px 0 0;cursor:pointer;transform-origin:bottom;animation:barGrow .5s ease-out backwards;
  background:linear-gradient(180deg,var(--rose) 0%,var(--rose-light) 100%);
  transition:opacity .15s,filter .15s,box-shadow .15s}
.chart-bar.last{background:linear-gradient(180deg,var(--plum) 0%,var(--plum-dark) 100%);box-shadow:0 4px 14px rgba(138,74,99,.3)}
.chart-bar.dim{opacity:.4}
.chart-bar.hot{opacity:1;filter:saturate(1.2) brightness(1.03);box-shadow:0 6px 16px rgba(138,74,99,.22)}
.chart-x{height:16px;margin-top:8px;font-size:10px;color:var(--gray);text-align:center;line-height:16px;white-space:nowrap}
/* hover 浮层提示（替代原生 title） */
.chart-tip{position:absolute;left:50%;transform:translateX(-50%);z-index:6;pointer-events:none;white-space:nowrap;
  background:var(--ink);color:#fff;font-size:11px;line-height:1;padding:7px 11px;border-radius:8px;box-shadow:var(--shadow-pop)}
.chart-tip b{color:var(--rose)}

/* ===== 待办列表 ===== */
.todo-list{display:grid;gap:2px;font-size:13.5px}
.todo-row{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;border-bottom:1px solid var(--gray-light);transition:background .15s}
.todo-row:hover{background:var(--rose-pale)}
.todo-row.is-plain{cursor:default}
.todo-row.is-plain:hover{background:transparent}
.todo-ico{width:30px;height:30px;border-radius:9px;background:var(--rose-pale);display:inline-flex;align-items:center;justify-content:center;font-size:14px;flex:none}
.todo-txt{flex:1;min-width:0}
.todo-arrow{display:inline-block;margin-left:6px;font-style:normal;color:var(--plum);opacity:0;transform:translateX(-4px);transition:opacity .18s,transform .18s}
.todo-row:hover .todo-arrow{opacity:1;transform:none}
.todo-cnt{min-width:26px;text-align:center;padding:2px 9px;border-radius:999px;background:var(--gray-light);color:var(--gray);font-size:12px;font-weight:700;font-variant-numeric:tabular-nums;flex:none}
.todo-cnt.c-on{background:var(--rose-pale);color:var(--plum)}
.todo-cnt.c-err{background:var(--pale-error);color:var(--error)}
/* 快捷入口 chips */
.quick-row{display:flex;gap:8px;margin-top:12px}
.quick-chip{font-size:12px;font-weight:600;color:var(--plum);border:1px solid var(--gray-light);border-radius:999px;padding:4px 13px;transition:all .15s}
.quick-chip:hover{border-color:var(--rose);background:var(--rose-pale)}
/* 最缺货 Top 5 + 对账 */
.lstock{margin-top:14px;padding-top:12px;border-top:1px dashed var(--gray-light)}
.lstock-title{font-size:12px;color:var(--gray);margin-bottom:6px}
.lstock-row{display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:12.5px;padding:5px 0}
.lstock-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lstock-badge{flex:none;font-size:11.5px;padding:1px 9px;border-radius:999px;font-variant-numeric:tabular-nums}
.lstock-badge.b-err{background:var(--pale-error);color:var(--error)}
.lstock-badge.b-warn{background:var(--pale-warn);color:var(--warn)}
.recon{margin-top:12px;padding-top:12px;border-top:1px dashed var(--gray-light);font-size:12.5px;color:var(--gray)}

/* ===== 漏斗 ===== */
.approx-tag{font-size:11px;color:var(--gray);background:var(--gray-light);padding:2px 9px;border-radius:999px}
.fstep-row{display:flex;align-items:center;gap:12px;margin:7px 0}
.fstep-label{width:52px;font-size:13px;color:var(--gray);text-align:right;flex:none}
.fstep-main{flex:1;display:flex;align-items:center;gap:9px;min-width:0}
.fbar{height:26px;border-radius:8px;flex:none;box-shadow:inset 0 1px 0 rgba(255,255,255,.25);transition:width .45s ease-out}
.fnum{font-size:13.5px;color:var(--plum);font-variant-numeric:tabular-nums}
.fglobal{color:var(--gray);font-size:11.5px;white-space:nowrap}
.funnel-step{display:flex;justify-content:flex-start;padding-left:64px;margin:-2px 0}
.step-badge{font-size:10.5px;font-weight:700;color:var(--plum);background:var(--rose-pale);border:1px solid var(--rose-light);border-radius:999px;padding:1px 8px}
.funnel-foot{margin-top:12px;padding-top:12px;border-top:1px dashed var(--gray-light);font-size:12.5px;color:var(--gray);display:flex;justify-content:space-between}
.funnel-foot b{color:var(--plum);font-size:13.5px}

/* ===== 热销榜 ===== */
.plist{display:grid;gap:4px}
.prow{display:flex;align-items:center;gap:12px;font-size:13.5px;padding:10px 0;border-bottom:1px solid var(--gray-light)}
.prow:last-child{border-bottom:none}
.rank{width:26px;height:26px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;font-family:var(--font-title);font-size:14px;flex:none;background:var(--gray-light);color:var(--gray)}
.rank-1{background:linear-gradient(135deg,#D9B44A,var(--gold));color:#fff;box-shadow:0 3px 8px rgba(201,162,39,.35)}
.rank-2{background:var(--rose);color:#fff}
.rank-3{background:var(--rose-light);color:var(--plum)}
.pmain{flex:1;min-width:0}
.ptitle{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ptrack{height:5px;border-radius:3px;background:var(--gray-light);margin-top:7px;overflow:hidden}
.pfill{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--rose),var(--plum));transition:width .4s ease-out}
.psold{color:var(--gray);white-space:nowrap;font-variant-numeric:tabular-nums}
.psold b{color:var(--plum)}

/* ===== 入场动画（fill backwards，结束后不锁 transform，与 hover 上浮兼容） ===== */
.card-lift{animation:dashRise .5s ease-out .1s backwards}
@keyframes dashRise{from{opacity:0;transform:translateY(10px)}}
@keyframes barGrow{from{transform:scaleY(0)}}
</style>
