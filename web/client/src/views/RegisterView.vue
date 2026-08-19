<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useCartStore } from '../stores/cart'
import { useUiStore } from '../stores/ui'

const auth = useAuthStore()
const cart = useCartStore()
const ui = useUiStore()
const router = useRouter()

const name = ref('')
const email = ref('')
const password = ref('')
const busy = ref(false)

async function submit() {
  if (!name.value.trim() || !email.value.includes('@') || password.value.length < 8) {
    ui.toast('Name + valid email + 8-char password required', 'error')
    return
  }
  busy.value = true
  try {
    await auth.register(email.value.trim(), password.value, name.value.trim())
    await cart.mergeAfterLogin()
    ui.toast('Welcome to the glam crew! 500 points added ✓', 'success')
    router.push('/account')
  } catch (e) {
    ui.toast(e.status === 409 ? 'Email already registered — sign in instead' : 'Register failed', 'error')
  } finally { busy.value = false }
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:440px">
      <div class="card" style="padding:30px">
        <h1 style="font-family:var(--font-title);font-size:26px;margin-bottom:4px">Join GLOWMAG ✨</h1>
        <p style="font-size:13.5px;color:var(--gray);margin-bottom:20px">500 welcome points · member-only drops · free birthday gift.</p>
        <form @submit.prevent="submit">
          <div class="field">
            <label>Name</label>
            <input v-model="name" class="input" autocomplete="name" placeholder="Glam Queen">
          </div>
          <div class="field">
            <label>Email</label>
            <input v-model="email" class="input" type="email" autocomplete="email" placeholder="you@example.com">
          </div>
          <div class="field">
            <label>Password (8+ chars)</label>
            <input v-model="password" class="input" type="password" autocomplete="new-password" placeholder="••••••••">
          </div>
          <button class="btn btn-primary btn-block btn-lg" :class="{ loading: busy }" :disabled="busy">Create Account</button>
        </form>
        <div style="text-align:center;margin-top:14px;font-size:13px;color:var(--gray)">
          Already a member? <router-link to="/login" style="color:var(--plum);font-weight:600">Sign in</router-link>
        </div>
      </div>
    </div>
  </section>
</template>
