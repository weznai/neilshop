<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../../api/client'
import { fmtDate, fmtDateTime } from '../../composables/datetime'
import { money } from '../../composables/format'
import { i18n, tt } from '../../i18n'

const route = useRoute()
const router = useRouter()

/* 积分流水原因 → [en, zh]（文案对齐 server member/service_points.py REASON_TEXT；未知 code 回落后端原文） */
const REASON = {
  1: ['Order earned (frozen)', '下单获得（冻结中）'],
  2: ['Unfrozen', '解冻'],
  3: ['Review reward', '评价奖励'],
  4: ['Check-in', '签到'],
  5: ['Referral reward', '推荐奖励'],
  6: ['Birthday gift', '生日礼'],
  7: ['Redeemed at checkout', '消费扣除'],
  8: ['Voided on refund', '退款作废'],
  9: ['Returned from refund', '退款返还'],
  10: ['Expired', '过期'],
  11: ['Admin adjustment', '管理员调整'],
  12: ['Gallery look reward', '买家秀奖励'],
}
function reasonText(h) {
  const row = REASON[h.reason_code]
  return row ? tt(row[0], row[1]) : (h.reason || String(h.reason_code ?? ''))
}

const pts = ref(null)
const ledger = ref([])
const total = ref(0)
const size = 20
const expiring = ref([])
const loaded = ref(false)
/* 余额与流水分别标记失败：仅流水失败时余额照常展示，流水卡内重试 */
const ptsFailed = ref(false)
const ledgerFailed = ref(false)
/* page ↔ route.query（replace）：刷新/回退不丢状态 */
const page = ref(Math.max(1, Number(route.query.page) || 1))

const fmt = fmtDateTime

async function load() {
  ptsFailed.value = false
  ledgerFailed.value = false
  const [s, l, e] = await Promise.allSettled([
    req('GET', '/api/points'),
    req('GET', '/api/points/ledger?page=' + page.value + '&size=' + size),
    req('GET', '/api/points/expiring'),
  ])
  if (s.status === 'fulfilled') pts.value = s.value
  if (l.status === 'fulfilled') {
    ledger.value = l.value.items || []
    total.value = l.value.total || 0
    if (page.value > pages.value && pages.value > 0) { page.value = 1; syncQuery(); load(); return }
  }
  if (e.status === 'fulfilled') expiring.value = (e.value.items || []).filter((r) => (r.change || 0) > 0)
  ptsFailed.value = s.status === 'rejected'
  ledgerFailed.value = l.status === 'rejected'
  loaded.value = true
}
onMounted(load)

const pages = computed(() => Math.max(1, Math.ceil(total.value / size)))
function syncQuery() {
  const query = Object.assign({}, route.query)
  if (page.value > 1) query.page = String(page.value)
  else delete query.page
  router.replace({ query })
}
function go(p) {
  if (p < 1 || p > pages.value || p === page.value) return
  page.value = p
  syncQuery()
  load()
}
/* 浏览器回退/前进（同路由 query 变化）时恢复页码 */
watch(() => route.query, (q) => {
  if (route.name !== 'account-points') return
  const np = Math.max(1, Number(q.page) || 1)
  if (np !== page.value) { page.value = np; load() }
})

/* 规则口径与后端一致：$1=10 分（下单冻结）；100 分=$1；评价 +10；推荐 +1000 */
const RULES = [
  [['Order spend', '下单消费'], ['+10 pts per $1 (unfreezes after delivery)', '每 $1 +10 分（确认收货后解冻）']],
  [['Write a review', '写商品评价'], ['+10 pts', '+10 分']],
  [['Refer a friend who orders', '推荐好友注册并下单'], ['+1000 pts', '+1000 分']],
  [['Birthday month', '生日月福利'], ['points gift', '积分小礼物']],
]
</script>

<template>
  <div style="display:grid;gap:16px">
    <div class="card" style="padding:24px;background:linear-gradient(135deg,var(--plum-dark),var(--ink));color:#fff">
      <div style="font-size:12.5px;opacity:.75;letter-spacing:1px">GLOW POINTS</div>
      <div style="display:flex;gap:26px;flex-wrap:wrap;align-items:flex-end">
        <div>
          <div style="font-family:var(--font-title);font-size:44px;margin:6px 0">
            {{ pts ? (pts.usable || 0).toLocaleString() : '—' }}
          </div>
          <div style="font-size:13px;opacity:.85">{{ tt('Usable · 100 pts = $1, worth', '可用 · 100 分 = $1，结账时可抵') }} {{ pts ? money(pts.usable) : '—' }}</div>
        </div>
        <div style="text-align:left;padding-bottom:6px">
          <div style="font-size:22px;font-weight:700">{{ pts ? (pts.balance || 0).toLocaleString() : '—' }}</div>
          <div style="font-size:12px;opacity:.75">{{ tt('Total', '总积分') }}</div>
        </div>
        <div style="text-align:left;padding-bottom:6px">
          <div style="font-size:22px;font-weight:700;color:var(--rose-light)">{{ pts ? (pts.frozen || 0).toLocaleString() : '—' }}</div>
          <div style="font-size:12px;opacity:.75">{{ tt('Frozen', '冻结中') }}</div>
        </div>
      </div>
      <div v-if="ptsFailed" style="font-size:12.5px;margin-top:10px">
        {{ tt('Load failed —', '加载失败 ——') }} <a href="javascript:void(0)" style="color:#fff;text-decoration:underline" @click="load">{{ tt('retry', '重试') }}</a>
      </div>
    </div>

    <!-- 即将过期提醒（日期 chip 化） -->
    <div v-if="expiring.length" class="card" style="padding:16px 18px;border-left:4px solid var(--warn);display:flex;gap:12px;align-items:flex-start">
      <span style="font-size:18px">⏳</span>
      <div style="font-size:13px;line-height:1.8">
        <b>{{ tt('Points expiring soon', '积分即将过期') }}</b>
        <div v-for="(r, i) in expiring.slice(0, 3)" :key="i" class="exp-row">
          +{{ r.change }} {{ tt('pts ·', '分 ·') }} <span class="exp-chip">{{ fmtDate(r.expires_at) }}</span> {{ tt('expires', '过期') }}（{{ reasonText(r) }}）
        </div>
        <div v-if="expiring.length > 3" style="color:var(--gray);font-size:12px">
          {{ tt(`+ ${expiring.length - 3} more — see details in points history`, `还有 ${expiring.length - 3} 笔——详见积分流水`) }}
        </div>
      </div>
    </div>

    <div class="grid grid-2">
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">{{ tt('How points work', '积分规则') }}</h3>
        <div v-for="[a, b] in RULES" :key="a[1]" style="display:flex;justify-content:space-between;gap:10px;font-size:13.5px;padding:8px 0;border-bottom:1px solid var(--gray-light)">
          <span>{{ tt(a[0], a[1]) }}</span><b style="color:var(--plum);text-align:right">{{ tt(b[0], b[1]) }}</b>
        </div>
        <div style="font-size:12px;color:var(--gray);margin-top:10px">{{ tt('Points from orders are frozen first, and unfreeze automatically once the order completes / the return window passes.', '下单获得的积分先冻结，订单完成/过退货期后自动解冻可用。') }}</div>
      </div>

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">{{ tt('Points history', '积分流水') }}</h3>
        <div v-if="!loaded" class="skeleton" style="min-height:120px" />
        <div v-else-if="ledgerFailed" style="font-size:13.5px;color:var(--gray)">
          {{ tt('Load failed —', '加载失败 ——') }} <a href="javascript:void(0)" style="color:var(--plum)" @click="load">{{ tt('retry', '重试') }}</a>
        </div>
        <template v-else>
          <div v-if="ledger.length" style="display:grid;gap:2px;max-height:300px;overflow-y:auto">
            <div v-for="h in ledger" :key="h.id" style="display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:6px 0;border-bottom:1px dashed var(--gray-light)">
              <span style="min-width:0">
                <span style="color:var(--gray)">{{ fmt(h.created_at) }}</span> · {{ reasonText(h) }}
                <span v-if="h.frozen === 1 && h.change > 0" class="tag tag-pending" style="margin-left:4px">{{ tt('Frozen', '冻结中') }}</span>
                <span v-if="h.expires_at" class="exp-chip" style="margin-left:4px">{{ fmtDate(h.expires_at) }}</span>
              </span>
              <span style="text-align:right;flex:none">
                <b class="pl-amount" :class="(h.change || 0) >= 0 ? 'in' : 'out'">
                  {{ (h.change || 0) >= 0 ? '+' : '' }}{{ h.change }}
                </b>
                <div class="pl-bal">{{ tt('Balance', '余额') }} {{ h.balance_after }}</div>
              </span>
            </div>
          </div>
          <!-- 分页控件置于滚动容器外：不滚到底也可见 -->
          <div v-if="ledger.length && pages > 1" style="display:flex;gap:8px;align-items:center;justify-content:center;padding-top:10px">
            <button class="btn btn-secondary btn-sm" :disabled="page <= 1" @click="go(page - 1)">←</button>
            <span style="font-size:12.5px;color:var(--gray)">{{ tt(`Page ${page} / ${pages}`, `第 ${page} / ${pages} 页`) }}</span>
            <button class="btn btn-secondary btn-sm" :disabled="page >= pages" @click="go(page + 1)">→</button>
          </div>
          <div v-else style="font-size:13.5px;color:var(--gray)">{{ tt('No points yet — place an order to start earning ✨', '暂无积分记录，下单即可开始攒分 ✨') }}</div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 流水金额：+绿/−红 右对齐等宽数字 */
.pl-amount { font-variant-numeric: tabular-nums; font-size: 14px; }
.pl-amount.in { color: var(--success); }
.pl-amount.out { color: var(--error); }
.pl-bal { font-size: 11px; color: var(--gray); font-variant-numeric: tabular-nums; }
/* 过期日期 chip */
.exp-row { color: var(--gray); display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.exp-chip { display: inline-block; background: var(--pale-warn); color: var(--warn); font-weight: 700; font-size: 12px; border-radius: 999px; padding: 1px 10px; font-variant-numeric: tabular-nums; }
</style>
