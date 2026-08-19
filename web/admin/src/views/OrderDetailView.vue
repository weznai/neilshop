<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'

const route = useRoute()
const o = ref(null)
const err = ref('')
const OSTATUS = ['待处理', '已支付', '备货中', '已发货', '已送达', '已完成', '已取消', '已退款', '超时关闭', '已退款']

onMounted(async () => {
  const no = route.query.no
  if (!no) { err.value = '缺少订单号'; return }
  try { o.value = await req('GET', '/api/admin/trade/orders/' + encodeURIComponent(no)) }
  catch (e) { err.value = e.status === 404 ? '订单不存在' : '加载失败' }
})

const money = (c) => '$' + ((c || 0) / 100).toFixed(2)

async function act(type) {
  const no = o.value.order_no
  if (type === 'ship') {
    if (!confirm(`发货 ${no}？`)) return
    await req('POST', `/api/admin/trade/orders/${no}/ship`, { carrier: 'USPS', tracking_no: '9400' + Date.now() })
  } else if (type === 'deliver') {
    if (!confirm(`标记 ${no} 已妥投？`)) return
    await req('POST', `/api/admin/trade/orders/${no}/deliver`)
  } else if (type === 'refund') {
    if (!confirm(`退款 ${no}（默认全额）？`)) return
    await req('POST', `/api/admin/trade/orders/${no}/refund`, { amount: o.value.grand_total, reason: 'ops-refund' })
  }
  o.value = await req('GET', '/api/admin/trade/orders/' + encodeURIComponent(no))
  window.$gmToast('操作成功 ✓', 'success')
}
</script>

<template>
  <div class="topbar">
    <div>
      <h1 style="font-size:22px">订单详情</h1>
      <span style="font-size:12.5px;color:var(--gray)">{{ route.query.no }}</span>
    </div>
    <router-link to="/orders" class="btn btn-secondary btn-sm">← 返回列表</router-link>
  </div>

  <div v-if="err" class="card" style="padding:32px;text-align:center;color:var(--gray)">{{ err }}</div>
  <div v-else-if="!o" class="card skeleton" style="min-height:240px" />

  <div v-else class="grid-2" style="align-items:start">
    <div class="card" style="padding:20px">
      <h3 style="font-size:15px;margin-bottom:12px">商品明细</h3>
      <div v-for="(it, i) in o.items || []" :key="i" style="display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--gray-light);font-size:13px">
        <img :src="it.image" :alt="it.title" style="width:52px;height:52px;border-radius:9px;object-fit:cover">
        <div style="flex:1"><b>{{ it.title }}</b><div style="color:var(--gray)">x{{ it.qty }} · {{ money(it.price) }}</div></div>
        <b>{{ money(it.line_total ?? it.price * it.qty) }}</b>
      </div>
      <div style="display:grid;gap:6px;margin-top:12px;font-size:13px">
        <div style="display:flex;justify-content:space-between"><span>小计</span><span>{{ money(o.subtotal) }}</span></div>
        <div style="display:flex;justify-content:space-between"><span>运费</span><span>{{ money(o.shipping_fee) }}</span></div>
        <div style="display:flex;justify-content:space-between"><span>税费</span><span>{{ money(o.tax) }}</span></div>
        <div style="display:flex;justify-content:space-between;font-weight:800;font-size:14.5px;border-top:1px solid var(--gray-light);padding-top:6px">
          <span>总计</span><span style="color:var(--plum)">{{ money(o.grand_total) }}</span>
        </div>
      </div>
    </div>

    <div style="display:grid;gap:16px">
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">订单信息</h3>
        <div style="display:grid;gap:8px;font-size:13px">
          <div style="display:flex;justify-content:space-between"><span>状态</span>
            <span class="tag" :class="o.status >= 1 && o.status <= 5 ? 'tag-paid' : 'tag-error'">{{ OSTATUS[o.status] }}</span></div>
          <div style="display:flex;justify-content:space-between"><span>客户</span><span>{{ o.email }}</span></div>
          <div style="display:flex;justify-content:space-between"><span>物流</span><span>{{ o.carrier || '—' }} {{ o.tracking_no || '' }}</span></div>
        </div>
      </div>
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">收件地址</h3>
        <div style="font-size:13px;line-height:1.7;color:var(--ink)">
          {{ o.address?.full_name }}<br>{{ o.address?.line1 }} {{ o.address?.line2 }}<br>
          {{ o.address?.city }}, {{ o.address?.state }} {{ o.address?.zip }} · {{ o.address?.country }}
        </div>
      </div>
      <div class="card" style="padding:20px">
        <h3 style="font-size:15px;margin-bottom:12px">履约操作</h3>
        <div style="display:grid;gap:8px">
          <button v-if="o.status === 1 || o.status === 2" class="btn btn-primary" @click="act('ship')">📦 发货</button>
          <button v-if="o.status === 3" class="btn btn-secondary" @click="act('deliver')">✅ 标记妥投</button>
          <button v-if="[1, 2, 3, 4, 5].includes(o.status)" class="btn btn-ghost" style="color:var(--error)" @click="act('refund')">💸 退款</button>
        </div>
      </div>
    </div>
  </div>
</template>
