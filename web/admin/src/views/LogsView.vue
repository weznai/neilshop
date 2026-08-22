<script setup>
/* 审计日志：GET /api/admin/ops/logs（entity/action/admin_id/start/end 筛选；
 * 响应缺 admin_name 时回退 #admin_id） */
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { dt } from '../composables/format'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const items = ref([])
const total = ref(0)
const SIZE = 20
const loaded = ref(false)
const loadErr = ref(false)

/* 筛选项（entity 集合与后端 AdminLog 写入方一致）+ page 一并入 URL 同步 */
const f = reactive({ entity: '', action: '', admin_id: '', start: '', end: '', page: 1 })
useQuerySync(f, { nums: ['page'], defaults: { page: 1 } })

const ENTITY_META = {
  order: '订单', return: '退货', exchange: '换货', product: '商品', variant: '变体',
  product_translation: '商品翻译', ticket: '工单', member: '会员', review: '评价', ugc: 'UGC',
  article: '文章', faq: 'FAQ', discount: '折扣', popup: '弹窗', setting: '设置',
  shipping_rate: '运费', collection: '集合',
}
/* entity 徽标配色：每个域一个色相（hex 前缀，透明度后缀拼接） */
const ENTITY_COLOR = {
  order: '#6D2E46', return: '#B4453F', exchange: '#C0552F', product: '#2F6D4F', variant: '#3F7A5A',
  product_translation: '#4E7A57', ticket: '#3C5A9A', member: '#7A4A8F', review: '#A8456B', ugc: '#8A6D1B',
  article: '#4A6B8A', faq: '#5F6B7A', discount: '#2F5D8A', popup: '#8F4A5F', setting: '#555B66',
  shipping_rate: '#2F6D6B', collection: '#9A5B2F',
}
const entLabel = (e) => ENTITY_META[e] || e
const badgeStyle = (e) => {
  const c = ENTITY_COLOR[e] || '#7A6A70'
  return { background: c + '14', color: c, border: '1px solid ' + c + '30' }
}

/* action 徽标语义色：create/approve/publish=绿，update/toggle/ship=蓝，delete/reject/refund=红，其余中性 */
const ACTION_TONE = {
  create: 'tag-paid', approve: 'tag-paid', publish: 'tag-paid',
  update: 'tag-ship', toggle: 'tag-ship', ship: 'tag-ship',
  delete: 'tag-error', reject: 'tag-error', refund: 'tag-error',
}
const actClass = (a) => ACTION_TONE[a] || 'tag-done'
/* action 输入联想：域内常见动作 */
const ACTIONS = ['refund', 'publish', 'unpublish', 'ship', 'close', 'assign', 'reply', 'risk', 'upsert', 'approve', 'reject']

/* entity 行跳转：按实体域映射到对应管理页（无映射的保持纯文本） */
const ENT_ROUTE = {
  order: () => ({ path: '/orders' }),
  return: () => ({ path: '/returns', query: { tab: 'rma' } }),
  exchange: () => ({ path: '/returns', query: { tab: 'exch' } }),
  product: (id) => ({ path: '/product-edit', query: { id } }),
  variant: (id) => ({ path: '/product-edit', query: { id } }),
  product_translation: (id) => ({ path: '/product-edit', query: { id } }),
  collection: () => ({ path: '/marketing', query: { tab: 'collections' } }),
  review: () => ({ path: '/content' }),
  ugc: () => ({ path: '/content' }),
  article: () => ({ path: '/content' }),
  faq: () => ({ path: '/content' }),
  ticket: () => ({ path: '/tickets' }),
  member: () => ({ path: '/members' }),
  discount: () => ({ path: '/marketing' }),
  popup: () => ({ path: '/marketing' }),
  setting: () => ({ path: '/settings' }),
}
const entLink = (l) => ENT_ROUTE[l.entity]?.(l.entity_id) || null

const pages = computed(() => Math.max(1, Math.ceil(total.value / SIZE)))

function buildUrl(p) {
  const params = new URLSearchParams({ page: p, size: SIZE })
  if (f.entity) params.set('entity', f.entity)
  if (f.action.trim()) params.set('action', f.action.trim())
  if (f.admin_id) params.set('admin_id', Math.round(Number(f.admin_id)))
  if (f.start) params.set('start', f.start)
  /* end 为日期选择器值：补当天末时刻，含边界日全天 */
  if (f.end) params.set('end', f.end + 'T23:59:59')
  return '/api/admin/ops/logs?' + params
}

async function load(p = 1) {
  loadErr.value = false
  try {
    const d = await req('GET', buildUrl(p))
    items.value = d.items || []
    total.value = d.total ?? 0
    f.page = d.page || p
  } catch (e) {
    loadErr.value = true
    toast('审计日志加载失败：' + (e.message || ''), 'error')
  }
  loaded.value = true
}
onMounted(() => load(f.page))

function apply() { load(1) }
function reset() {
  Object.assign(f, { entity: '', action: '', admin_id: '', start: '', end: '', page: 1 })
  load(1)
}

const pad2 = (n) => String(n).padStart(2, '0')
const fmtShort = (d) => `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
/* 含时刻的 ISO 串（末尾 Z/偏移保留原样，naive 按UTC理解） */
const ISO_DT_RE = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/
function parseIso(v) {
  const s = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(v) ? v : v.replace(' ', 'T') + 'Z'
  const d = new Date(s)
  return isNaN(d) ? null : d
}
/* diff 值人性化：13 位毫秒时间戳 / ISO 日期时间 → 本地化 MM-DD HH:mm；key 含 _at 兜底 */
function humanVal(key, v) {
  if (v == null) return v
  if (typeof v === 'number' && /^\d{13}$/.test(String(v))) return fmtShort(new Date(v))
  if (typeof v === 'string' && ISO_DT_RE.test(v)) {
    const d = parseIso(v)
    if (d) return fmtShort(d)
  }
  if (key.includes('_at')) {
    if (typeof v === 'number' && !isNaN(v)) return fmtShort(new Date(v))
    if (typeof v === 'string') {
      if (ISO_DATE_RE.test(v)) return v.slice(5)
      const d = parseIso(v)
      if (d) return fmtShort(d)
    }
  }
  return v
}
/* diff_json：update 型为 {field:{before,after}}，其余为平对象；逐值人性化后展示 */
function humanizeDiff(diff) {
  if (diff == null || typeof diff !== 'object' || Array.isArray(diff)) return diff
  const out = {}
  for (const [k, v] of Object.entries(diff)) {
    if (v && typeof v === 'object' && !Array.isArray(v) && ('before' in v || 'after' in v)) {
      out[k] = { before: humanVal(k, v.before), after: humanVal(k, v.after) }
    } else out[k] = humanVal(k, v)
  }
  return out
}
/* 摘要截断 + <details> 展开完整 JSON */
function diffText(v) {
  if (v == null) return ''
  const s = typeof v === 'string' ? v : JSON.stringify(v)
  return s.length > 72 ? s.slice(0, 72) + '…' : s
}
function diffFull(v) {
  if (v == null) return ''
  try { return typeof v === 'string' ? v : JSON.stringify(v, null, 2) } catch (_) { return String(v) }
}
/* 管理员：优先 admin_name（契约增强后），否则 #admin_id */
const adminName = (l) => l.admin_name || (l.admin_id ? '#' + l.admin_id : '—')
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">审计日志</h1>
      <span class="page-sub">管理员操作记录 · 共 {{ total }} 条</span>
    </div>
  </div>

  <!-- 筛选栏 -->
  <div class="card filter-bar" style="padding:14px 16px;margin-bottom:14px;align-items:flex-end">
    <div class="field" style="margin:0">
      <label>实体</label>
      <select v-model="f.entity" class="input" style="width:130px" @change="apply">
        <option value="">全部</option>
        <option v-for="(label, e) in ENTITY_META" :key="e" :value="e">{{ label }}（{{ e }}）</option>
      </select>
    </div>
    <div class="field" style="margin:0">
      <label>动作</label>
      <input v-model="f.action" class="input" style="width:140px" list="log-actions" placeholder="如 refund / publish" @keydown.enter="apply">
      <datalist id="log-actions">
        <option v-for="a in ACTIONS" :key="a" :value="a"></option>
      </datalist>
    </div>
    <div class="field" style="margin:0">
      <label>管理员 ID</label>
      <input v-model="f.admin_id" class="input" style="width:110px" type="number" min="1" placeholder="如 1" @keydown.enter="apply">
    </div>
    <div class="field" style="margin:0">
      <label>开始日期</label>
      <input v-model="f.start" class="input" style="width:150px" type="date" @change="apply">
    </div>
    <div class="field" style="margin:0">
      <label>结束日期</label>
      <input v-model="f.end" class="input" style="width:150px" type="date" @change="apply">
    </div>
    <button class="btn btn-secondary btn-sm" style="height:36px" @click="apply">筛选</button>
    <button class="btn btn-ghost btn-sm" style="height:36px" @click="reset">重置</button>
  </div>

  <div v-if="!loaded" class="card skeleton" style="min-height:280px" />

  <div v-else class="card tbl-wrap">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="padding:10px">时间</th><th>管理员</th><th>实体</th><th>动作</th><th>#ID</th><th>变更内容</th>
      </tr></thead>
      <tbody>
        <tr v-for="l in items" :key="l.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:10px;white-space:nowrap;color:var(--gray)">{{ dt(l.created_at) }}</td>
          <td style="white-space:nowrap">{{ adminName(l) }}</td>
          <td><span class="ent-badge" :style="badgeStyle(l.entity)">{{ entLabel(l.entity) }}</span></td>
          <td><span class="tag" :class="actClass(l.action)" style="font-size:11.5px">{{ l.action }}</span></td>
          <td>
            <router-link v-if="entLink(l)" :to="entLink(l)" title="跳转到对应管理页" style="color:var(--plum)"><b>#{{ l.entity_id }}</b> ↗</router-link>
            <b v-else>#{{ l.entity_id }}</b>
          </td>
          <td style="max-width:320px">
            <details v-if="l.diff_json != null">
              <summary style="cursor:pointer;color:var(--gray);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{{ diffText(humanizeDiff(l.diff_json)) }}</summary>
              <pre style="margin-top:6px;background:#F6F4F5;border-radius:8px;padding:10px;font-size:11.5px;line-height:1.6;max-height:260px;overflow:auto">{{ diffFull(humanizeDiff(l.diff_json)) }}</pre>
            </details>
            <span v-else style="color:var(--gray)">—</span>
          </td>
        </tr>
      </tbody>
    </table>
    <EmptyState v-if="loadErr" icon="⚠️" title="审计日志加载失败" sub="服务端可能未启动或会话已过期">
      <template #action><button class="btn btn-secondary btn-sm" @click="load(1)">重试</button></template>
    </EmptyState>
    <EmptyState v-else-if="!items.length" icon="🗒️" title="暂无匹配日志" sub="调整筛选条件后重试，或稍后再来看看" />
    <Pagination embed :page="f.page" :pages="pages" :total="total" unit="条" @go="load" />
  </div>
</template>

<style scoped>
.ent-badge{display:inline-block;font-size:11px;font-weight:600;border-radius:999px;padding:2px 10px;white-space:nowrap}
</style>
