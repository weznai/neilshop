<script setup>
import { onMounted, ref } from 'vue'
import { req } from '../../api/client'
import { useUiStore } from '../../stores/ui'

const ui = useUiStore()
const returns = ref([])
const loaded = ref(false)
const RSTATUS = {
  0: ['Requested', 'tag-pending'], 1: ['Approved', 'tag-paid'], 2: ['Rejected', 'tag-error'],
  3: ['Refunded', 'tag-done'], 4: ['Closed', 'tag-done'],
}

onMounted(async () => {
  try { returns.value = (await req('GET', '/api/returns')).items || [] } catch (_) { /* */ }
  loaded.value = true
})
</script>

<template>
  <div>
    <div class="card" style="padding:18px;margin-bottom:16px;font-size:13.5px;color:var(--gray);line-height:1.7">
      ↩️ <b>30-day free returns</b> · <b>exchanges always free</b>（we reship instantly, you keep the original）。
      Start from <router-link to="/account/orders" style="color:var(--plum)">Orders</router-link> → Detail → Return/Exchange.
    </div>
    <div v-if="returns.length" style="display:grid;gap:12px">
      <div v-for="r in returns" :key="r.id || r.rma_no" class="card" style="padding:18px">
        <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">
          <div>
            <b>RMA {{ r.rma_no || r.id }}</b>
            <div style="font-size:12px;color:var(--gray)">Order {{ r.order_no }} · {{ new Date(r.created_at).toLocaleDateString() }}</div>
          </div>
          <span class="tag" :class="RSTATUS[r.status]?.[1]">{{ RSTATUS[r.status]?.[0] || '—' }}</span>
          <b style="color:var(--plum)">${{ ((r.refund_amount || 0) / 100).toFixed(2) }}</b>
        </div>
      </div>
    </div>
    <div v-else-if="loaded" class="card" style="padding:30px;text-align:center;color:var(--gray)">
      No returns yet. Nothing to worry about 💅
    </div>
  </div>
</template>
