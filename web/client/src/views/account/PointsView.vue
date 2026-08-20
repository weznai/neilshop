<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { req } from '../../api/client'

const route = useRoute()
const router = useRouter()

const pts = ref(null)
const ledger = ref([])
const total = ref(0)
const size = 20
const expiring = ref([])
const loaded = ref(false)
const failed = ref(false)
/* page ↔ route.query（replace）：刷新/回退不丢状态 */
const page = ref(Math.max(1, Number(route.query.page) || 1))

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)
function fmt(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d)) return '—'
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

async function load() {
  failed.value = false
  const [s, l, e] = await Promise.allSettled([
    req('GET', '/api/points'),
    req('GET', '/api/points/ledger?page=' + page.value + '&size=' + size),
    req('GET', '/api/points/expiring'),
  ])
  if (s.status === 'fulfilled') pts.value = s.value
  if (l.status === 'fulfilled') {
    ledger.value = l.value.items || []
    total.value = l.value.total || 0
  }
  if (e.status === 'fulfilled') expiring.value = (e.value.items || []).filter((r) => (r.change || 0) > 0)
  failed.value = s.status === 'rejected' && l.status === 'rejected'
  loaded.value = true
}
onMounted(load)

const pages = () => Math.max(1, Math.ceil(total.value / size))
function syncQuery() {
  const query = Object.assign({}, route.query)
  if (page.value > 1) query.page = String(page.value)
  else delete query.page
  router.replace({ query })
}
function go(p) {
  if (p < 1 || p > pages() || p === page.value) return
  page.value = p
  syncQuery()
  load()
}
/* 浏览器回退/前进（同路由 query 变化）时恢复页码 */
watch(() => route.query, (q) => {
  const np = Math.max(1, Number(q.page) || 1)
  if (np !== page.value) { page.value = np; load() }
})

/* 规则口径与后端一致：$1=10 分（下单冻结）；100 分=$1；评价 +100；推荐 +1000 */
const RULES = [
  ['下单消费', '每 $1 +10 分（确认收货后解冻）'],
  ['写商品评价', '+100 分'],
  ['推荐好友注册并下单', '+1000 分'],
  ['生日月福利', '积分小礼物'],
]
</script>

<template>
  <div style="display:grid;gap:16px">
    <div class="card" style="padding:24px;background:linear-gradient(135deg,#2E1430,var(--ink));color:#fff">
      <div style="font-size:12.5px;opacity:.75;letter-spacing:1px">GLOW POINTS</div>
      <div style="display:flex;gap:26px;flex-wrap:wrap;align-items:flex-end">
        <div>
          <div style="font-family:var(--font-title);font-size:44px;margin:6px 0">
            {{ pts ? (pts.usable || 0).toLocaleString() : '—' }}
          </div>
          <div style="font-size:13px;opacity:.85">可用 · 100 分 = $1，结账时可抵 {{ pts ? money(pts.usable) : '—' }}</div>
        </div>
        <div style="text-align:left;padding-bottom:6px">
          <div style="font-size:22px;font-weight:700">{{ pts ? (pts.balance || 0).toLocaleString() : '—' }}</div>
          <div style="font-size:12px;opacity:.75">总积分</div>
        </div>
        <div style="text-align:left;padding-bottom:6px">
          <div style="font-size:22px;font-weight:700;color:#F2C4CE">{{ pts ? (pts.frozen || 0).toLocaleString() : '—' }}</div>
          <div style="font-size:12px;opacity:.75">冻结中</div>
        </div>
      </div>
    </div>

    <!-- 即将过期提醒 -->
    <div v-if="expiring.length" class="card" style="padding:16px 18px;border-left:4px solid var(--warn);display:flex;gap:12px;align-items:flex-start">
      <span style="font-size:18px">⏳</span>
      <div style="font-size:13px;line-height:1.8">
        <b>积分即将过期</b>
        <div v-for="(r, i) in expiring.slice(0, 3)" :key="i" style="color:var(--gray)">
          +{{ r.change }} 分将于 <b style="color:var(--warn)">{{ fmtDate(r.expires_at) }}</b> 过期（{{ r.reason }}）
        </div>
      </div>
    </div>

    <div class="grid grid-2">
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">积分规则</h3>
        <div v-for="[a, b] in RULES" :key="a" style="display:flex;justify-content:space-between;gap:10px;font-size:13.5px;padding:8px 0;border-bottom:1px solid var(--gray-light)">
          <span>{{ a }}</span><b style="color:var(--plum);text-align:right">{{ b }}</b>
        </div>
        <div style="font-size:12px;color:var(--gray);margin-top:10px">下单获得的积分先冻结，订单完成/过退货期后自动解冻可用。</div>
      </div>

      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">积分流水</h3>
        <div v-if="!loaded" class="skeleton" style="min-height:120px" />
        <div v-else-if="failed" style="font-size:13.5px;color:var(--gray)">加载失败，请刷新重试</div>
        <template v-else>
          <div v-if="ledger.length" style="display:grid;gap:2px;max-height:300px;overflow-y:auto">
            <div v-for="h in ledger" :key="h.id" style="display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:6px 0;border-bottom:1px dashed var(--gray-light)">
              <span style="min-width:0">
                <span style="color:var(--gray)">{{ fmt(h.created_at) }}</span> · {{ h.reason }}
                <span v-if="h.frozen === 1 && h.change > 0" class="tag tag-pending" style="margin-left:4px">冻结中</span>
              </span>
              <span style="text-align:right;flex:none">
                <b :style="{ color: (h.change || 0) >= 0 ? 'var(--success)' : 'var(--error)' }">
                  {{ (h.change || 0) >= 0 ? '+' : '' }}{{ h.change }}
                </b>
                <div style="font-size:11px;color:var(--gray)">余额 {{ h.balance_after }}</div>
              </span>
            </div>
            <div v-if="pages() > 1" style="display:flex;gap:8px;align-items:center;justify-content:center;padding-top:10px">
              <button class="btn btn-secondary btn-sm" :disabled="page <= 1" @click="go(page - 1)">←</button>
              <span style="font-size:12.5px;color:var(--gray)">第 {{ page }} / {{ pages() }} 页</span>
              <button class="btn btn-secondary btn-sm" :disabled="page >= pages()" @click="go(page + 1)">→</button>
            </div>
          </div>
          <div v-else style="font-size:13.5px;color:var(--gray)">暂无积分记录，下单即可开始攒分 ✨</div>
        </template>
      </div>
    </div>
  </div>
</template>
