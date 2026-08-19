<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { req } from '../api/client'

const router = useRouter()
const items = ref([])
const total = ref(0)
const q = ref('')
const loaded = ref(false)
const bulk = ref(false)
const bulkText = ref('')
const bulkResult = ref(null)

async function load() {
  loaded.value = false
  try {
    const d = await req('GET', '/api/admin/catalog/products?' + new URLSearchParams({ page: 1, size: 50, q: q.value.trim() }))
    items.value = d.items || []
    total.value = d.total ?? items.value.length
  } catch (_) { items.value = [] }
  loaded.value = true
}
onMounted(load)

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

async function toggle(p) {
  await req('PUT', '/api/admin/catalog/products/' + p.id, { status: p.status === 1 ? 0 : 1 })
  window.$gmToast(p.status === 1 ? '已下架' : '已上架', 'success')
  load()
}
async function bulkImport() {
  try {
    const rows = bulkText.value.trim().split(/\n+/).filter(Boolean).map((l) => {
      const [slug, title, price, stock, category_id] = l.split(',').map((s) => s.trim())
      return { slug, title, price: Math.round(parseFloat(price) * 100), stock: parseInt(stock, 10) || 0, category_id: parseInt(category_id, 10) || 1 }
    })
    const d = await req('POST', '/api/admin/catalog/products/bulk', { items: rows })
    bulkResult.value = d
    window.$gmToast(`导入完成：成功 ${d.ok ?? d.created ?? rows.length} 行`, 'success')
    load()
  } catch (e) { window.$gmToast('导入失败：' + (e.message || ''), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">商品管理</h1>
      <span style="font-size:12.5px;color:var(--gray)">共 {{ total }} 款</span>
    </div>
    <div style="display:flex;gap:10px">
      <input v-model="q" class="input" style="width:220px" placeholder="搜标题 / slug" @keydown.enter="load()">
      <button class="btn btn-secondary" @click="bulk = true">📦 批量导入</button>
      <router-link to="/product-edit" class="btn btn-primary">＋ 新建商品</router-link>
    </div>
  </div>

  <div class="card" style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="padding:10px">商品</th><th>价格</th><th>库存</th><th>销量</th><th>状态</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="p in items" :key="p.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:10px">
            <div style="display:flex;gap:10px;align-items:center">
              <img :src="p.hero_image" :alt="p.title" style="width:42px;height:42px;border-radius:8px;object-fit:cover">
              <div>
                <b>{{ p.title }}</b>
                <span v-if="p.is_new" class="tag tag-paid" style="margin-left:6px;font-size:10px">NEW</span>
                <div style="font-size:11.5px;color:var(--gray)">{{ p.slug }}</div>
              </div>
            </div>
          </td>
          <td><b>{{ money(p.price_min) }}</b><span v-if="p.price_max > p.price_min" style="color:var(--gray)">–{{ money(p.price_max) }}</span></td>
          <td><span class="tag" :class="p.stock_summary?.total ? 'tag-done' : 'tag-error'">{{ p.stock_summary?.total ?? 0 }}</span></td>
          <td style="color:var(--gray)">{{ p.sold_count ?? 0 }}</td>
          <td><span class="tag" :class="p.status === 1 ? 'tag-paid' : 'tag-pending'">{{ p.status === 1 ? '在售' : '下架' }}</span></td>
          <td style="text-align:right;white-space:nowrap">
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/product-edit', query: { id: p.id } }">编辑</router-link>
            <button class="btn btn-ghost btn-sm" style="margin-left:6px" @click="toggle(p)">{{ p.status === 1 ? '下架' : '上架' }}</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="loaded && !items.length" style="text-align:center;color:var(--gray);padding:28px 0">没有匹配商品</div>
  </div>

  <!-- 批量导入弹窗 -->
  <div v-if="bulk" class="modal open" @click.self="bulk = false">
    <div class="modal-box" style="max-width:560px">
      <button class="modal-x" @click="bulk = false">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">📦 批量导入</h3>
      <p style="font-size:12.5px;color:var(--gray);margin-bottom:12px">CSV 粘贴（slug,title,price,stock,category_id）≤100 行，部分成功不回滚。</p>
      <textarea v-model="bulkText" class="input" rows="8" placeholder="nova-set,Nova Set,15.99,50,1"></textarea>
      <button class="btn btn-primary btn-block" style="margin-top:12px" @click="bulkImport">导入</button>
      <div v-if="bulkResult" style="margin-top:10px;font-size:12.5px;color:var(--gray)">
        结果：{{ JSON.stringify(bulkResult.results || bulkResult).slice(0, 400) }}
      </div>
    </div>
  </div>
</template>
