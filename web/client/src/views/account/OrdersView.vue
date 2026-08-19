<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../../api/client'

const orders = ref([])
const loaded = ref(false)
const OSTATUS = {
  0: ['Pending', 'tag-pending'], 1: ['Paid', 'tag-paid'], 2: ['Packing', 'tag-pending'],
  3: ['Shipped', 'tag-ship'], 4: ['Delivered', 'tag-ship'], 5: ['Done', 'tag-done'],
  6: ['Cancelled', 'tag-error'], 7: ['Refunded', 'tag-error'], 8: ['Expired', 'tag-error'], 9: ['Refunded', 'tag-error'],
}
const TABS = [['all', 'All', null], ['s1', 'Paid', 1], ['s3', 'Shipped', 3], ['s5', 'Done', 5]]

const tab = ref(null)
onMounted(async () => {
  try { orders.value = (await req('GET', '/api/orders')).items || [] } catch (_) { /* */ }
  loaded.value = true
})
const shown = () => (tab.value == null ? orders.value : orders.value.filter((o) => o.status === tab.value))
</script>

<template>
  <div>
    <div style="display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap">
      <button
        v-for="[k, label, sv] in TABS" :key="k" class="btn btn-sm"
        :class="tab === sv ? 'btn-primary' : 'btn-secondary'" @click="tab = sv"
      >{{ label }}</button>
    </div>
    <div v-if="shown().length" style="display:grid;gap:12px">
      <div v-for="o in shown()" :key="o.order_no" class="card ocard" :data-no="o.order_no" style="padding:18px">
        <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">
          <div>
            <b>{{ o.order_no }}</b>
            <div style="font-size:12px;color:var(--gray)">{{ new Date(o.created_at).toLocaleString() }} · {{ (o.items || []).length }} items</div>
          </div>
          <div style="display:flex;gap:10px;align-items:center">
            <span class="tag" :class="OSTATUS[o.status]?.[1]">{{ OSTATUS[o.status]?.[0] }}</span>
            <b style="color:var(--plum)">${{ ((o.grand_total || 0) / 100).toFixed(2) }}</b>
            <router-link class="btn btn-secondary btn-sm" :to="{ path: '/account/orders/detail', query: { no: o.order_no } }">Detail →</router-link>
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="loaded" class="card" style="padding:30px;text-align:center;color:var(--gray)">
      No orders in this view.
    </div>
  </div>
</template>
