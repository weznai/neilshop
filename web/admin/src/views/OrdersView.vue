<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'

const items = ref([])
const total = ref(0)
const page = ref(1)
const status = ref(null)
const q = ref('')
const loaded = ref(false)
const OSTATUS = {
  0: ['待处理', 'tag-pending'], 1: ['已支付', 'tag-paid'], 2: ['备货中', 'tag-pending'],
  3: ['已发货', 'tag-ship'], 4: ['已送达', 'tag-ship'], 5: ['已完成', 'tag-done'],
  6: ['已取消', 'tag-error'], 7: ['已退款', 'tag-error'], 8: ['超时关闭', 'tag-error'], 9: ['已退款', 'tag-error'],
}
const TABS = [['all', '全部', null], ['s0', '待处理', 0], ['s1', '已付', 1], ['s3', '已发货', 3], ['s5', '已完成', 5], ['s9', '已退款', 9]]

async function load() {
  loaded.value = false
  const params = { page: page.value, size: 20 }
  if (status.value != null) params.status = status.value
  if (q.value.trim()) params.q = q.value.trim()
  try {
    const d = await req('GET', '/api/admin/trade/orders?' + new URLSearchParams(params))
    items.value = d.items || []
    total.value = d.total ?? items.value.length
  } catch (_) { items.value = [] }
  loaded.value = true
}
onMounted(load)

function tab(sv) { status.value = sv; page.value = 1; load() }
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }
function money(c) { return '$' + ((c || 0) / 100).toFixed(2) }
function time(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const p = (x) => String(x).padStart(2, '0')
  return p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes())
}
async function ship(o) {
  if (!confirm(`发货 ${o.order_no}？将扣库存并通知客户。`)) return
  try {
    await req('POST', `/api/admin/trade/orders/${o.order_no}/ship`, { carrier: 'USPS', tracking_no: '9400' + Date.now() })
    window.$gmToast(`${o.order_no} 已发货 ✓`, 'success')
    load()
  } catch (e) { window.$gmToast('发货失败：' + (e.message || ''), 'error') }
}
function exportCsv() {
  const rows = [['订单号', '邮箱', '金额', '状态', '时间'],
    ...items.value.map((o) => [o.order_no, o.email, money(o.grand_total), OSTATUS[o.status]?.[0], o.created_at])]
  const csv = rows.map((r) => r.join(',')).join('\n')
  const url = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `orders-p${page.value}.csv`
  a.click()
  URL.revokeObjectURL(url)
  window.$gmToast('已导出 ' + items.value.length + ' 单 ✓', 'success')
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">订单管理</h1>
      <span style="font-size:12.5px;color:var(--gray)">共 {{ total }} 单</span>
    </div>
    <div style="display:flex;gap:10px">
      <input v-model="q" class="input" style="width:220px" placeholder="搜订单号 / 邮箱" @keydown.enter="page = 1; load()">
      <button class="btn btn-secondary" @click="page = 1; load()">搜索</button>
      <button class="btn btn-secondary" @click="exportCsv">⬇ CSV</button>
    </div>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button
      v-for="[k, label, sv] in TABS" :key="k"
      style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer;color:var(--gray);border-bottom:2.5px solid transparent"
      :style="{ color: status === sv ? 'var(--plum)' : 'var(--gray)', borderBottomColor: status === sv ? 'var(--plum)' : 'transparent' }"
      @click="tab(sv)"
    >{{ label }}<span v-if="status === sv" style="color:var(--gray);font-weight:400"> ({{ total }})</span></button>
  </div>

  <div class="card" style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="text-align:left;color:var(--gray)">
          <th style="padding:10px">订单号</th><th>客户</th><th>金额</th><th>状态</th><th>时间</th><th style="text-align:right">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="o in items" :key="o.order_no" style="border-top:1px solid var(--gray-light)">
          <td style="padding:11px 10px"><b>{{ o.order_no }}</b></td>
          <td>{{ esc(o.email) }}</td>
          <td><b style="color:var(--plum)">{{ money(o.grand_total) }}</b></td>
          <td><span class="tag" :class="OSTATUS[o.status]?.[1]">{{ OSTATUS[o.status]?.[0] }}</span></td>
          <td style="color:var(--gray)">{{ time(o.created_at) }}</td>
          <td style="text-align:right;white-space:nowrap">
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/order-detail', query: { no: o.order_no } }">详情</router-link>
            <button v-if="o.status === 1 || o.status === 2" class="btn btn-primary btn-sm" style="margin-left:6px" @click="ship(o)">📦 发货</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="loaded && !items.length" style="text-align:center;color:var(--gray);padding:28px 0">该状态下暂无订单</div>
  </div>

  <div v-if="total > 20" style="display:flex;justify-content:center;gap:8px;margin-top:16px">
    <button class="btn btn-secondary btn-sm" :disabled="page <= 1" @click="page--; load()">←</button>
    <span style="align-self:center;font-size:13px;color:var(--gray)">第 {{ page }} 页</span>
    <button class="btn btn-secondary btn-sm" :disabled="page * 20 >= total" @click="page++; load()">→</button>
  </div>
</template>
