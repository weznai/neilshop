<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../../api/client'
import { useUiStore } from '../../stores/ui'

const route = useRoute()
const ui = useUiStore()
const o = ref(null)
const err = ref('')

const OSTATUS = ['Pending', 'Paid', 'Packing', 'Shipped', 'Delivered', 'Done', 'Cancelled', 'Refunded', 'Expired', 'Refunded']

onMounted(async () => {
  const no = route.query.no
  if (!no) { err.value = 'Missing order number'; return }
  try {
    o.value = await req('GET', '/api/orders/' + encodeURIComponent(no))
  } catch (e) {
    err.value = e.status === 404 ? 'Order not found' : 'Could not load order'
  }
})

const steps = computed(() => {
  if (!o.value) return []
  const s = o.value.status
  const labels = ['Placed', 'Paid', 'Packing', 'Shipped', 'Delivered']
  const upto = s >= 4 ? 4 : s < 0 ? 0 : s
  return labels.map((l, i) => ({ l, done: i <= upto }))
})

async function requestReturn() {
  ui.toast('Return request flow — see Returns tab for RMA management', 'success')
}
</script>

<template>
  <div>
    <div v-if="err" class="card" style="padding:30px;text-align:center;color:var(--gray)">{{ err }}</div>
    <div v-else-if="!o" class="card skeleton" style="min-height:220px" />
    <div v-else style="display:grid;gap:16px">
      <div class="card" style="padding:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
          <h2 style="font-family:var(--font-title);font-size:22px">{{ o.order_no }}</h2>
          <span class="tag" :class="o.status >= 1 && o.status <= 5 ? 'tag-paid' : 'tag-error'">{{ OSTATUS[o.status] }}</span>
        </div>
        <!-- 时间线 -->
        <div style="display:flex;gap:0;margin:18px 0">
          <div v-for="(s, i) in steps" :key="i" style="flex:1;text-align:center;position:relative">
            <div :style="{ background: s.done ? 'var(--success)' : 'var(--gray-light)' }" style="width:26px;height:26px;border-radius:50%;margin:0 auto 6px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px">
              {{ s.done ? '✓' : i + 1 }}
            </div>
            <div style="font-size:11.5px" :style="{ color: s.done ? 'var(--ink)' : 'var(--gray)' }">{{ s.l }}</div>
          </div>
        </div>
      </div>

      <div class="grid-m-1" style="display:grid;grid-template-columns:1.4fr 1fr;gap:16px">
        <div class="card" style="padding:20px">
          <h3 style="font-size:15px;margin-bottom:12px">Items</h3>
          <div v-for="(it, i) in o.items || []" :key="i" style="display:flex;gap:12px;padding:10px 0;border-bottom:1px solid var(--gray-light)">
            <img :src="it.image" :alt="it.title" style="width:56px;height:56px;border-radius:9px;object-fit:cover">
            <div style="flex:1;font-size:13.5px">
              <b>{{ it.title }}</b>
              <div style="color:var(--gray);font-size:12px">Qty {{ it.qty }}</div>
            </div>
            <b style="font-size:13.5px">${{ ((it.line_total ?? it.price * it.qty) / 100).toFixed(2) }}</b>
          </div>
          <div style="display:grid;gap:6px;margin-top:12px;font-size:13.5px">
            <div style="display:flex;justify-content:space-between"><span>Subtotal</span><span>${{ ((o.subtotal || 0) / 100).toFixed(2) }}</span></div>
            <div style="display:flex;justify-content:space-between"><span>Shipping</span><span>${{ ((o.shipping_fee || 0) / 100).toFixed(2) }}</span></div>
            <div style="display:flex;justify-content:space-between"><span>Tax</span><span>${{ ((o.tax || 0) / 100).toFixed(2) }}</span></div>
            <div style="display:flex;justify-content:space-between;font-weight:800;font-size:15px;border-top:1px solid var(--gray-light);padding-top:6px">
              <span>Total</span><span style="color:var(--plum)">${{ ((o.grand_total || 0) / 100).toFixed(2) }}</span>
            </div>
          </div>
        </div>

        <div style="display:grid;gap:16px;align-content:start">
          <div class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:10px">Shipping to</h3>
            <div style="font-size:13.5px;line-height:1.7">
              {{ o.address?.full_name }}<br>
              {{ o.address?.line1 }} {{ o.address?.line2 }}<br>
              {{ o.address?.city }}, {{ o.address?.state }} {{ o.address?.zip }}<br>
              {{ o.address?.country }}
            </div>
          </div>
          <div v-if="[1, 2, 3].includes(o.status)" class="card" style="padding:20px">
            <h3 style="font-size:15px;margin-bottom:10px">Need help?</h3>
            <button class="btn btn-secondary btn-block btn-sm" @click="requestReturn">Start a return / exchange</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
