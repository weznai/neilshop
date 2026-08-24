<script setup>
/* 审计日志：GET /api/admin/ops/logs（entity/action/admin_id/start/end 筛选；
 * 响应缺 admin_name 时回退 #admin_id） */
import { computed, onMounted, reactive, ref } from 'vue'
import { req } from '../api/client'
import { toast } from '../composables/toast'
import { dt } from '../composables/format'
import { csvCell, downloadCsv, fetchAllPages } from '../composables/exportCsv'
import { useQuerySync } from '../composables/useQuerySync'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const items = ref([])
const total = ref(0)
const SIZE = 20
const loaded = ref(false)
const loadErr = ref(false)
const errMsg = ref('')       /* 最近一次加载失败信息（空态 sub / 横幅文案） */

/* 筛选项（entity 集合与后端 AdminLog 写入方一致）+ page 一并入 URL 同步；
 * onPop：浏览器回退/前进导致 query 变化时重拉当前页（见 useQuerySync 外部导航同步） */
const f = reactive({ entity: '', action: '', admin_id: '', start: '', end: '', page: 1 })
useQuerySync(f, { nums: ['page'], defaults: { page: 1 }, onPop: () => load(f.page) })

const ENTITY_META = {
  order: '订单', return: '退货', exchange: '换货', product: '商品', variant: '变体',
  product_translation: '商品翻译', ticket: '工单', member: '会员', review: '评价', ugc: 'UGC',
  article: '文章', faq: 'FAQ', discount: '折扣', popup: '弹窗', setting: '设置',
  shipping_rate: '运费', collection: '集合', giftcard: '礼品卡', media: '媒体',
  admin: '管理员账号', data_request: '数据请求', chat_quick_replies: '快捷回复卡',
  llm_config: 'LLM 配置', llm_rag_reindex: 'RAG 重建',
}
/* entity 徽标配色：每个域一个色相（hex 前缀，透明度后缀拼接） */
const ENTITY_COLOR = {
  order: '#6D2E46', return: '#B4453F', exchange: '#C0552F', product: '#2F6D4F', variant: '#3F7A5A',
  product_translation: '#4E7A57', ticket: '#3C5A9A', member: '#7A4A8F', review: '#A8456B', ugc: '#8A6D1B',
  article: '#4A6B8A', faq: '#5F6B7A', discount: '#2F5D8A', popup: '#8F4A5F', setting: '#555B66',
  shipping_rate: '#2F6D6B', collection: '#9A5B2F', giftcard: '#6B4A7A', media: '#6B7A4A',
  admin: '#5A5F8A', data_request: '#7A5A4A', chat_quick_replies: '#2F5D6B', llm_config: '#5F4A9A', llm_rag_reindex: '#3A7A8A',
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
  restore_draft: 'tag-done',   /* 商品批量恢复草稿：与 unpublish 同为状态回退类，中性色 */
}
const actClass = (a) => ACTION_TONE[a] || 'tag-done'
/* action 输入联想：域内常见动作 */
const ACTIONS = ['refund', 'publish', 'unpublish', 'ship', 'close', 'assign', 'reply', 'risk', 'upsert', 'approve', 'reject', 'restore_draft']

/* entity 行跳转：按实体域映射到对应管理页（无映射的保持纯文本） */
const ENT_ROUTE = {
  order: () => ({ path: '/orders' }),
  return: () => ({ path: '/returns', query: { tab: 'rma' } }),
  exchange: () => ({ path: '/returns', query: { tab: 'exch' } }),
  product: (id) => ({ path: '/product-edit', query: { id } }),
  /* variant 日志 entity_id 是变体 id，product-edit 需要商品 id：优先取 diff.product_id 深链；
   * 旧日志 diff 无 product_id → 退回商品列表（不带 id） */
  variant: (id, l) => (l?.diff_json?.product_id ? { path: '/product-edit', query: { id: l.diff_json.product_id } } : { path: '/products' }),
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
  giftcard: () => ({ path: '/marketing', query: { tab: 'giftcards' } }),
  setting: () => ({ path: '/settings' }),
  shipping_rate: () => ({ path: '/marketing', query: { tab: 'rates' } }),
  /* media 无独立管理页：保持纯文本展示（不入 ENT_ROUTE） */
}
const entLink = (l) => ENT_ROUTE[l.entity]?.(l.entity_id, l) || null

const pages = computed(() => Math.max(1, Math.ceil(total.value / SIZE)))

function buildUrl(p, size = SIZE) {
  const params = new URLSearchParams({ page: p, size })
  if (f.entity) params.set('entity', f.entity)
  if (f.action.trim()) params.set('action', f.action.trim())
  /* admin_id 空串/非法输入（NaN）不带参数（即清除筛选），防后端 422 */
  const aid = Math.round(Number(f.admin_id))
  if (f.admin_id && Number.isInteger(aid)) params.set('admin_id', aid)
  /* 日期筛选时区：本地日期转 UTC ISO 再提交（start=本地00:00 / end=本地23:59:59.999），
   * 使筛选与本地展示一致；后端 _parse_log_dt 支持显式时区统一落 UTC */
  if (f.start) {
    const [y, m, d] = f.start.split('-').map(Number)
    params.set('start', new Date(y, m - 1, d).toISOString())
  }
  if (f.end) {
    const [y, m, d] = f.end.split('-').map(Number)
    params.set('end', new Date(y, m - 1, d, 23, 59, 59, 999).toISOString())
  }
  return '/api/admin/ops/logs?' + params
}

let pageRetried = false   /* 页码回拉防递归：单次加载链最多回拉一次 */
async function load(p = 1) {
  loadErr.value = false
  errMsg.value = ''
  try {
    const d = await req('GET', buildUrl(p))
    items.value = d.items || []
    total.value = d.total ?? 0
    f.page = d.page || p
    /* page 越界钳制：URL 直链/筛选收窄后回退导致页码超出总页数 → 回最后一页重拉一次（空结果 pages=0 不钳制） */
    if ((d.pages ?? 0) > 0 && f.page > d.pages && !pageRetried) { pageRetried = true; load(d.pages); return }
  } catch (e) {
    loadErr.value = true
    errMsg.value = e.message || ''
    toast('审计日志加载失败：' + (e.message || ''), 'error')
  }
  pageRetried = false
  loaded.value = true
}
onMounted(() => load(f.page))

function apply() { load(1) }
function reset() {
  Object.assign(f, { entity: '', action: '', admin_id: '', start: '', end: '', page: 1 })
  load(1)
}
/* 表格空态文案：任一筛选（实体/动作/管理员/日期）生效→未匹配，否则暂无 */
const filtered = computed(() => !!(f.entity || f.action.trim() || f.admin_id || f.start || f.end))

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

/* CSV 导出：当前筛选（实体/动作/管理员/日期）全量拉取，size=100 上限 2000 行 */
const exporting = ref(false)
async function exportCsv() {
  if (exporting.value) return
  exporting.value = true
  try {
    const { all, truncated } = await fetchAllPages((p) => req('GET', buildUrl(p, 100)), { pageSize: 100, maxPages: 20 })
    if (truncated) toast('匹配结果过多，仅导出前 ' + all.length + ' 条', 'error')
    downloadCsv({
      filename: 'logs_' + new Date().toISOString().slice(0, 10).replace(/-/g, ''),
      headers: ['时间', '管理员', '实体', '动作', '对象ID', '变更内容'],
      rows: all.map((l) => [dt(l.created_at), adminName(l), entLabel(l.entity) + '（' + l.entity + '）', l.action,
        l.entity_id ?? '', diffFull(l.diff_json) || '']),
    })
    toast('已导出 ' + all.length + ' 条 ✓', 'success')
  } catch (e) { toast('导出失败：' + (e.message || ''), 'error') }
  exporting.value = false
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 class="page-title">审计日志</h1>
      <span class="page-sub">管理员操作记录 · 共 {{ total }} 条</span>
    </div>
    <div style="display:flex;gap:10px;align-items:center">
      <button class="btn btn-secondary" :disabled="exporting" @click="exportCsv">{{ exporting ? '导出中…' : '⬇ CSV' }}</button>
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

  <!-- 首屏失败（无旧数据）：错误空态置顶，隐藏表格 -->
  <EmptyState v-else-if="loadErr && !items.length" icon="⚠️" title="审计日志加载失败" :sub="errMsg || '服务端可能未启动或会话已过期'">
    <template #action><button class="btn btn-secondary btn-sm" @click="load(f.page)">重试</button></template>
  </EmptyState>

  <div v-else class="card tbl-wrap">
    <!-- 刷新失败（有旧数据）：卡内顶部横幅，旧数据保留 -->
    <div v-if="loadErr" class="err-banner">
      <span>⚠️ 刷新失败：{{ errMsg || '网络异常，下方为旧数据' }}</span>
      <button class="btn btn-secondary btn-sm" @click="load(f.page)">重试</button>
    </div>
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
    <EmptyState v-if="!items.length" :icon="filtered ? '🔍' : '🗒️'" :title="filtered ? '未找到匹配的日志' : '暂无日志'" :sub="filtered ? '试试调整或清除筛选' : '管理员操作记录将显示在这里'" />
    <Pagination embed :page="f.page" :pages="pages" :total="total" unit="条" @go="load" />
  </div>
</template>

<style scoped>
.ent-badge{display:inline-block;font-size:11px;font-weight:600;border-radius:999px;padding:2px 10px;white-space:nowrap}
/* 刷新失败横幅：pale-error 底 + error 字，圆角，卡内顶部 */
.err-banner{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 14px;margin:12px 12px 0;background:var(--pale-error);color:var(--error);border-radius:10px;font-size:12.5px}
</style>
