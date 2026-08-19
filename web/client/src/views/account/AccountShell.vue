<script setup>
/* 账户中心外壳：标题 + 侧栏导航 + 登录守卫 */
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const ready = ref(false)
const NAV = [
  ['/account', 'Overview', '👤'],
  ['/account/orders', 'Orders', '📦'],
  ['/account/returns', 'Returns & Exchanges', '↩️'],
  ['/account/points', 'Glow Points', '⭐'],
  ['/account/address', 'Address Book', '📍'],
  ['/account/wishlist', 'Wishlist', '💜'],
  ['/account/settings', 'Settings', '⚙️'],
]

onMounted(async () => {
  if (auth.isLoggedIn) {
    try { await auth.me() } catch (_) { /* 401 → 视图内自行 gate */ }
  }
  ready.value = true
})
</script>

<template>
  <section class="section">
    <div class="container">
      <div v-if="ready && !auth.isLoggedIn" style="text-align:center;padding:60px 0;color:var(--gray)">
        <div style="font-size:44px;margin-bottom:10px">🔐</div>
        <p style="margin-bottom:16px">Sign in to view your account</p>
        <router-link class="btn btn-primary" :to="{ path: '/login', query: { next: route.fullPath } }">Sign In</router-link>
      </div>

      <div v-else class="grid-m-1" style="display:grid;grid-template-columns:220px 1fr;gap:28px;align-items:start">
        <aside class="card" style="padding:16px">
          <div style="padding:4px 8px 12px;border-bottom:1px solid var(--gray-light);margin-bottom:10px">
            <b style="font-size:14px">{{ auth.user?.name || auth.user?.email || 'Account' }}</b>
            <div style="font-size:12px;color:var(--gray)">{{ auth.user?.email }}</div>
          </div>
          <nav style="display:grid;gap:2px">
            <router-link
              v-for="[href, label, ico] in NAV" :key="href" :to="href"
              style="display:flex;gap:10px;align-items:center;padding:9px 10px;border-radius:9px;font-size:13.5px;color:var(--ink);text-decoration:none"
              :style="{ background: route.path === href ? 'var(--rose-pale)' : '', fontWeight: route.path === href ? '700' : '' }"
            >{{ ico }} {{ label }}</router-link>
            <button
              style="display:flex;gap:10px;align-items:center;padding:9px 10px;border-radius:9px;font-size:13.5px;color:var(--error);background:none;border:none;cursor:pointer;text-align:left"
              @click="auth.logout().then(() => $router.push('/'))"
            >🚪 Sign out</button>
          </nav>
        </aside>
        <div><router-view /></div>
      </div>
    </div>
  </section>
</template>
