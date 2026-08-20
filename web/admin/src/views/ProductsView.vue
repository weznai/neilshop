<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { req } from '../api/client'
import { toast } from '../composables/toast'

const router = useRouter()
const items = ref([])
const total = ref(0)
const pages = ref(1)
const page = ref(1)
const q = ref('')
const status = ref(null)
const loaded = ref(false)
const bulk = ref(false)
const bulkText = ref('')
const bulkResult = ref(null)

const TABS = [[null, '全部'], [1, '在售'], [0, '草稿'], [2, '归档']]
const SMeta = { 0: ['草稿', 'tag-pending'], 1: ['在售', 'tag-paid'], 2: ['归档', 'tag'] }
const BULK_ERR = { 'slug already exists': 'slug 已存在', 'category not found': '分类不存在' }
const failures = computed(() => (bulkResult.value?.results || []).filter((r) => !r.ok))

async function load() {
  loaded.value = false
  try {
    const qs = { page: page.value, size: 50, q: q.value.trim() }
    if (status.value !== null) qs.status = status.value
    const d = await req('GET', '/api/admin/catalog/products?' + new URLSearchParams(qs))
    items.value = d.items || []
    total.value = d.total ?? 0
    pages.value = Math.max(1, Math.ceil(total.value / 50))
  } catch (e) { items.value = []; toast('加载失败', 'error') }
  loaded.value = true
}
onMounted(load)

function search() { page.value = 1; load() }
function tab(sv) { status.value = sv; page.value = 1; load() }

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

async function toggle(p) {
  const action = p.status === 1 ? 'unpublish' : 'publish'
  /* unpublish 语义为归档（status→2），文案与后端保持一致 */
  if (!confirm(action === 'publish' ? `上架 ${p.title}？` : `归档 ${p.title}？（前台不再展示，可在「归档」tab 查看）`)) return
  try {
    await req('POST', `/api/admin/catalog/products/${p.id}/${action}`)
    toast(action === 'publish' ? '已上架 ✓' : '已归档 ✓', 'success')
    load()
  } catch (e) { toast('操作失败：' + (e.data?.detail || e.message), 'error') }
}
async function bulkImport() {
  try {
    const lines = bulkText.value.trim().split(/\n+/).filter(Boolean)
    const bad = []
    const rows = lines.map((l, i) => {
      const c = l.split(',').map((s) => s.trim())
      /* 固定列序 slug,title,price,category_id：列数不足 4 直接判格式错误 */
      if (c.length < 4) { bad.push(`第 ${i + 1} 行：列数不足 4（需 slug,title,price,category_id）`); return null }
      const price = Math.round(parseFloat(c[2]) * 100)
      const cat = Number(c[3])
      if (!c[0] || !c[1] || !Number.isFinite(price) || price < 0) { bad.push(`第 ${i + 1} 行：slug/标题缺失或价格无效`); return null }
      if (!Number.isInteger(cat) || cat < 1 || cat > 4) { bad.push(`第 ${i + 1} 行：category_id 需为 1-4 整数（当前 ${c[3]}）`); return null }
      return { slug: c[0], title: c[1], price_min: price, price_max: price, category_id: cat }
    }).filter(Boolean)
    if (bad.length) { toast('存在格式错误的行，未导入：' + bad[0] + (bad.length > 1 ? ` 等 ${bad.length} 处` : ''), 'error'); return }
    if (!rows.length) { toast('没有可导入的行', 'error'); return }
    const d = await req('POST', '/api/admin/catalog/products/bulk', { items: rows })
    bulkResult.value = d
    toast(d.failed ? `导入完成：成功 ${d.created} / 失败 ${d.failed}` : `全部导入成功（${d.created}）✓`, d.failed ? 'error' : 'success')
    load()
  } catch (e) { toast('导入失败：' + (e.data?.detail || e.message), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">商品管理</h1>
      <span style="font-size:12.5px;color:var(--gray)">共 {{ total }} 款</span>
    </div>
    <div style="display:flex;gap:10px">
      <input v-model="q" class="input" style="width:220px" placeholder="搜标题 / slug" @keydown.enter="search">
      <button class="btn btn-secondary" @click="search">搜索</button>
      <button class="btn btn-secondary" @click="bulk = true">📦 批量导入</button>
      <router-link to="/product-edit" class="btn btn-primary">＋ 新建商品</router-link>
    </div>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button v-for="[sv, label] in TABS" :key="String(sv)"
            style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer"
            :style="{ color: status === sv ? 'var(--plum)' : 'var(--gray)', borderBottom: status === sv ? '2.5px solid var(--plum)' : '2.5px solid transparent' }"
            @click="tab(sv)">{{ label }}</button>
  </div>

  <div class="card tbl-wrap">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="padding:10px">商品</th><th>价格</th><th>库存</th><th>销量</th><th>评分</th><th>状态</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="p in items" :key="p.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:10px">
            <div style="display:flex;gap:10px;align-items:center">
              <img v-if="p.hero_image && !p.broken" :src="p.hero_image" :alt="p.title" style="width:42px;height:42px;border-radius:8px;object-fit:cover" @error="p.broken = true">
              <div v-else style="width:42px;height:42px;border-radius:8px;background:var(--rose-pale);color:var(--plum);display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;flex:none">{{ (p.title || '?').slice(0, 1).toUpperCase() }}</div>
              <div>
                <b>{{ p.title }}</b>
                <span v-if="p.is_new" class="tag tag-paid" style="margin-left:6px;font-size:10px">NEW</span>
                <span v-if="p.is_best_seller" class="tag tag-done" style="margin-left:4px;font-size:10px">HOT</span>
                <div style="font-size:11.5px;color:var(--gray)">{{ p.slug }} · {{ p.variant_count ?? 0 }} 变体</div>
              </div>
            </div>
          </td>
          <td>
            <b>{{ money(p.price_min) }}</b><span v-if="p.price_max > p.price_min" style="color:var(--gray)">–{{ money(p.price_max) }}</span>
            <div v-if="p.compare_at_price" style="font-size:11px;color:var(--gray);text-decoration:line-through">{{ money(p.compare_at_price) }}</div>
          </td>
          <td>
            <span class="tag" :class="p.total_stock ? (p.low_stock_count ? 'tag-pending' : 'tag-done') : 'tag-error'">{{ p.total_stock ?? 0 }}</span>
            <div v-if="p.low_stock_count" style="font-size:11px;color:var(--error)">{{ p.low_stock_count }} 个低水位</div>
          </td>
          <td style="color:var(--gray)">{{ p.sold_count ?? 0 }}</td>
          <td style="color:var(--gray)">{{ ((p.rating_avg || 0) / 100).toFixed(1) }} <small v-if="p.rating_count">({{ p.rating_count }})</small></td>
          <td>
            <span class="tag" :class="SMeta[p.status]?.[1] || 'tag'">{{ SMeta[p.status]?.[0] || p.status }}</span>
            <span v-if="p.scheduled" class="tag tag-sched" style="margin-left:4px" title="到点自动在前台可见">定时</span>
          </td>
          <td style="text-align:right;white-space:nowrap">
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/product-edit', query: { id: p.id } }">编辑</router-link>
            <button class="btn btn-ghost btn-sm" style="margin-left:6px" @click="toggle(p)">{{ p.status === 1 ? '归档' : '上架' }}</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="loaded && !items.length" style="text-align:center;color:var(--gray);padding:28px 0">没有匹配商品</div>
  </div>

  <div v-if="pages > 1" style="display:flex;justify-content:center;gap:8px;margin-top:16px;align-items:center">
    <button class="btn btn-secondary btn-sm" :disabled="page <= 1" @click="page--; load()">←</button>
    <span style="font-size:13px;color:var(--gray)">第 {{ page }} / {{ pages }} 页</span>
    <button class="btn btn-secondary btn-sm" :disabled="page >= pages" @click="page++; load()">→</button>
  </div>

  <!-- 批量导入弹窗 -->
  <div v-if="bulk" class="modal open" @click.self="bulk = false">
    <div class="modal-box" style="max-width:560px">
      <button class="modal-x" @click="bulk = false">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">📦 批量导入</h3>
      <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">CSV 粘贴（slug,title,price,category_id）≤100 行，部分成功不回滚；price 单位美元，库存请在变体中维护。</p>
      <textarea v-model="bulkText" class="input" rows="8" placeholder="nova-set,Nova Set,15.99,1"></textarea>
      <button class="btn btn-primary btn-block" style="margin-top:12px" @click="bulkImport">导入</button>
      <div v-if="bulkResult" style="margin-top:12px;font-size:12.5px">
        <p style="color:var(--gray)">结果：成功 <b style="color:var(--success)">{{ bulkResult.created }}</b> · 失败 <b :style="{ color: bulkResult.failed ? 'var(--error)' : 'var(--gray)' }">{{ bulkResult.failed }}</b></p>
        <div v-if="failures.length" style="max-height:180px;overflow-y:auto;border-top:1px dashed var(--gray-light);padding-top:8px">
          <div v-for="f in failures" :key="f.index" style="padding:3px 0;color:var(--error)">
            第 {{ f.index + 1 }} 行 · {{ f.slug || '（无 slug）' }}：{{ BULK_ERR[f.error] || f.error }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
