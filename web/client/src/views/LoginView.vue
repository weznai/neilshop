<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { i18n } from '../i18n'
import { useAuthStore } from '../stores/auth'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'

const auth = useAuthStore()
const cart = useCartStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()

const email = ref('')
const password = ref('')
const busy = ref(false)

async function submit() {
  if (!email.value.includes('@') || !password.value) {
    ui.toast('Enter your email and password', 'error')
    return
  }
  busy.value = true
  try {
    await auth.login(email.value.trim(), password.value)
    await cart.mergeAfterLogin()
    router.push(route.query.next ? String(route.query.next) : '/account')
  } catch (e) {
    ui.toast(e.status === 401 ? 'Email or password incorrect' : 'Login failed — try again', 'error')
  } finally { busy.value = false }
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:420px">
      <div class="card" style="padding:30px">
        <h1 style="font-family:var(--font-title);font-size:26px;margin-bottom:4px">Welcome back 💅</h1>
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:20px">Sign in for orders, points &amp; faster checkout.</p>
        <form @submit.prevent="submit">
          <div class="field">
            <label>Email</label>
            <input v-model="email" class="input" type="email" autocomplete="email" placeholder="you@example.com">
          </div>
          <div class="field">
            <label>Password</label>
            <input v-model="password" class="input" type="password" autocomplete="current-password" placeholder="••••••••">
          </div>
          <button class="btn btn-primary btn-block btn-lg" :class="{ loading: busy }" :disabled="busy">Sign In</button>
        </form>
        <div style="text-align:center;margin-top:14px;font-size:13px;color:var(--gray)">
          New here? <router-link to="/register" style="color:var(--plum);font-weight:600">Create account</router-link>
          · <router-link to="/track" style="text-decoration:underline">Track order (no login)</router-link>
        </div>
        <div style="margin-top:16px;padding:10px 12px;background:var(--rose-pale);border-radius:10px;font-size:12px;color:var(--gray)">
          🧪 Demo account: <b>emma@glowmag.com</b> / <b>glowmag123</b>
        </div>
      </div>
    </div>
  </section>
</template>
