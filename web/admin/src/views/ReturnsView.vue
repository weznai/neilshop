<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../api/client'

const rmas = ref([])
const exch = ref([])
const tab = ref('rma')
const loaded = ref(false)
const RSTATUS = {
  0: ['待审核', 'tag-pending'], 1: ['已批准', 'tag-paid'], 2: ['已拒绝', 'tag-error'],
  3: ['已退款', 'tag-done'], 4: ['已关闭', 'tag-done'],
}
const ESTATUS = {
  0: ['待审核', 'tag-pending'], 1: ['换货中', 'tag-paid'], 2: ['已重发', 'tag-ship'], 3: ['已拒绝', 'tag-error'], 4: ['已关闭', 'tag-done'],
}

onMounted(async () => {
  try {
    rmas.value = (await req('GET', '/api/admin/trade/rmas')).items || []
    exch.value = (await req('GET', '/api/admin/trade/exchanges?page=1')).items || []
  } catch (_) { /* */ }
  loaded.value = true
})

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

async function decide(r, approve) {
  if (!confirm(`${approve ? '批准' : '拒绝'} ${r.rma_no || r.id}？`)) return
  try {
    await req('POST', `/api/admin/trade/rmas/${r.id}/${approve ? 'approve' : 'reject'}`,
      approve ? { refund_amount: r.refund_amount } : { reason: 'ops-reject' })
    window.$gmToast('已' + (approve ? '批准' : '拒绝') + ' ✓', 'success')
    rmas.value = (await req('GET', '/api/admin/trade/rmas')).items || []
  } catch (e) { window.$gmToast('操作失败：' + (e.message || ''), 'error') }
}
async function decideEx(x, approve) {
  if (!confirm(`${approve ? '批准换货' : '拒绝'} ${x.order_no}？`)) return
  try {
    await req('POST', `/api/admin/trade/exchanges/${x.id}/${approve ? 'approve' : 'reject'}`)
    window.$gmToast('操作成功 ✓', 'success')
    exch.value = (await req('GET', '/api/admin/trade/exchanges?page=1')).items || []
  } catch (e) { window.$gmToast('操作失败：' + (e.message || ''), 'error') }
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">退货审核</h1>
      <span style="font-size:12.5px;color:var(--gray)">RMA {{ rmas.length }} · 换货 {{ exch.length }}</span>
    </div>
  </div>

  <div class="otab" style="display:flex;gap:4px;border-bottom:1.5px solid var(--gray-light);margin-bottom:14px">
    <button
      v-for="[k, label] in [['rma', '退货 RMA'], ['exch', '换货']]"
      :key="k"
      style="padding:9px 16px;font-size:13.5px;font-weight:600;border:none;background:none;cursor:pointer"
      :style="{ color: tab === k ? 'var(--plum)' : 'var(--gray)', borderBottom: tab === k ? '2.5px solid var(--plum)' : '2.5px solid transparent' }"
      @click="tab = k"
    >{{ label }}</button>
  </div>

  <div class="card" style="overflow-x:auto">
    <table v-if="tab === 'rma'" style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">RMA</th><th>订单</th><th>原因</th><th>金额</th><th>状态</th><th style="text-align:right">操作</th></tr></thead>
      <tbody>
        <tr v-for="r in rmas" :key="r.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:11px 10px"><b>{{ r.rma_no || '#' + r.id }}</b></td>
          <td>{{ r.order_no }}</td>
          <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis">{{ r.reason || '—' }}</td>
          <td><b style="color:var(--plum)">{{ money(r.refund_amount) }}</b></td>
          <td><span class="tag" :class="RSTATUS[r.status]?.[1]">{{ RSTATUS[r.status]?.[0] }}</span></td>
          <td style="text-align:right">
            <template v-if="r.status === 0">
              <button class="btn btn-primary btn-sm" @click="decide(r, true)">批准退款</button>
              <button class="btn btn-ghost btn-sm" style="color:var(--error);margin-left:6px" @click="decide(r, false)">拒绝</button>
            </template>
          </td>
        </tr>
      </tbody>
    </table>

    <table v-else style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="text-align:left;color:var(--gray)"><th style="padding:10px">订单</th><th>换货商品</th><th>状态</th><th style="text-align:right">操作</th></tr></thead>
      <tbody>
        <tr v-for="x in exch" :key="x.id" style="border-top:1px solid var(--gray-light)">
          <td style="padding:11px 10px"><b>{{ x.order_no }}</b></td>
          <td>{{ x.title || x.variant_title || '—' }}</td>
          <td><span class="tag" :class="ESTATUS[x.status]?.[1]">{{ ESTATUS[x.status]?.[0] }}</span></td>
          <td style="text-align:right">
            <button v-if="x.status === 0" class="btn btn-primary btn-sm" @click="decideEx(x, true)">批准换货</button>
            <button v-if="x.status === 0" class="btn btn-ghost btn-sm" style="color:var(--error);margin-left:6px" @click="decideEx(x, false)">拒绝</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="loaded && !(tab === 'rma' ? rmas.length : exch.length)" style="text-align:center;color:var(--gray);padding:28px 0">
      暂无{{ tab === 'rma' ? '退货' : '换货' }}申请
    </div>
  </div>
</template>
