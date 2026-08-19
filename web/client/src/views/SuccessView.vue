<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { req } from '../api/client'
import { useCartStore } from '../stores/cart'

const route = useRoute()
const cart = useCartStore()
const order = ref(null)
const loaded = ref(false)

onMounted(async () => {
  cart.refresh().catch(() => {})   /* 下单后服务端车已清空，拉平本地 */
  const no = route.query.no
  if (no) {
    try { order.value = await req('GET', '/api/orders/' + no) } catch (_) { /* 未登录无邮箱参数时静默 */ }
  }
  loaded.value = true
})
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:640px;text-align:center">
      <div style="width:72px;height:72px;border-radius:50%;background:rgba(62,189,147,.12);border:2px solid rgba(62,189,147,.4);display:flex;align-items:center;justify-content:center;margin:0 auto 18px;font-size:32px">✓</div>
      <h1 style="font-family:var(--font-title);font-size:32px;margin-bottom:8px">Order confirmed!</h1>
      <p style="color:var(--gray);margin-bottom:8px">
        Thanks for your order{{ order ? `, confirmation sent to ${order.email}` : '' }}.
      </p>
      <div v-if="order" class="card" style="padding:18px;margin:20px 0;text-align:left;display:grid;gap:8px;font-size:14px">
        <div style="display:flex;justify-content:space-between"><span>Order</span><b>{{ order.order_no }}</b></div>
        <div style="display:flex;justify-content:space-between"><span>Total</span><b style="color:var(--plum)">${{ ((order.grand_total || 0) / 100).toFixed(2) }}</b></div>
        <div style="display:flex;justify-content:space-between"><span>Status</span>
          <span class="tag" :class="order.status >= 1 ? 'tag-paid' : 'tag-pending'">
            {{ ['Pending', 'Paid', 'Packing', 'Shipped', 'Delivered', 'Done', 'Cancelled', 'Refunded', 'Expired', 'Refunded'][order.status] || '—' }}
          </span>
        </div>
      </div>
      <div v-else-if="loaded" class="card" style="padding:18px;margin:20px 0;font-size:14px">
        Order <b>{{ route.query.no }}</b> received. Track it anytime from your account.
      </div>
      <div style="display:flex;gap:12px;justify-content:center;margin-top:10px">
        <router-link to="/account/orders" class="btn btn-primary">View my orders</router-link>
        <router-link to="/store" class="btn btn-secondary">Keep shopping</router-link>
      </div>
      <p style="font-size:12.5px;color:var(--gray);margin-top:22px">
        🎁 You earned Glow points on this order — redeem 100 pts for $1 off next time.
      </p>
    </div>
  </section>
</template>
