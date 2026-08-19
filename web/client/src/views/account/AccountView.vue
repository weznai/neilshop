<script setup>
import { computed, onMounted, ref } from 'vue'
import { req } from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const orders = ref([])
const loaded = ref(false)

onMounted(async () => {
  try { orders.value = (await req('GET', '/api/orders')).items || [] } catch (_) { /* */ }
  loaded.value = true
})

const u = computed(() => auth.user || {})
const TIER = { 0: 'Glow', 1: 'Shimmer', 2: 'Diva', 3: 'Queen' }
const recent = computed(() => orders.value.slice(0, 3))
</script>

<template>
  <div style="display:grid;gap:18px">
    <div class="card" style="padding:22px;background:linear-gradient(135deg,var(--rose-pale),#fff 70%)">
      <div style="display:flex;gap:14px;align-items:center">
        <span style="width:56px;height:56px;border-radius:50%;background:linear-gradient(135deg,var(--rose),var(--plum));color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:22px;font-weight:700">
          {{ (u.name || u.email || 'G').charAt(0).toUpperCase() }}
        </span>
        <div>
          <h2 style="font-family:var(--font-title);font-size:22px">Hi, {{ u.name || 'glam queen' }} 👑</h2>
          <div style="font-size:13px;color:var(--gray)">
            <span class="tag tag-paid">{{ TIER[u.tier || 0] }} tier</span>
            {{ u.points?.toLocaleString?.() || 0 }} pts · lifetime ${{ ((u.total_spent || 0) / 100).toFixed(2) }}
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-3">
      <div class="card" style="padding:18px">
        <div style="font-size:12.5px;color:var(--gray)">📦 Orders</div>
        <b style="font-size:26px">{{ orders.length }}</b>
        <div style="font-size:12.5px"><router-link to="/account/orders" style="color:var(--plum)">View all →</router-link></div>
      </div>
      <div class="card" style="padding:18px">
        <div style="font-size:12.5px;color:var(--gray)">⭐ Glow Points</div>
        <b style="font-size:26px;color:var(--plum)">{{ u.points?.toLocaleString?.() || 0 }}</b>
        <div style="font-size:12.5px"><router-link to="/account/points" style="color:var(--plum)">Redeem →</router-link></div>
      </div>
      <div class="card" style="padding:18px">
        <div style="font-size:12.5px;color:var(--gray)">💜 Wishlist</div>
        <b style="font-size:26px">{{ JSON.parse(localStorage.getItem('gm_wl_count') || '0') }}</b>
        <div style="font-size:12.5px"><router-link to="/account/wishlist" style="color:var(--plum)">Manage →</router-link></div>
      </div>
    </div>

    <div class="card" style="padding:20px">
      <h3 style="font-size:16px;margin-bottom:12px">Recent orders</h3>
      <div v-if="recent.length" style="display:grid;gap:10px">
        <div v-for="o in recent" :key="o.order_no" style="display:flex;justify-content:space-between;align-items:center;font-size:14px;padding:10px 0;border-bottom:1px solid var(--gray-light)">
          <div><b>{{ o.order_no }}</b><div style="font-size:12px;color:var(--gray)">{{ new Date(o.created_at).toLocaleDateString() }}</div></div>
          <b style="color:var(--plum)">${{ ((o.grand_total || 0) / 100).toFixed(2) }}</b>
          <router-link class="btn btn-secondary btn-sm" :to="{ path: '/account/orders/detail', query: { no: o.order_no } }">Detail</router-link>
        </div>
      </div>
      <div v-else-if="loaded" style="color:var(--gray);font-size:14px;padding:14px 0">
        No orders yet — <router-link to="/store" style="color:var(--plum)">start shopping</router-link> 💅
      </div>
    </div>
  </div>
</template>
