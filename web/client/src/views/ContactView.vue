<script setup>
import { ref } from 'vue'
import { req } from '../api/client'
import { useUiStore } from '../stores/ui'

const ui = useUiStore()
const form = ref({ name: '', email: '', topic: 'order', message: '' })
const busy = ref(false)

async function submit() {
  const f = form.value
  if (!f.name || !f.email.includes('@') || !f.message) {
    ui.toast('Please complete all fields', 'error')
    return
  }
  busy.value = true
  try {
    await req('POST', '/api/support/tickets', {
      subject: `[${f.topic}] ${f.name}`,
      message: f.message,
      email: f.email,
    })
    ui.toast('Ticket created — reply within ~4 hours ✓', 'success')
    f.message = ''
  } catch (e) {
    ui.toast(e.status === 401 ? 'Sign in to open a ticket' : 'Submit failed', 'error')
  } finally { busy.value = false }
}
</script>

<template>
  <section class="section">
    <div class="container" style="max-width:640px">
      <div class="section-head"><h2 class="section-title">Contact Us 💬</h2></div>
      <div class="card" style="padding:24px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field"><label>Your name</label><input v-model="form.name" class="input"></div>
          <div class="field"><label>Email</label><input v-model="form.email" class="input" type="email"></div>
        </div>
        <div class="field">
          <label>Topic</label>
          <select v-model="form.topic" class="input">
            <option value="order">Order / shipping</option>
            <option value="return">Returns &amp; exchanges</option>
            <option value="product">Product question</option>
            <option value="collab">Collab / press</option>
            <option value="other">Something else</option>
          </select>
        </div>
        <div class="field"><label>Message</label><textarea v-model="form.message" class="input" rows="5" placeholder="How can we help?"></textarea></div>
        <button class="btn btn-primary" :class="{ loading: busy }" :disabled="busy" @click="submit">Send message</button>
        <p style="font-size:12.5px;color:var(--gray);margin-top:12px">
          Average first reply: under 4 hours (Mon–Sat). For order issues, include your NS… order number.
        </p>
      </div>
    </div>
  </section>
</template>
