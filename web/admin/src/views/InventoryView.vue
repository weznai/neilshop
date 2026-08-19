<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'

const variants = ref([])
const low = ref([])
const movements = ref([])
const loaded = ref(false)
const q = ref('')
const adjust = ref(null)
const adjQty = ref(0)

async function load() {
  loaded.value = false
  try {
    variants.value = (await req('GET', '/api/admin/catalog/variants?' + new URLSearchParams({ page: 1, size: 50, q: q.value.trim() }))).items || []
  } catch (_) { variants.value = [] }
  try { low.value = (await req('GET', '/api/admin/trade/stock/low?threshold=8')).items || [] } catch (_) { /* */ }
  try { movements.value = (await req('GET', '/api/admin/trade/stock/movements?page=1')).items || [] } catch (_) { /* */ }
  loaded.value = true
}
onMounted(load)

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

async function doAdjust() {
  if (!adjust.value || !adjQty.value) return
  try {
    await req('POST', '/api/admin/trade/stock/adjust', {
      variant_id: adjust.value.id, delta: adjQty.value, reason: 'ops-manual',
    })
    window.$gmToast(`已调整 ${adjust.value.sku} ${adjQty.value > 0 ? '+' : ''}${adjQty.value} ✓`, 'success')
    adjust.value = null
    adjQty.value = 0
    load()
  } catch (e) { window.$gmToast('调整失败：' + (e.message || ''), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">库存中心</h1>
      <span style="font-size:12.5px;color:var(--gray)">SKU 概览 · 低库存 {{ low.length }} · 变动流水</span>
    </div>
    <input v-model="q" class="input" style="width:220px" placeholder="搜 SKU / 标题" @keydown.enter="load()">
  </div>

  <div class="card" style="overflow-x:auto;margin-bottom:16px">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)">
        <th style="padding:10px">SKU</th><th>商品</th><th>规格</th><th>价格</th><th>现货</th><th>安全库存</th><th>水位</th><th style="text-align:right">操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="v in variants" :key="v.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:10px"><b>{{ v.sku }}</b></td>
          <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis">{{ v.title || v.product_title }}</td>
          <td>{{ v.option1_value }}</td>
          <td>{{ money(v.price) }}</td>
          <td><b>{{ v.stock }}</b></td>
          <td style="color:var(--gray)">{{ v.safety_stock }}</td>
          <td>
            <div class="stock-track" style="width:70px"><div class="stock-fill" :style="{ width: Math.min(100, v.stock * 3) + '%' }"></div></div>
          </td>
          <td style="text-align:right">
            <button class="btn btn-secondary btn-sm" @click="adjust = v; adjQty = 0">调整</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="loaded && !variants.length" style="text-align:center;color:var(--gray);padding:28px 0">无匹配 SKU</div>
  </div>

  <div class="grid-2" style="align-items:start">
    <div class="card" style="padding:18px">
      <h3 style="font-size:14.5px;margin-bottom:10px">⚠️ 低库存预警（≤8）</h3>
      <div v-for="l in low" :key="l.id" style="display:flex;justify-content:space-between;font-size:13px;padding:7px 0;border-bottom:1px solid var(--gray-light)">
        <span>{{ l.sku || l.title }}</span><b style="color:var(--error)">{{ l.stock }}</b>
      </div>
      <div v-if="!low.length" style="font-size:13px;color:var(--gray);padding:10px 0">全部水位健康 ✓</div>
    </div>
    <div class="card" style="padding:18px">
      <h3 style="font-size:14.5px;margin-bottom:10px">📜 最近变动</h3>
      <div v-for="(m, i) in movements.slice(0, 10)" :key="i" style="display:flex;justify-content:space-between;font-size:13px;padding:7px 0;border-bottom:1px solid var(--gray-light)">
        <span style="color:var(--gray)">{{ (m.created_at || '').slice(5, 16).replace('T', ' ') }} · {{ m.reason }}</span>
        <b :style="{ color: m.delta >= 0 ? 'var(--success)' : 'var(--error)' }">{{ m.delta >= 0 ? '+' : '' }}{{ m.delta }}</b>
      </div>
      <div v-if="!movements.length" style="font-size:13px;color:var(--gray);padding:10px 0">暂无流水</div>
    </div>
  </div>

  <!-- 调整弹窗 -->
  <div v-if="adjust" class="modal open" @click.self="adjust = null">
    <div class="modal-box" style="max-width:400px">
      <button class="modal-x" @click="adjust = null">×</button>
      <h3 style="font-family:var(--font-title);margin-bottom:6px">调整库存</h3>
      <p style="font-size:13px;color:var(--gray);margin-bottom:12px">
        {{ adjust.sku }} · 当前 <b>{{ adjust.stock }}</b>（安全库存 {{ adjust.safety_stock }}）
      </p>
      <div class="field"><label>增减数量（±）</label><input v-model.number="adjQty" class="input" type="number" placeholder="如 20 或 -5"></div>
      <button class="btn btn-primary btn-block" style="margin-top:12px" @click="doAdjust">确认调整</button>
    </div>
  </div>
</template>
